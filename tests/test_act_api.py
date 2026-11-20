import json

import httpx
import pytest

from acta.act_api import ActClient


def test_login_posts_api_key_and_returns_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == httpx.URL("https://tenant.example/rest/v1/auth/login")
        assert json.loads(request.content) == {"api_key": "secret"}
        return httpx.Response(200, json={"token": "bearer-token"})

    client = ActClient(
        "https://tenant.example/rest/v1/",
        "secret",
        transport=httpx.MockTransport(handler),
    )

    assert client.login() == "bearer-token"


def test_poll_operation_waits_until_completed_case_insensitively():
    responses = iter(
        [
            {"id": "operation-1", "is_completed": False, "status": "running"},
            {"id": "operation-1", "is_completed": True, "status": "COMPLETED"},
        ]
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"token": "bearer-token"})
        return httpx.Response(200, json=next(responses))

    client = ActClient(
        "https://tenant.example/rest/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    client.login()

    result = client.poll_operation(
        {"id": "operation-1"},
        "topology upload",
        max_iterations=2,
        interval=0,
    )

    assert result["status"] == "COMPLETED"
    poll_requests = requests[1:]
    assert len(poll_requests) == 2
    assert all(
        request.url.path == "/rest/v1/operations/operation-1"
        for request in poll_requests
    )
    assert all(
        request.headers["Authorization"] == "Bearer bearer-token"
        for request in poll_requests
    )


def test_poll_operation_rejects_missing_operation_id():
    client = ActClient(
        "https://tenant.example/rest/v1",
        "secret",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )

    with pytest.raises(ValueError, match="operation ID.*topology upload"):
        client.poll_operation({}, "topology upload", interval=0)


def test_poll_operation_raises_when_completed_with_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"token": "bearer-token"})
        return httpx.Response(
            200,
            json={
                "id": "operation-1",
                "is_completed": True,
                "status": "failed",
            },
        )

    client = ActClient(
        "https://tenant.example/rest/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    client.login()

    with pytest.raises(RuntimeError, match="topology upload.*failed"):
        client.poll_operation(
            {"id": "operation-1"},
            "topology upload",
            max_iterations=1,
            interval=0,
        )


def test_poll_operation_times_out():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"token": "bearer-token"})
        return httpx.Response(
            200,
            json={
                "id": "operation-1",
                "is_completed": False,
                "status": "running",
            },
        )

    client = ActClient(
        "https://tenant.example/rest/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    client.login()

    with pytest.raises(TimeoutError, match="topology upload.*1 iteration"):
        client.poll_operation(
            {"id": "operation-1"},
            "topology upload",
            max_iterations=1,
            interval=0,
        )

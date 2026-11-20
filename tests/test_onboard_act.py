"""Unit tests for ACT onboard helpers (no live SSH / ACT)."""

from __future__ import annotations

import httpx
import pytest

from acta.act_api import ActClient
from acta.onboard_act import (
    EOS_PASS_DEFAULT,
    EOS_USER_DEFAULT,
    build_terminattr_snippet,
    resolve_eos_credentials,
    run_onboard_act,
)


def test_resolve_eos_credentials_from_veos_block():
    username, password = resolve_eos_credentials(
        {"veos": {"username": "admin", "password": "arista123"}}
    )

    assert username == "admin"
    assert password == "arista123"


def test_resolve_eos_credentials_defaults_when_veos_missing():
    username, password = resolve_eos_credentials({})

    assert username == EOS_USER_DEFAULT
    assert password == EOS_PASS_DEFAULT


def test_resolve_eos_credentials_defaults_when_topology_none():
    username, password = resolve_eos_credentials(None)

    assert username == EOS_USER_DEFAULT
    assert password == EOS_PASS_DEFAULT


def test_resolve_eos_credentials_partial_veos_uses_defaults():
    username, password = resolve_eos_credentials({"veos": {"username": "ops"}})

    assert username == "ops"
    assert password == EOS_PASS_DEFAULT


def test_build_terminattr_snippet_matches_onboard_sh():
    snippet = build_terminattr_snippet(
        cvaas_token="enrollment-token",
        cvaas_host="apiserver.arista.io",
        cvaas_port="443",
    )

    assert snippet == (
        "enable\n"
        'bash echo "enrollment-token" > /tmp/cv-onboarding-token\n'
        "configure\n"
        "daemon TerminAttr\n"
        "   exec /usr/bin/TerminAttr "
        "-smashexcludes=ale,flexCounter,hardware,kni,pulse,strata "
        "-cvaddr=apiserver.arista.io:443 "
        "-cvauth=token-secure,/tmp/cv-onboarding-token -taillogs\n"
        "   shutdown\n"
        "   no shutdown\n"
        "end\n"
        "write"
    )


def test_run_onboard_act_pastes_snippet_via_injected_ssh():
    lab = {
        "id": "lab-1",
        "name": "demo-lab",
        "state": 2,
        "topology_definition": "demo.yml",
    }
    lab_detail = {
        "id": "lab-1",
        "name": "demo-lab",
        "topology_definition": "demo.yml",
        "devices": {
            "veos": [
                {"hostname": "spine1", "internal_ip": "10.0.0.1"},
                {"hostname": "leaf1", "internal_ip": "10.0.0.2"},
            ]
        },
    }
    topology_detail = {
        "id": "topo-1",
        "topology": {
            "veos": {"username": "cvpadmin", "password": "secret!"},
            "nodes": [
                {"spine1": {"node_type": "veos"}},
                {"leaf1": {"node_type": "veos"}},
            ],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/auth/login"):
            return httpx.Response(200, json={"token": "bearer-token"})
        if path.endswith("/labs") and request.method == "GET":
            return httpx.Response(200, json={"result": [lab]})
        if path.endswith("/labs/lab-1"):
            return httpx.Response(200, json=lab_detail)
        if path.endswith("/topologies") and request.method == "GET":
            assert request.url.params.get("topology_pathname") == "demo.yml"
            return httpx.Response(200, json={"result": [{"id": "topo-1"}]})
        if path.endswith("/topologies/topo-1"):
            return httpx.Response(200, json=topology_detail)
        raise AssertionError(f"unexpected request: {request.method} {path}")

    client = ActClient(
        "https://tenant.example/rest/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    client.login()

    ssh_calls: list[tuple[str, str]] = []

    def fake_ssh(host: str, commands: str) -> None:
        ssh_calls.append((host, commands))

    credentials = run_onboard_act(
        client,
        act_user="alice",
        cvaas_token="enrollment-token",
        cvaas_host="apiserver.arista.io",
        run_ssh=fake_ssh,
    )

    expected = build_terminattr_snippet(
        cvaas_token="enrollment-token",
        cvaas_host="apiserver.arista.io",
    )
    assert credentials == ("cvpadmin", "secret!")
    assert ssh_calls == [
        ("10.0.0.1", expected),
        ("10.0.0.2", expected),
    ]


def test_run_onboard_act_raises_when_no_running_labs():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"token": "bearer-token"})
        if request.url.path.endswith("/labs"):
            return httpx.Response(
                200,
                json={"result": [{"id": "lab-1", "name": "stopped", "state": 1}]},
            )
        raise AssertionError(f"unexpected request: {request.url.path}")

    client = ActClient(
        "https://tenant.example/rest/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    client.login()

    with pytest.raises(RuntimeError, match="No Running labs"):
        run_onboard_act(
            client,
            act_user="alice",
            cvaas_token="tok",
            cvaas_host="apiserver.arista.io",
            run_ssh=lambda host, commands: None,
        )


def test_run_onboard_act_prompts_when_multiple_running_labs():
    labs = [
        {
            "id": "lab-a",
            "name": "alpha",
            "state": 2,
            "topology_definition": "a.yml",
        },
        {
            "id": "lab-b",
            "name": "beta",
            "state": 2,
            "topology_definition": "b.yml",
        },
    ]
    lab_detail = {
        "id": "lab-b",
        "name": "beta",
        "topology_definition": "b.yml",
        "devices": {"veos": [{"hostname": "spine1", "internal_ip": "10.0.0.9"}]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/auth/login"):
            return httpx.Response(200, json={"token": "bearer-token"})
        if path.endswith("/labs") and request.method == "GET":
            return httpx.Response(200, json={"result": labs})
        if path.endswith("/labs/lab-b"):
            return httpx.Response(200, json=lab_detail)
        if path.endswith("/topologies"):
            return httpx.Response(200, json={"result": []})
        raise AssertionError(f"unexpected request: {request.method} {path}")

    client = ActClient(
        "https://tenant.example/rest/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    client.login()

    ssh_calls: list[tuple[str, str]] = []

    run_onboard_act(
        client,
        act_user="alice",
        cvaas_token="tok",
        cvaas_host="apiserver.arista.io",
        run_ssh=lambda host, commands: ssh_calls.append((host, commands)),
        choose_lab=lambda running: running[1],
    )

    assert [host for host, _ in ssh_calls] == ["10.0.0.9"]

"""HTTP tests for the local Web UI API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from acta.web.app import create_app
from acta.web.errors import WebError
from acta.web.jobs import submit_job


def test_health_ok(tmp_path: Path) -> None:
    client = TestClient(create_app(labs_root=tmp_path))
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "dot" in body
    assert body["bind_hint"] == "127.0.0.1"
    assert body["labs_root"] == str(tmp_path.resolve())


def test_web_error_handler_returns_json(tmp_path: Path) -> None:
    app = create_app(labs_root=tmp_path)

    @app.get("/api/_boom")
    def _boom() -> None:
        raise WebError(400, "bad input", fields={"name": "required"})

    # create_app may mount SPA StaticFiles at "/"; a route registered after
    # that mount is shadowed. Prefer the API probe over the catch-all.
    boom_route = app.router.routes.pop()
    app.router.routes.insert(0, boom_route)

    client = TestClient(app)
    response = client.get("/api/_boom")
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "bad input"
    assert body["fields"] == {"name": "required"}


def _preview_payload() -> dict:
    return {
        "hostname_prefix": "demo",
        "serial_prefix": "DEMO",
        "eos_version": "4.35.4M",
        "capacity": {
            "fabric_mode": "l3ls",
            "max_spines": 2,
            "max_leaves": 4,
            "max_mleafs_per_pair": 0,
            "spines": 2,
            "leaves": 4,
        },
        "mlag_pairs": True,
        "spine_mlag": False,
        "member_leaf_pairs": [],
        "member_leaves_per_pair": 0,
    }


def test_preview_and_write_topology(tmp_path: Path) -> None:
    client = TestClient(create_app(labs_root=tmp_path))
    preview = client.post("/api/preview", json=_preview_payload())
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert "demo-spine1" in body["yaml_text"]
    assert body["summary"]["node_count"] >= 1

    written = client.post(
        "/api/topologies",
        json={"yaml_text": body["yaml_text"], "stem": "demo"},
    )
    assert written.status_code == 200, written.text
    name = written.json()["name"]
    assert name.endswith(".yml")

    listed = client.get("/api/topologies")
    assert listed.status_code == 200
    assert any(item["name"] == name for item in listed.json())

    fetched = client.get(f"/api/topologies/{name}")
    assert fetched.status_code == 200
    assert "demo-spine1" in fetched.json()["yaml_text"]


def test_preview_rejects_invalid_spec(tmp_path: Path) -> None:
    client = TestClient(create_app(labs_root=tmp_path))
    payload = _preview_payload()
    payload["spine_mlag"] = True
    response = client.post("/api/preview", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_jobs_list_and_get(tmp_path: Path) -> None:
    client = TestClient(create_app(labs_root=tmp_path))
    job = submit_job("test.noop", lambda: None)
    for _ in range(50):
        detail = client.get(f"/api/jobs/{job.id}")
        assert detail.status_code == 200
        if detail.json()["status"] in {"succeeded", "failed"}:
            break
    assert detail.json()["status"] == "succeeded"
    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert any(item["id"] == job.id for item in listed.json())

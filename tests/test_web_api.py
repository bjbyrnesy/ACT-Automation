"""HTTP tests for the local Web UI API stub."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from acta.web.app import create_app
from acta.web.errors import WebError


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

    client = TestClient(app)
    response = client.get("/api/_boom")
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "bad input"
    assert body["fields"] == {"name": "required"}

"""FastAPI application factory for the local Web UI."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from acta.web.errors import WebError


def create_app(*, labs_root: Path) -> FastAPI:
    """Build the API app bound to a labs directory."""
    root = labs_root.resolve()
    app = FastAPI(title="ACTA Web UI", version="0.1.0")
    app.state.labs_root = root

    @app.exception_handler(WebError)
    async def _web_error_handler(_request: Request, exc: WebError) -> JSONResponse:
        payload: dict[str, object] = {"detail": exc.detail}
        if exc.fields is not None:
            payload["fields"] = exc.fields
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "dot": shutil.which("dot") is not None,
            "labs_root": str(root),
            "bind_hint": "127.0.0.1",
        }

    return app

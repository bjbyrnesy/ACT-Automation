"""FastAPI routes for lab-host container images."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from acta.web import images
from acta.web.settings_api import get_settings

router = APIRouter()

_RUNTIMES = frozenset({"docker", "podman"})


@router.get("/api/images")
def get_images(request: Request) -> dict[str, Any]:
    """List images on the configured lab host."""
    settings = get_settings(Path(request.app.state.labs_root))
    host = str(settings.get("CLAB_HOST") or "").strip() or None
    preferred: str | None = (
        str(settings.get("CLAB_RUNTIME") or os.environ.get("CLAB_RUNTIME") or "")
        .strip()
        .lower()
    )
    if preferred not in _RUNTIMES:
        preferred = None
    runtime = images.resolve_clab_runtime(host, preferred)
    rows = images.list_host_images(host=host, runtime=runtime)
    return {"images": rows, "runtime": runtime, "host": host or ""}

"""FastAPI routes for lab-host container images."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from acta.web import images
from acta.web.errors import WebError
from acta.web.jobs import submit_job
from acta.web.settings_api import get_settings

router = APIRouter()

_RUNTIMES = frozenset({"docker", "podman"})
_UPLOAD_DIR = ".acta-uploads"


def _host_and_runtime(request: Request) -> tuple[str | None, str]:
    """Lab host and resolved container runtime from Web UI settings."""
    settings = get_settings(Path(request.app.state.labs_root))
    host = str(settings.get("CLAB_HOST") or "").strip() or None
    preferred: str | None = (
        str(settings.get("CLAB_RUNTIME") or os.environ.get("CLAB_RUNTIME") or "")
        .strip()
        .lower()
    )
    if preferred not in _RUNTIMES:
        preferred = None
    return host, images.resolve_clab_runtime(host, preferred)


@router.get("/api/images")
def get_images(request: Request) -> dict[str, Any]:
    """List images on the configured lab host."""
    host, runtime = _host_and_runtime(request)
    rows = images.list_host_images(host=host, runtime=runtime)
    return {"images": rows, "runtime": runtime, "host": host or ""}


def _too_large() -> WebError:
    return WebError(400, "archive exceeds 10GB limit", fields={"file": "too large"})


async def _save_upload(upload: UploadFile, dest: Path) -> int:
    """Stream ``upload`` to ``dest`` (mode 0600), enforcing ``UPLOAD_MAX_BYTES``."""
    total = 0
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > images.UPLOAD_MAX_BYTES:
                    raise _too_large()
                out.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return total


@router.post("/api/jobs/images/load")
async def load_image(request: Request) -> dict[str, Any]:
    """Upload an image archive and load it on the lab host as a job.

    ``BodyLimitMiddleware`` enforces the byte cap while the body streams in;
    the checks here are defence in depth.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > images.UPLOAD_MAX_BYTES:
        raise _too_large()
    form = await request.form()
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise WebError(400, "file is required", fields={"file": "required"})
        name = str(form.get("name") or "").strip() or None
        tag = str(form.get("tag") or "").strip() or None
        images.assert_archive_name(upload.filename or "")
        images.assert_image_name_tag(name, tag)
        host, runtime = await run_in_threadpool(_host_and_runtime, request)
        if host:
            images.assert_scp_host(host)
        suffix = images.archive_suffix(upload.filename or "")
        dest = (
            Path(request.app.state.labs_root)
            / _UPLOAD_DIR
            / f"{uuid.uuid4().hex}{suffix}"
        )
        await _save_upload(upload, dest)
    finally:
        await form.close()

    def run() -> None:
        try:
            images.load_archive_on_host(
                host=host, runtime=runtime, archive_path=dest, name=name, tag=tag
            )
        finally:
            dest.unlink(missing_ok=True)

    try:
        job = submit_job("images.load", run)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {"id": job.id, "kind": job.kind, "status": job.status}

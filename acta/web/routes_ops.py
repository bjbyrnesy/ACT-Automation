"""FastAPI routes for ops jobs (clab / ACT) and sync extend / attach."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from acta.web import ops
from acta.web.errors import WebError
from acta.web.jobs import Job, submit_job
from acta.web.settings_api import get_settings

router = APIRouter()

_SYNC_ERRORS = (ValueError, FileExistsError, FileNotFoundError, OSError, TypeError)
_RUNTIMES = frozenset({"docker", "podman"})


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = None

    def options(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude={"path"})


class ClabBody(_Body):
    host: str | None = None
    runtime: Literal["docker", "podman"] | None = None
    from_act: bool | None = None
    name: str | None = None
    image: str | None = None
    host_image: str | None = None
    mgmt_network: str | None = None
    mgmt_bridge: str | None = None
    mgmt_subnet: str | None = None
    mgmt_gateway: str | None = None
    mgmt_range: str | None = None
    mgmt_mtu: int | None = None
    disableaaa: bool | None = None


class ActUploadBody(_Body):
    deploy: bool = False
    tenant: str | None = None


class ActOnboardBody(_Body):
    tenant: str | None = None
    user: str | None = None
    api_key: str | None = None
    cvaas_host: str | None = None
    cvaas_token: str | None = None


class ExtendBody(_Body):
    add: str | None = None
    site: str | None = None
    pair: int | None = None
    count: int = 1
    name: str | None = None
    first_site: str | None = None
    rekey_identity: bool | None = None
    bb_redundancy: str | None = None
    border_redundancy: str | None = None
    bb_count: int | None = None
    border_count: int | None = None
    force: bool | None = None


class AttachBody(_Body):
    host: str | None = None
    to: list[str] | None = None
    mlag_pair: int | None = None
    mleaf: int | None = None
    et: int | None = None


def _resolve(request: Request, raw: str | None) -> Path:
    """Resolve *raw* inside the labs root and require a readable file."""
    if raw is None or not raw.strip():
        return ops.require_written_path(None)
    root: Path = request.app.state.labs_root
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root):
        raise WebError(400, "path must be inside the labs directory")
    return ops.require_written_path(candidate)


def _clab_opts(request: Request, body: ClabBody) -> dict[str, Any]:
    """Job options with Web UI settings filling host/runtime/images when omitted."""
    opts = body.options()
    settings = get_settings(Path(request.app.state.labs_root))
    if opts.get("host") is None:
        host = str(settings.get("CLAB_HOST") or "").strip()
        if host:
            opts["host"] = host
    if opts.get("runtime") is None:
        runtime = (
            str(settings.get("CLAB_RUNTIME") or os.environ.get("CLAB_RUNTIME") or "")
            .strip()
            .lower()
        )
        if runtime in _RUNTIMES:
            opts["runtime"] = runtime
    if opts.get("image") is None:
        image = str(settings.get("CLAB_IMAGE") or "").strip()
        if image:
            opts["image"] = image
    if opts.get("host_image") is None:
        host_image = str(settings.get("CLAB_HOST_IMAGE") or "").strip()
        if host_image:
            opts["host_image"] = host_image
    return opts


def _job_view(job: Job) -> dict[str, Any]:
    return {"id": job.id, "kind": job.kind, "status": job.status}


def _submit(kind: str, fn: Callable[[], object]) -> dict[str, Any]:
    def run() -> None:
        result = fn()
        if isinstance(result, Path):
            print(f"Wrote {result}")

    return _job_view(submit_job(kind, run))


def _sync(fn: Callable[[], Path]) -> dict[str, str]:
    try:
        path = fn()
    except _SYNC_ERRORS as exc:
        raise WebError(400, str(exc)) from exc
    return {"path": str(path), "name": path.name}


@router.post("/api/jobs/clab/generate")
def clab_generate(body: ClabBody, request: Request) -> dict[str, Any]:
    path, opts = _resolve(request, body.path), _clab_opts(request, body)
    return _submit("clab.generate", lambda: ops.op_clab_generate(path, **opts))


@router.post("/api/jobs/clab/deploy")
def clab_deploy(body: ClabBody, request: Request) -> dict[str, Any]:
    path, opts = _resolve(request, body.path), _clab_opts(request, body)
    return _submit("clab.deploy", lambda: ops.op_clab_deploy(path, **opts))


@router.post("/api/jobs/clab/destroy")
def clab_destroy(body: ClabBody, request: Request) -> dict[str, Any]:
    path, opts = _resolve(request, body.path), _clab_opts(request, body)
    return _submit("clab.destroy", lambda: ops.op_clab_destroy(path, **opts))


@router.post("/api/jobs/clab/redeploy")
def clab_redeploy(body: ClabBody, request: Request) -> dict[str, Any]:
    path, opts = _resolve(request, body.path), _clab_opts(request, body)
    return _submit("clab.redeploy", lambda: ops.op_clab_redeploy(path, **opts))


@router.post("/api/jobs/clab/onboard")
def clab_onboard(body: ClabBody, request: Request) -> dict[str, Any]:
    path, opts = _resolve(request, body.path), _clab_opts(request, body)
    return _submit("clab.onboard", lambda: ops.op_clab_onboard(path, **opts))


@router.post("/api/jobs/act/upload")
def act_upload(body: ActUploadBody, request: Request) -> dict[str, Any]:
    path = _resolve(request, body.path)
    deploy, opts = body.deploy, body.options()
    opts.pop("deploy", None)
    return _submit("act.upload", lambda: ops.op_act_upload(path, deploy=deploy, **opts))


@router.post("/api/jobs/act/onboard")
def act_onboard(body: ActOnboardBody) -> dict[str, Any]:
    opts = body.options()
    return _submit("act.onboard", lambda: ops.op_act_onboard(**opts))


@router.post("/api/extend")
def extend(body: ExtendBody, request: Request) -> dict[str, str]:
    path, opts = _resolve(request, body.path), body.options()
    return _sync(lambda: ops.op_extend(path, **opts))


@router.post("/api/attach")
def attach(body: AttachBody, request: Request) -> dict[str, str]:
    path, opts = _resolve(request, body.path), body.options()
    return _sync(lambda: ops.op_attach(path, **opts))

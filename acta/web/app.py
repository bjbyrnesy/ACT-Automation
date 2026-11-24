"""FastAPI application factory for the local Web UI."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from acta.capacity import Capacity
from acta.create import FabricSpec
from acta.web.errors import WebError
from acta.web.jobs import get_job, list_jobs
from acta.web.labs import (
    delete_topology,
    get_lab,
    lab_id_from_filename,
    list_labs,
    list_topologies,
    read_topology,
    write_topology,
)
from acta.web.preview import preview_from_spec
from acta.web.routes_images import router as images_router
from acta.web.routes_ops import router as ops_router
from acta.web.routes_settings import router as settings_router

_STATIC_DIR = Path(__file__).resolve().parent / "static"


class CapacityBody(BaseModel):
    fabric_mode: str
    max_spines: int
    max_leaves: int
    max_mleafs_per_pair: int = 0
    spines: int
    leaves: int
    use_case: str | None = None
    bb_redundancy: str = "mlag-peer"
    border_redundancy: str = "mlag-peer"
    bb_count: int = 2
    border_count: int = 2
    backbone_mode: str = "hub"


class PreviewBody(BaseModel):
    hostname_prefix: str
    serial_prefix: str
    eos_version: str
    capacity: CapacityBody
    mlag_pairs: bool = True
    spine_mlag: bool = False
    member_leaf_pairs: list[int] = Field(default_factory=list)
    member_leaves_per_pair: int = 0
    dc_count: int = 1
    sites: list[str] = Field(default_factory=list)


class WriteTopologyBody(BaseModel):
    yaml_text: str
    stem: str | None = None


def _spec_from_body(body: PreviewBody) -> FabricSpec:
    cap = body.capacity
    return FabricSpec(
        hostname_prefix=body.hostname_prefix,
        serial_prefix=body.serial_prefix,
        eos_version=body.eos_version,
        capacity=Capacity(
            fabric_mode=cap.fabric_mode,
            max_spines=cap.max_spines,
            max_leaves=cap.max_leaves,
            max_mleafs_per_pair=cap.max_mleafs_per_pair,
            spines=cap.spines,
            leaves=cap.leaves,
            use_case=cap.use_case,
            bb_redundancy=cap.bb_redundancy,
            border_redundancy=cap.border_redundancy,
            bb_count=cap.bb_count,
            border_count=cap.border_count,
            backbone_mode=cap.backbone_mode,
        ),
        mlag_pairs=body.mlag_pairs,
        spine_mlag=body.spine_mlag,
        member_leaf_pairs=list(body.member_leaf_pairs),
        member_leaves_per_pair=body.member_leaves_per_pair,
        dc_count=body.dc_count,
        sites=tuple(body.sites),
    )


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

    @app.post("/api/preview")
    def preview(body: PreviewBody) -> dict[str, Any]:
        result = preview_from_spec(_spec_from_body(body))
        return {
            "yaml_text": result.yaml_text,
            "png_base64": result.png_base64,
            "summary": result.summary,
        }

    @app.get("/api/topologies")
    def topologies() -> list[dict]:
        return list_topologies(root)

    @app.get("/api/labs")
    def labs() -> list[dict]:
        return list_labs(root)

    @app.get("/api/labs/{lab_id}")
    def lab_get(lab_id: str) -> dict:
        return get_lab(root, lab_id)

    @app.get("/api/topologies/{name}")
    def topology_get(name: str) -> dict:
        return read_topology(root, name)

    @app.delete("/api/topologies/{name}")
    def topology_delete(name: str) -> dict[str, str]:
        delete_topology(root, name)
        return {"deleted": name}

    @app.get("/api/topologies/{name}/attach-targets")
    def topology_attach_targets(name: str) -> dict:
        from acta.web.attach_targets import attach_targets_from_yaml

        topo = read_topology(root, name)
        return attach_targets_from_yaml(topo["yaml_text"])

    @app.post("/api/topologies")
    def topology_write(body: WriteTopologyBody) -> dict[str, str]:
        path = write_topology(root, body.yaml_text, stem=body.stem)
        return {
            "path": str(path),
            "name": path.name,
            "lab_id": lab_id_from_filename(path.name),
        }

    @app.get("/api/jobs")
    def jobs() -> list[dict]:
        return [
            {
                "id": job.id,
                "kind": job.kind,
                "status": job.status,
                "log": job.log,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
            }
            for job in list_jobs()
        ]

    @app.get("/api/jobs/{job_id}")
    def job_get(job_id: str) -> dict:
        job = get_job(job_id)
        return {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "log": job.log,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
        }

    app.include_router(images_router)
    app.include_router(ops_router)
    app.include_router(settings_router)

    # Only mount SPA when a real build is present (avoid catching /api via .gitkeep).
    if (_STATIC_DIR / "index.html").is_file():
        # Keep index.html (and SPA HTML fallbacks) uncached so restarts pick up
        # new hashed asset filenames. Hashed /assets/* can stay cacheable.
        @app.middleware("http")
        async def _spa_html_no_cache(request: Request, call_next):  # type: ignore[no-untyped-def]
            response = await call_next(request)
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                response.headers["Cache-Control"] = "no-store"
            return response

        app.mount(
            "/",
            StaticFiles(directory=_STATIC_DIR, html=True),
            name="spa",
        )

    return app

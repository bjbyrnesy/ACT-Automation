"""In-memory background job registry for Web UI ops."""

from __future__ import annotations

import contextlib
import io
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from acta.web.errors import WebError

JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class Job:
    """A single background job tracked by the Web UI."""

    id: str
    kind: str
    status: JobStatus
    log: str
    created_at: float
    finished_at: float | None


_lock = threading.Lock()
_jobs: dict[str, Job] = {}


def _run_job(job_id: str, fn: Callable[[], None]) -> None:
    buf = io.StringIO()
    with _lock:
        job = _jobs[job_id]
        job.status = "running"
    try:
        with contextlib.redirect_stdout(buf):
            fn()
    except Exception as exc:  # noqa: BLE001 — job runner must mark any failure
        with _lock:
            job = _jobs[job_id]
            captured = buf.getvalue()
            job.log = f"{captured}{exc}"
            job.status = "failed"
            job.finished_at = time.time()
        return
    with _lock:
        job = _jobs[job_id]
        job.log = buf.getvalue()
        job.status = "succeeded"
        job.finished_at = time.time()


def submit_job(kind: str, fn: Callable[[], None]) -> Job:
    """Queue ``fn`` on a background thread and return the job immediately."""
    job = Job(
        id=uuid.uuid4().hex,
        kind=kind,
        status="queued",
        log="",
        created_at=time.time(),
        finished_at=None,
    )
    with _lock:
        _jobs[job.id] = job
    thread = threading.Thread(
        target=_run_job,
        args=(job.id, fn),
        name=f"acta-job-{job.id}",
        daemon=True,
    )
    thread.start()
    return job


def get_job(job_id: str) -> Job:
    """Return a job by id or raise ``WebError`` 404."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise WebError(404, f"job not found: {job_id}")
        return job


def list_jobs() -> list[Job]:
    """Return all known jobs (newest first)."""
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)

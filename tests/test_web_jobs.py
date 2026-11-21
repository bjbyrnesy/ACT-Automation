"""Lifecycle tests for the in-memory Web UI job registry."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from acta.web import jobs as jobs_mod
from acta.web.errors import WebError
from acta.web.jobs import get_job, list_jobs, submit_job


@pytest.fixture(autouse=True)
def _clear_job_registry() -> Iterator[None]:
    with jobs_mod._lock:
        jobs_mod._jobs.clear()
    yield
    with jobs_mod._lock:
        jobs_mod._jobs.clear()


def _wait_until(
    job_id: str,
    *,
    status: str,
    timeout: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = get_job(job_id)
        if job.status == status:
            return
        time.sleep(0.01)
    raise AssertionError(
        f"job {job_id} did not reach {status!r} within {timeout}s "
        f"(last={get_job(job_id).status!r})"
    )


def test_submit_returns_quickly_with_queued_or_running() -> None:
    started = threading.Event()
    release = threading.Event()

    def _blocked() -> None:
        started.set()
        release.wait(timeout=2.0)

    before = time.monotonic()
    job = submit_job("test.block", _blocked)
    elapsed = time.monotonic() - before

    assert elapsed < 0.5
    assert job.id
    assert job.kind == "test.block"
    assert job.status in {"queued", "running"}
    assert job.finished_at is None
    assert started.wait(timeout=2.0)
    release.set()
    _wait_until(job.id, status="succeeded")


def test_successful_job_reaches_succeeded() -> None:
    def _ok() -> None:
        print("hello-job")

    job = submit_job("test.ok", _ok)
    _wait_until(job.id, status="succeeded")
    done = get_job(job.id)
    assert done.status == "succeeded"
    assert done.finished_at is not None
    assert "hello-job" in done.log


def test_failed_job_captures_error_in_log() -> None:
    def _boom() -> None:
        raise RuntimeError("boom-msg")

    job = submit_job("test.fail", _boom)
    _wait_until(job.id, status="failed")
    done = get_job(job.id)
    assert done.status == "failed"
    assert done.finished_at is not None
    assert "boom-msg" in done.log


def test_get_job_missing_raises_404() -> None:
    with pytest.raises(WebError) as exc_info:
        get_job("missing-id")
    assert exc_info.value.status_code == 404
    assert "missing-id" in exc_info.value.detail


def test_list_jobs_includes_submitted() -> None:
    job_a = submit_job("test.a", lambda: None)
    job_b = submit_job("test.b", lambda: None)
    _wait_until(job_a.id, status="succeeded")
    _wait_until(job_b.id, status="succeeded")

    ids = {j.id for j in list_jobs()}
    assert job_a.id in ids
    assert job_b.id in ids

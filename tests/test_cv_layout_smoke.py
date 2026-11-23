"""Smoke-test the TypeScript CV layout against a fixture topology."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
SMOKE = UI / "scripts" / "cv-layout-smoke.ts"
FIXTURE = ROOT / "topology-blz3-2026-11-21.yml"


@pytest.mark.skipif(
    shutil.which("npx") is None or not FIXTURE.is_file(),
    reason="npx and topology-blz3-2026-11-21.yml required",
)
def test_cv_layout_smoke() -> None:
    """Member-leaf centering, peer gap, and host placement stay stable."""
    result = subprocess.run(
        ["npx", "--yes", "tsx", str(SMOKE)],
        cwd=UI,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cvLayout smoke ok" in result.stdout

"""Destroy deployed containerlab labs."""

from __future__ import annotations

import sys
from pathlib import Path

from .support import (
    DESTROY_SCRIPT,
    fail,
    host_run,
    resolve_clab_runtime,
    resolve_topology_path,
    validate_lab,
)


def destroy(args, *, allow_missing: bool = False):
    """Tear down a lab previously deployed under ``~/.act-automation/clab/<name>``."""
    try:
        path = resolve_topology_path(Path(args.topology), args, materialize=False)
    except ValueError as exc:
        # First-time redeploy: no sibling yet — skip teardown, let deploy materialize.
        if allow_missing and "No existing .clab.yml" in str(exc):
            print(f"Skipped destroy ({exc})")
            return
        raise
    args.topology = str(path)
    lab = validate_lab(path)
    runtime = resolve_clab_runtime(args.host, getattr(args, "runtime", None))
    print(f"Using container runtime: {runtime}")
    result = host_run(
        args.host,
        DESTROY_SCRIPT,
        [lab["name"], runtime, "1" if allow_missing else "0"],
        "",
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode:
        fail(f"Destroy failed: {result.stderr.strip()}")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    skipped = "skipping destroy" in (result.stdout or "").lower()
    if skipped:
        print(f"Skipped destroy for {lab['name']} (lab not deployed).")
    else:
        print(f"Destroyed {lab['name']}.")

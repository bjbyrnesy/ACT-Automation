"""Launcher for the local Web UI (``acta serve``)."""

from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from acta.web.app import create_app

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def default_labs_root() -> Path:
    """Return ``./labs`` under the current working directory.

    Topology YAML belongs here (gitignored), not in the repo root. Tracked
    samples live under ``examples/`` and should be copied into ``labs/``.
    """
    return Path.cwd() / "labs"


def run_serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    labs_root: Path | None = None,
    open_browser: bool = True,
) -> None:
    """Run uvicorn on loopback and optionally open the default browser."""
    bind = host.strip() or "127.0.0.1"
    if bind not in _LOOPBACK:
        raise SystemExit(
            f"ERROR: refusing non-loopback bind {bind!r} "
            "(use 127.0.0.1 / localhost for v1)"
        )
    root = (labs_root or default_labs_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = create_app(labs_root=root)
    url = f"http://{bind}:{port}/"
    print(f"ACTA Web UI listening on {url}", flush=True)
    print(f"Labs root: {root}", flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    if open_browser:

        def _open() -> None:
            time.sleep(0.6)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()
    # factory=False: pass the app instance; log startup so the TTY shows "running"
    uvicorn.run(app, host=bind, port=port, log_level="info", access_log=True)

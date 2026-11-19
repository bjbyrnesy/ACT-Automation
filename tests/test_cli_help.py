import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_acta_help_lists_core_commands():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    out = proc.stdout
    for name in ("create", "extend", "upload", "onboard", "clab"):
        assert name in out

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


def test_create_help_mentions_for_target():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "create", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--for" in proc.stdout
    assert "clab" in proc.stdout


def test_upload_help_mentions_topology():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "upload", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "topology" in proc.stdout.casefold()
    assert "--deploy" in proc.stdout


def test_onboard_help_mentions_lab():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "onboard", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    out = proc.stdout.casefold()
    assert "lab" in out
    assert "terminattr" in out or "cvaas" in out


def test_clab_help_lists_subcommands():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "acta.py"), "clab", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    out = proc.stdout
    for name in ("generate", "deploy", "onboard"):
        assert name in out


def test_save_config_writes_act_create_and_clab_keys(tmp_path: Path):
    from acta.config import CONFIG_KEYS, load_config, save_config

    path = tmp_path / ".config"
    data = {key: f"v-{key}" for key in CONFIG_KEYS}
    save_config(path, data)
    loaded = load_config(path)
    assert loaded == data
    text = path.read_text(encoding="utf-8")
    for key in (
        "ACT_TENANT",
        "ACT_API_KEY",
        "MAX_SPINES",
        "CLAB_HOST",
        "CLAB_MGMT_GATEWAY",
        "CVAAS_TOKEN",
    ):
        assert f"{key}=" in text

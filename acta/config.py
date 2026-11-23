from __future__ import annotations

import os
import re
import shlex
import tempfile
from pathlib import Path

CONFIG_KEYS = (
    "ACT_TENANT",
    "ACT_USER",
    "ACT_API_KEY",
    "CVAAS_TOKEN",
    "CVAAS_USER",
    "CVAAS_HOST",
    "DC_COUNT",
    "SPINE_COUNT",
    "LEAF_COUNT",
    "MLAG_PAIRS",
    "EOS_VERSION",
    "MEMBER_LEAF_PAIRS",
    "MEMBER_LEAVES_PER_PAIR",
    "CLAB_HOST",
    "CLAB_IMAGE",
    "CLAB_NAME",
    "CLAB_RUNTIME",
    "CLAB_MGMT_SUBNET",
    "CLAB_MGMT_GATEWAY",
    "CLAB_MGMT_RANGE",
    "CLAB_MGMT_BRIDGE",
    "CLAB_MGMT_MTU",
    "CLAB_MGMT_NETWORK",
    "CLAB_DNS",
    "CLAB_NTP",
    "CLAB_DISABLEAAA",
    "CLAB_FROM_ACT",
    "CREATE_FOR",
    "FABRIC_MODE",
    "USE_CASE",
    "CLAB_HOST_IMAGE",
    "GENERIC_VERSION",
    "GENERIC_USERNAME",
    "GENERIC_PASSWORD",
    "MAX_SPINES",
    "MAX_LEAVES",
    "MAX_MLEAFS_PER_PAIR",
    "PREVIEW_AUTO",
    "PREVIEW_DEBOUNCE_MS",
)

_ASSIGNMENT_RE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*)$")


def load_config(path: Path) -> dict[str, str]:
    """Load known shell-style assignments from a config file."""
    if not path.exists():
        return {}

    config: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT_RE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid config line {line_number}")
        key = match.group("key")
        if key not in CONFIG_KEYS:
            continue
        try:
            values = shlex.split(match.group("value"), comments=False, posix=True)
        except ValueError as error:
            raise ValueError(f"invalid config line {line_number}: {error}") from error
        if len(values) > 1:
            raise ValueError(f"invalid config line {line_number}")
        config[key] = values[0] if values else ""
    return config


def save_config(path: Path, data: dict[str, str]) -> None:
    """Atomically save known config values with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Cached by ACT Automation. Delete this file to be re-prompted."]
    lines.extend(f"{key}={shlex.quote(data.get(key, ''))}" for key in CONFIG_KEYS)
    content = "\n".join(lines) + "\n"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        config_file = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with config_file:
            config_file.write(content)
        temporary_path.replace(path)
        path.chmod(0o600)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise

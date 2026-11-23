"""Preview façade: FabricSpec -> ACT YAML plus optional Graphviz PNG."""

from __future__ import annotations

import base64
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acta.create import FabricSpec, emit_act_yaml
from acta.diagram import topology_to_dot, write_png
from acta.web.errors import WebError

_NODE_KEY_RE = re.compile(r"^  - ([A-Za-z0-9][\w.-]*):\s*$")
_MODE_RE = re.compile(r"^# capacity: fabric_mode=(\S+)", re.MULTILINE)


@dataclass(frozen=True)
class PreviewResult:
    yaml_text: str
    png_base64: str | None
    summary: dict[str, Any]


def _count_nodes(yaml_text: str) -> int:
    count = 0
    in_nodes = False
    for line in yaml_text.splitlines():
        if not in_nodes:
            in_nodes = line.strip() == "nodes:" and not line.startswith(" ")
            continue
        if line and not line.startswith(" "):
            break
        if _NODE_KEY_RE.match(line):
            count += 1
    return count


def png_bytes_from_yaml(yaml_text: str) -> bytes | None:
    """Render ACT YAML to PNG bytes; ``None`` when Graphviz is unavailable."""
    dot_source = topology_to_dot(yaml_text)
    with tempfile.TemporaryDirectory(prefix="acta-preview-") as tmp:
        png_path = Path(tmp) / "topology.png"
        if not write_png(dot_source, png_path) or not png_path.exists():
            return None
        return png_path.read_bytes()


def preview_from_spec(spec: FabricSpec) -> PreviewResult:
    """Emit YAML for ``spec`` and render a PNG when possible."""
    try:
        yaml_text = emit_act_yaml(spec)
    except ValueError as exc:
        raise WebError(422, str(exc)) from exc
    png = png_bytes_from_yaml(yaml_text)
    mode_match = _MODE_RE.search(yaml_text)
    summary: dict[str, Any] = {
        "node_count": _count_nodes(yaml_text),
        "fabric_mode": mode_match.group(1) if mode_match else spec.capacity.fabric_mode,
        "sites": list(spec.sites),
        "title": spec.hostname_prefix,
    }
    return PreviewResult(
        yaml_text=yaml_text,
        png_base64=base64.b64encode(png).decode("ascii") if png else None,
        summary=summary,
    )


def preview_from_yaml(yaml_text: str) -> PreviewResult:
    """Render PNG (and summary) for existing ACT YAML text."""
    if not yaml_text.strip():
        raise WebError(400, "yaml_text is required")
    png = png_bytes_from_yaml(yaml_text)
    mode_match = _MODE_RE.search(yaml_text)
    summary: dict[str, Any] = {
        "node_count": _count_nodes(yaml_text),
        "fabric_mode": mode_match.group(1) if mode_match else None,
        "sites": [],
        "title": None,
    }
    return PreviewResult(
        yaml_text=yaml_text,
        png_base64=base64.b64encode(png).decode("ascii") if png else None,
        summary=summary,
    )

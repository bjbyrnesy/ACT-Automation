from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from acta.topology import parse_connections

_NODE_RE = re.compile(r"^  - (?P<name>[^:\n]+):\s*$", re.MULTILINE)


def topology_to_dot(topology_source: str) -> str:
    """Return a minimal Graphviz representation of an ACT topology."""
    nodes = [match.group("name") for match in _NODE_RE.finditer(topology_source)]
    lines = [
        "graph topology {",
        '  graph [rankdir="TB", overlap=false, splines=true];',
        '  node [shape=box, style="rounded,filled", fillcolor="#dbeafe"];',
    ]
    lines.extend(f'  "{_escape(name)}";' for name in nodes)
    lines.extend(
        f'  "{_escape(connection.a_node)}" -- ' f'"{_escape(connection.b_node)}";'
        for connection in parse_connections(topology_source)
    )
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_png(dot_source: str, png_path: Path) -> bool:
    """Render DOT source to ``png_path`` when Graphviz is available."""
    dot = shutil.which("dot")
    if dot is None:
        return False

    try:
        result = subprocess.run(
            [dot, "-Tpng", "-o", str(png_path)],
            input=dot_source,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        png_path.unlink(missing_ok=True)
        return False
    if result.returncode != 0:
        png_path.unlink(missing_ok=True)
        return False
    return True


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

"""List and store ACT topology files in a labs directory."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from acta.web.errors import WebError

_NODES_LINE = re.compile(r"(?m)^nodes\s*:")
_STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def list_topologies(root: Path) -> list[dict]:
    """Return ACT-like YAML files directly under *root*, sorted by filename."""
    if not root.is_dir():
        return []

    entries = []
    for path in sorted(root.iterdir()):
        if path.suffix not in {".yml", ".yaml"}:
            continue
        if path.name.endswith((".clab.yml", ".clab.yaml")) or not path.is_file():
            continue
        if path.is_symlink() or not _NODES_LINE.search(
            path.read_text(encoding="utf-8")
        ):
            continue
        clab_name = f"{path.stem}.clab"
        entries.append(
            {
                "name": path.name,
                "path": str(path),
                "mtime": path.stat().st_mtime,
                "has_clab_sibling": any(
                    (root / f"{clab_name}{suffix}").is_file()
                    for suffix in (".yml", ".yaml")
                ),
            }
        )
    return entries


def read_topology(root: Path, name: str) -> dict:
    """Read a YAML file by basename, refusing paths outside *root*."""
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or Path(name).suffix not in {".yml", ".yaml"}
    ):
        raise WebError(400, "Invalid topology name")

    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise WebError(400, "Invalid topology name")
    if not path.is_file():
        raise WebError(404, "Topology not found")
    return {"yaml_text": path.read_text(encoding="utf-8"), "path": str(path)}


def write_topology(root: Path, yaml_text: str, *, stem: str | None = None) -> Path:
    """Write a dated YAML file without overwriting an existing topology."""
    chosen_stem = "topology" if stem is None else stem
    if not _STEM.fullmatch(chosen_stem):
        raise WebError(400, "Invalid topology stem")

    root.mkdir(parents=True, exist_ok=True)
    dated_stem = f"{chosen_stem}-{date.today().isoformat()}"
    suffix = 1
    while True:
        filename = f"{dated_stem}{f'-{suffix}' if suffix > 1 else ''}.yml"
        path = root / filename
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(yaml_text)
            return path
        except FileExistsError:
            suffix += 1

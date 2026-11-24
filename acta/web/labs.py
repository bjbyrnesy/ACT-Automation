"""List and store ACT topology files in a labs directory."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from acta.web.errors import WebError

_NODES_LINE = re.compile(r"(?m)^nodes\s*:")
_STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
# ``{lab}-{YYYY-MM-DD}.yml`` or ``{lab}-{YYYY-MM-DD}-{n}.yml``; else whole stem is lab id.
_VERSIONED = re.compile(r"^(?P<lab>.+)-(?P<date>\d{4}-\d{2}-\d{2})(?:-(?P<rev>\d+))?$")


def lab_id_from_filename(name: str) -> str:
    """Return the lab id (filename stem before an optional dated suffix)."""
    stem = Path(name).stem
    match = _VERSIONED.fullmatch(stem)
    if match is None:
        return stem
    return match.group("lab")


def _is_act_topology(path: Path) -> bool:
    if path.suffix not in {".yml", ".yaml"}:
        return False
    if path.name.endswith((".clab.yml", ".clab.yaml")) or not path.is_file():
        return False
    if path.is_symlink():
        return False
    return bool(_NODES_LINE.search(path.read_text(encoding="utf-8")))


def _entry(path: Path, *, root: Path) -> dict:
    clab_stem = f"{path.stem}.clab"
    return {
        "name": path.name,
        "path": str(path),
        "lab_id": lab_id_from_filename(path.name),
        "mtime": path.stat().st_mtime,
        "has_clab_sibling": any(
            (root / f"{clab_stem}{suffix}").is_file() for suffix in (".yml", ".yaml")
        ),
    }


def list_topologies(root: Path) -> list[dict]:
    """Return ACT-like YAML files directly under *root*, sorted by filename."""
    if not root.is_dir():
        return []

    entries = []
    for path in sorted(root.iterdir()):
        if not _is_act_topology(path):
            continue
        entries.append(_entry(path, root=root))
    return entries


def list_labs(root: Path) -> list[dict]:
    """Group ACT topologies by lab id (filename stem before date)."""
    groups: dict[str, list[dict]] = {}
    for entry in list_topologies(root):
        groups.setdefault(entry["lab_id"], []).append(entry)

    labs: list[dict] = []
    for lab_id, versions in sorted(groups.items()):
        versions_sorted = sorted(versions, key=lambda item: item["mtime"], reverse=True)
        latest = versions_sorted[0]
        labs.append(
            {
                "id": lab_id,
                "version_count": len(versions_sorted),
                "latest": latest,
                "versions": versions_sorted,
            }
        )
    return labs


def get_lab(root: Path, lab_id: str) -> dict:
    """Return one lab with its versions, or 404."""
    if not lab_id or not _STEM.fullmatch(lab_id):
        raise WebError(400, "Invalid lab id")
    for lab in list_labs(root):
        if lab["id"] == lab_id:
            return lab
    raise WebError(404, "Lab not found")


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
    if path.is_symlink():
        raise WebError(400, "Invalid topology name")
    if not path.is_file():
        raise WebError(404, "Topology not found")
    yaml_text = path.read_text(encoding="utf-8")
    # Prefer sibling .clab.yml / live inspect over ACT's placeholder 192.168.0.0/24.
    from acta.show_topo import collect_mgmt_ips

    return {
        "yaml_text": yaml_text,
        "path": str(path),
        "name": path.name,
        "lab_id": lab_id_from_filename(path.name),
        "mgmt_ips": collect_mgmt_ips(path, yaml_text),
    }


def delete_topology(root: Path, name: str) -> None:
    """Delete one ACT topology file by basename."""
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
    if path.is_symlink() or not path.is_file():
        raise WebError(404, "Topology not found")
    if not _is_act_topology(path):
        raise WebError(400, "Not an ACT topology file")
    path.unlink()


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

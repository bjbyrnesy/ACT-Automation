from __future__ import annotations

import os
import re
import tempfile
import warnings
from dataclasses import replace
from datetime import date
from pathlib import Path

from acta.capacity import Capacity, format_capacity_header, parse_capacity_header
from acta.mac import generate_mac
from acta.portplan import PortPlan
from acta.topology import Connection, parse_connections, used_ports_from_connections

_CAPACITY_LINE_RE = re.compile(r"^#\s*capacity:.*$", re.MULTILINE)
_NODE_RE = re.compile(r"^  - (?P<name>[^:\n]+):\s*$", re.MULTILINE)
_FABRIC_NODE_RE = re.compile(
    r"^(?P<prefix>.+)-(?P<role>spine|leaf)(?P<index>[1-9]\d*)$"
)
_SERIAL_RE = re.compile(
    r"^[ \t]+serial_number:\s*(?P<prefix>\S+)-(?:spine|leaf)[1-9]\d*\s*$",
    re.MULTILINE,
)
_LINKS_RE = re.compile(r"^links:\s*$", re.MULTILINE)
_DATA_PLANE_RE = re.compile(r"^#{10,}\n# Data-plane links\n#{10,}\n", re.MULTILINE)


def _fabric_nodes(text: str, role: str) -> list[tuple[int, str, str]]:
    nodes: list[tuple[int, str, str]] = []
    for node_match in _NODE_RE.finditer(text):
        name = node_match.group("name")
        identity_match = _FABRIC_NODE_RE.fullmatch(name)
        if identity_match is None or identity_match.group("role") != role:
            continue
        nodes.append(
            (
                int(identity_match.group("index")),
                name,
                identity_match.group("prefix"),
            )
        )
    return sorted(nodes)


def _replace_capacity(text: str, capacity: Capacity) -> str:
    lines = text.splitlines()
    capacity_indexes = {
        index
        for index, line in enumerate(lines)
        if _CAPACITY_LINE_RE.fullmatch(line) is not None
    }
    if not capacity_indexes:
        raise ValueError("missing # capacity: header")

    first = min(capacity_indexes)
    replacement = format_capacity_header(capacity).splitlines()
    updated: list[str] = []
    for index, line in enumerate(lines):
        if index == first:
            updated.extend(replacement)
        if index not in capacity_indexes:
            updated.append(line)
    return "\n".join(updated) + "\n"


def _node_yaml(
    hostname_prefix: str,
    serial_prefix: str,
    leaf_index: int,
) -> str:
    identity = f"leaf{leaf_index}"
    return "\n".join(
        [
            f"  - {hostname_prefix}-{identity}:",
            "      node_type: veos",
            f"      ip_addr: 192.168.0.{20 + leaf_index}/24",
            f"      serial_number: {serial_prefix}-{identity}",
            f"      system_mac_address: {generate_mac(serial_prefix, identity)}",
            "      ztp: false",
        ]
    )


def _insert_node(text: str, node_yaml: str) -> str:
    marker = _DATA_PLANE_RE.search(text) or _LINKS_RE.search(text)
    if marker is None:
        raise ValueError("topology is missing a links section")
    return (
        f"{text[: marker.start()].rstrip()}\n\n{node_yaml}\n\n{text[marker.start():]}"
    )


def _connection_line(connection: Connection) -> str:
    return (
        f"  - connection: [{connection.a_node}:Ethernet{connection.a_port}, "
        f"{connection.b_node}:Ethernet{connection.b_port}]"
    )


def _append_connections(text: str, connections: list[Connection]) -> str:
    lines = [_connection_line(connection) for connection in connections]
    return f"{text.rstrip()}\n" + "\n".join(lines) + "\n"


def _new_output_path(path: Path) -> Path:
    suffix = path.suffix or ".yml"
    base = path.with_name(f"{path.stem}-{date.today().isoformat()}{suffix}")
    candidate = base
    sequence = 2
    while candidate.exists():
        candidate = base.with_stem(f"{base.stem}-{sequence}")
        sequence += 1
    return candidate


def _write_atomic(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.chmod(mode)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _resolve_output(path: Path, out: Path | None, new: bool) -> Path:
    if out is not None and new:
        raise ValueError("out and new are mutually exclusive")
    if out is not None:
        if out.exists():
            raise FileExistsError(f"output path already exists: {out}")
        return out
    if new:
        return _new_output_path(path)
    return path


def extend_topology(
    path: Path,
    add: str,
    *,
    site: str | None = None,
    pair: int | None = None,
    count: int = 1,
    out: Path | None = None,
    new: bool = False,
) -> Path:
    """Extend an ACT topology without changing existing link endpoints."""
    del site, pair
    if add != "leaf":
        raise NotImplementedError(f"extending with {add!r} is not implemented")
    if count < 1:
        raise ValueError("count must be at least 1")

    text = path.read_text(encoding="utf-8")
    capacity = parse_capacity_header(text)
    original_connections = parse_connections(text)
    spines = _fabric_nodes(text, "spine")
    leaves = _fabric_nodes(text, "leaf")
    if not spines:
        raise ValueError("topology has no spine nodes")
    hostname_prefixes = {prefix for _, _, prefix in [*spines, *leaves]}
    if len(hostname_prefixes) != 1:
        raise ValueError("topology fabric node prefixes are inconsistent")
    serial_match = _SERIAL_RE.search(text)
    if serial_match is None:
        raise ValueError("topology has no recognizable fabric serial number")

    hostname_prefix = hostname_prefixes.pop()
    serial_prefix = serial_match.group("prefix")
    next_leaf = max([capacity.leaves, *(index for index, _, _ in leaves)]) + 1
    plan = PortPlan(capacity)
    connections = list(original_connections)
    updated_text = text

    for leaf_index in range(next_leaf, next_leaf + count):
        leaf_name = f"{hostname_prefix}-leaf{leaf_index}"
        new_connections: list[Connection] = []
        leaf_used: set[int] = set()
        for spine_index, spine_name, _ in spines:
            preferred_spine_port = plan.spine_to_leaf_port(leaf_index)
            spine_used = used_ports_from_connections(connections, spine_name)
            spine_port = plan.next_free_port(spine_used, preferred_spine_port)
            leaf_port = plan.next_free_port(
                leaf_used,
                plan.leaf_to_spine_port(spine_index),
            )
            if spine_port != preferred_spine_port:
                warnings.warn(
                    f"{spine_name}:Ethernet{preferred_spine_port} is unavailable; "
                    f"using Ethernet{spine_port}",
                    stacklevel=2,
                )
            new_connections.append(
                Connection(spine_name, spine_port, leaf_name, leaf_port)
            )
            leaf_used.add(leaf_port)
        updated_text = _insert_node(
            updated_text,
            _node_yaml(hostname_prefix, serial_prefix, leaf_index),
        )
        updated_text = _append_connections(updated_text, new_connections)
        connections.extend(new_connections)

    updated_capacity = replace(capacity, leaves=capacity.leaves + count)
    updated_text = _replace_capacity(updated_text, updated_capacity)
    before = {
        (connection.a_node, connection.a_port, connection.b_node, connection.b_port)
        for connection in original_connections
    }
    after = {
        (connection.a_node, connection.a_port, connection.b_node, connection.b_port)
        for connection in parse_connections(updated_text)
    }
    if not before <= after:
        raise RuntimeError("extend would change existing connection endpoints")

    output_path = _resolve_output(path, out, new)
    _write_atomic(output_path, updated_text, path.stat().st_mode & 0o777)
    return output_path

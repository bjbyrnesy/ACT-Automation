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
    r"^(?P<prefix>.+)-(?P<role>spine|leaf|mleaf)(?P<index>[1-9]\d*)$"
)
_SERIAL_RE = re.compile(
    r"^[ \t]+serial_number:\s*(?P<prefix>\S+)-(?:spine|leaf|mleaf)[1-9]\d*\s*$",
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
    role: str,
    index: int,
) -> str:
    address_base = {"spine": 10, "leaf": 20, "mleaf": 130}[role]
    identity = f"{role}{index}"
    return "\n".join(
        [
            f"  - {hostname_prefix}-{identity}:",
            "      node_type: veos",
            f"      ip_addr: 192.168.0.{address_base + index}/24",
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


def _warn_soft_capacity(identity: str, field: str, maximum: int) -> None:
    warnings.warn(
        f"{identity} exceeds planned soft capacity {field}={maximum}; "
        "continuing with available ports",
        stacklevel=3,
    )


def _allocate_port(
    plan: PortPlan,
    used: set[int],
    preferred: int,
    node: str,
) -> int:
    port = plan.next_free_port(used, preferred)
    if port != preferred:
        warnings.warn(
            f"{node}:Ethernet{preferred} is unavailable; using Ethernet{port}",
            stacklevel=3,
        )
    return port


def _leaf_mesh_connections(
    plan: PortPlan,
    connections: list[Connection],
    spines: list[tuple[int, str, str]],
    leaf_name: str,
    leaf_index: int,
) -> list[Connection]:
    new_connections: list[Connection] = []
    leaf_used: set[int] = set()
    for spine_index, spine_name, _ in spines:
        spine_port = _allocate_port(
            plan,
            used_ports_from_connections(connections, spine_name),
            plan.spine_to_leaf_port(leaf_index),
            spine_name,
        )
        leaf_port = _allocate_port(
            plan,
            leaf_used,
            plan.leaf_to_spine_port(spine_index),
            leaf_name,
        )
        new_connections.append(Connection(spine_name, spine_port, leaf_name, leaf_port))
        leaf_used.add(leaf_port)
        connections.append(new_connections[-1])
    return new_connections


def _spine_mesh_connections(
    plan: PortPlan,
    connections: list[Connection],
    leaves: list[tuple[int, str, str]],
    spine_name: str,
    spine_index: int,
) -> list[Connection]:
    new_connections: list[Connection] = []
    spine_used: set[int] = set()
    for leaf_index, leaf_name, _ in leaves:
        spine_port = _allocate_port(
            plan,
            spine_used,
            plan.spine_to_leaf_port(leaf_index),
            spine_name,
        )
        leaf_port = _allocate_port(
            plan,
            used_ports_from_connections(connections, leaf_name),
            plan.leaf_to_spine_port(spine_index),
            leaf_name,
        )
        new_connections.append(Connection(spine_name, spine_port, leaf_name, leaf_port))
        spine_used.add(spine_port)
        connections.append(new_connections[-1])
    return new_connections


def _mleafs_for_pair(
    connections: list[Connection],
    odd_leaf_name: str,
    even_leaf_name: str,
) -> set[str]:
    pair_leaves = {odd_leaf_name, even_leaf_name}
    member_leaves: set[str] = set()
    for connection in connections:
        endpoints = {connection.a_node, connection.b_node}
        for endpoint in endpoints:
            if "-mleaf" in endpoint and endpoints & pair_leaves:
                member_leaves.add(endpoint)
    return member_leaves


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
    del site
    if add not in {"leaf", "spine", "pair", "mleaf"}:
        raise ValueError(f"unsupported extension type: {add!r}")
    if count < 1:
        raise ValueError("count must be at least 1")
    if add == "mleaf" and pair is None:
        raise ValueError("mleaf extension requires pair")
    if pair is not None and pair < 1:
        raise ValueError("pair must be at least 1")

    text = path.read_text(encoding="utf-8")
    capacity = parse_capacity_header(text)
    original_connections = parse_connections(text)
    spines = _fabric_nodes(text, "spine")
    leaves = _fabric_nodes(text, "leaf")
    mleafs = _fabric_nodes(text, "mleaf")
    if not spines:
        raise ValueError("topology has no spine nodes")
    hostname_prefixes = {prefix for _, _, prefix in [*spines, *leaves, *mleafs]}
    if len(hostname_prefixes) != 1:
        raise ValueError("topology fabric node prefixes are inconsistent")
    serial_match = _SERIAL_RE.search(text)
    if serial_match is None:
        raise ValueError("topology has no recognizable fabric serial number")

    hostname_prefix = hostname_prefixes.pop()
    serial_prefix = serial_match.group("prefix")
    plan = PortPlan(capacity)
    connections = list(original_connections)
    updated_text = text
    leaves_added = 0
    spines_added = 0

    if add in {"leaf", "pair"}:
        leaves_to_add = count if add == "leaf" else count * 2
        next_leaf = max([capacity.leaves, *(item[0] for item in leaves)]) + 1
        added_leaf_names: list[str] = []
        for leaf_index in range(next_leaf, next_leaf + leaves_to_add):
            if leaf_index > capacity.max_leaves:
                _warn_soft_capacity(
                    f"leaf{leaf_index}", "max_leaves", capacity.max_leaves
                )
            leaf_name = f"{hostname_prefix}-leaf{leaf_index}"
            new_connections = _leaf_mesh_connections(
                plan,
                connections,
                spines,
                leaf_name,
                leaf_index,
            )
            updated_text = _insert_node(
                updated_text,
                _node_yaml(hostname_prefix, serial_prefix, "leaf", leaf_index),
            )
            updated_text = _append_connections(updated_text, new_connections)
            added_leaf_names.append(leaf_name)
            leaves_added += 1

        if add == "pair":
            mlag_ports = plan.leaf_mlag_ports()
            for pair_offset in range(0, len(added_leaf_names), 2):
                odd_name, even_name = added_leaf_names[pair_offset : pair_offset + 2]
                peer_connections: list[Connection] = []
                for preferred in mlag_ports:
                    odd_port = _allocate_port(
                        plan,
                        used_ports_from_connections(connections, odd_name),
                        preferred,
                        odd_name,
                    )
                    even_port = _allocate_port(
                        plan,
                        used_ports_from_connections(connections, even_name),
                        preferred,
                        even_name,
                    )
                    connection = Connection(
                        odd_name,
                        odd_port,
                        even_name,
                        even_port,
                    )
                    peer_connections.append(connection)
                    connections.append(connection)
                updated_text = _append_connections(updated_text, peer_connections)

    elif add == "spine":
        if capacity.fabric_mode == "l2" and capacity.spines >= 2:
            raise ValueError("L2 fabrics cannot have more than 2 spines")
        next_spine = max([capacity.spines, *(item[0] for item in spines)]) + 1
        if capacity.fabric_mode == "l2" and next_spine + count - 1 > 2:
            raise ValueError("L2 fabrics cannot have more than 2 spines")
        for spine_index in range(next_spine, next_spine + count):
            if spine_index > capacity.max_spines:
                _warn_soft_capacity(
                    f"spine{spine_index}", "max_spines", capacity.max_spines
                )
            spine_name = f"{hostname_prefix}-spine{spine_index}"
            new_connections = _spine_mesh_connections(
                plan,
                connections,
                leaves,
                spine_name,
                spine_index,
            )
            updated_text = _insert_node(
                updated_text,
                _node_yaml(hostname_prefix, serial_prefix, "spine", spine_index),
            )
            updated_text = _append_connections(updated_text, new_connections)
            spines_added += 1

    else:
        assert pair is not None
        odd_leaf_index = pair * 2 - 1
        even_leaf_index = pair * 2
        leaf_names = {index: name for index, name, _ in leaves}
        if odd_leaf_index not in leaf_names or even_leaf_index not in leaf_names:
            raise ValueError(f"leaf pair {pair} does not exist")
        odd_name = leaf_names[odd_leaf_index]
        even_name = leaf_names[even_leaf_index]
        next_slot = len(_mleafs_for_pair(connections, odd_name, even_name)) + 1
        next_mleaf = max([0, *(item[0] for item in mleafs)]) + 1
        for offset in range(count):
            slot = next_slot + offset
            if slot > capacity.max_mleafs_per_pair:
                _warn_soft_capacity(
                    f"mleaf slot {slot}",
                    "max_mleafs_per_pair",
                    capacity.max_mleafs_per_pair,
                )
            mleaf_index = next_mleaf + offset
            mleaf_name = f"{hostname_prefix}-mleaf{mleaf_index}"
            preferred_leaf_port = plan.leaf_mleaf_port(slot)
            odd_port = _allocate_port(
                plan,
                used_ports_from_connections(connections, odd_name),
                preferred_leaf_port,
                odd_name,
            )
            even_port = _allocate_port(
                plan,
                used_ports_from_connections(connections, even_name),
                preferred_leaf_port,
                even_name,
            )
            mleaf_connections = [
                Connection(mleaf_name, 1, odd_name, odd_port),
                Connection(mleaf_name, 2, even_name, even_port),
            ]
            updated_text = _insert_node(
                updated_text,
                _node_yaml(hostname_prefix, serial_prefix, "mleaf", mleaf_index),
            )
            updated_text = _append_connections(updated_text, mleaf_connections)
            connections.extend(mleaf_connections)

    updated_capacity = replace(
        capacity,
        leaves=capacity.leaves + leaves_added,
        spines=capacity.spines + spines_added,
    )
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

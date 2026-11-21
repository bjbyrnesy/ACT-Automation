from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from acta.capacity import Capacity, format_capacity_header, parse_capacity_header
from acta.create import node_block
from acta.diagram import topology_to_dot, write_png
from acta.portplan import PortPlan, persisted_site_ordinal
from acta.topology import Connection, parse_connections, used_ports_from_connections

_CAPACITY_LINE_RE = re.compile(r"^#\s*capacity:.*$", re.MULTILINE)
_NODE_RE = re.compile(r"^  - (?P<name>[^:\n]+):\s*$", re.MULTILINE)
_FABRIC_NODE_RE = re.compile(
    r"^(?P<prefix>.+)-(?P<role>spine|leaf|mleaf)(?P<index>[1-9]\d*)$"
)
_BB_NODE_RE = re.compile(r"^(?P<prefix>.+)-bb1$")
_MLEAF_NAME_RE = re.compile(r"(?:^|-)mleaf[1-9]\d*$")
_BB_SERIAL_RE = re.compile(
    r"^[ \t]+serial_number:\s*(?P<prefix>\S+)-bb1\s*$",
    re.MULTILINE,
)
_SERIAL_RE = re.compile(
    r"^[ \t]+serial_number:\s*(?P<prefix>\S+)-(?:spine|leaf|mleaf)[1-9]\d*\s*$",
    re.MULTILINE,
)
_DATED_STEM_RE = re.compile(r"-\d{4}-\d{2}-\d{2}(?:-\d+)?$")
_LINKS_RE = re.compile(r"^links:\s*$", re.MULTILINE)
_DATA_PLANE_RE = re.compile(r"^#{10,}\n# Data-plane links\n#{10,}\n", re.MULTILINE)


def _multi_dc_prefix(text: str) -> str | None:
    """Return the hostname prefix when the topology has a backbone (multi-DC)."""
    for node_match in _NODE_RE.finditer(text):
        bb_match = _BB_NODE_RE.fullmatch(node_match.group("name"))
        if bb_match is not None:
            return bb_match.group("prefix")
    return None


def _sites(text: str, hostname_prefix: str) -> list[str]:
    site_re = re.compile(
        rf"^{re.escape(hostname_prefix)}-(?P<site>[A-Za-z0-9][A-Za-z0-9_-]*)-"
        r"(?:border|spine|leaf|mleaf)[1-9]\d*$"
    )
    found = {
        match.group("site")
        for node_match in _NODE_RE.finditer(text)
        if (match := site_re.fullmatch(node_match.group("name"))) is not None
    }
    return sorted(found)


def _fabric_nodes(
    text: str,
    role: str,
    *,
    hostname_prefix: str | None = None,
    site: str | None = None,
) -> list[tuple[int, str, str]]:
    """List ``(index, name, prefix)``; multi-DC passes prefix and site to scope."""
    nodes: list[tuple[int, str, str]] = []
    scoped_re = (
        re.compile(rf"^{re.escape(hostname_prefix)}-{site}-{role}(?P<index>[1-9]\d*)$")
        if hostname_prefix is not None and site is not None
        else None
    )
    for node_match in _NODE_RE.finditer(text):
        name = node_match.group("name")
        if scoped_re is not None:
            scoped_match = scoped_re.fullmatch(name)
            if scoped_match is not None:
                nodes.append((int(scoped_match.group("index")), name, hostname_prefix))
            continue
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
    site: str | None = None,
    site_index: int | None = None,
) -> str:
    return "\n".join(
        node_block(
            hostname_prefix, serial_prefix, role, index, site, site_index=site_index
        )
    )


def _insert_node(text: str, node_yaml: str) -> str:
    marker = _DATA_PLANE_RE.search(text) or _LINKS_RE.search(text)
    if marker is None:
        raise ValueError("topology is missing a links section")
    return (
        f"{text[: marker.start()].rstrip()}\n\n{node_yaml}\n\n{text[marker.start() :]}"
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
    stem = _DATED_STEM_RE.sub("", path.stem)
    base = path.with_name(f"{stem}-{date.today().isoformat()}{suffix}")
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


def _warn_soft_capacity(
    warnings: list[str], identity: str, field: str, maximum: int
) -> None:
    warnings.append(
        f"{identity} exceeds planned soft capacity {field}={maximum}; "
        "continuing with available ports"
    )


@dataclass(frozen=True)
class _PortRule:
    """Reserved-block geometry for the node role that owns a port."""

    reserved_top: int
    protected: frozenset[int]


def _leaf_rule(plan: PortPlan) -> _PortRule:
    return _PortRule(plan.leaf_reserved_top(), plan.leaf_protected_ports())


def _spine_rule(plan: PortPlan, multi_dc: bool) -> _PortRule:
    return _PortRule(
        plan.spine_reserved_top(multi_dc), plan.spine_protected_ports(multi_dc)
    )


def _allocate_port(
    plan: PortPlan,
    used: set[int],
    preferred: int,
    node: str,
    warnings: list[str],
    rule: _PortRule,
    *,
    overrun: bool = False,
) -> int:
    """Allocate a port; overrun (past soft max) goes above reserved blocks."""
    port = plan.allocate_port(
        used,
        preferred,
        reserved_top=rule.reserved_top,
        protected=rule.protected,
        overrun=overrun,
    )
    if port != preferred and not overrun:
        warnings.append(
            f"{node}:Ethernet{preferred} is unavailable; using Ethernet{port}"
        )
    return port


def _leaf_mesh_connections(
    plan: PortPlan,
    connections: list[Connection],
    spines: list[tuple[int, str, str]],
    leaf_name: str,
    leaf_index: int,
    warnings: list[str],
    multi_dc: bool,
) -> list[Connection]:
    """Mesh a new leaf; MLAG and member-leaf slot ports are never taken."""
    new_connections: list[Connection] = []
    leaf_used: set[int] = set()
    leaf_rule = _leaf_rule(plan)
    spine_rule = _spine_rule(plan, multi_dc)
    for spine_index, spine_name, _ in spines:
        spine_port = _allocate_port(
            plan,
            used_ports_from_connections(connections, spine_name),
            plan.spine_to_leaf_port(leaf_index),
            spine_name,
            warnings,
            spine_rule,
            overrun=leaf_index > plan.capacity.max_leaves,
        )
        leaf_port = _allocate_port(
            plan,
            leaf_used,
            plan.leaf_to_spine_port(spine_index),
            leaf_name,
            warnings,
            leaf_rule,
            overrun=spine_index > plan.capacity.max_spines,
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
    warnings: list[str],
    multi_dc: bool,
) -> list[Connection]:
    """Mesh a new spine; spine MLAG/uplink and leaf service ports stay free."""
    new_connections: list[Connection] = []
    spine_used: set[int] = set()
    leaf_rule = _leaf_rule(plan)
    spine_rule = _spine_rule(plan, multi_dc)
    for leaf_index, leaf_name, _ in leaves:
        spine_port = _allocate_port(
            plan,
            spine_used,
            plan.spine_to_leaf_port(leaf_index),
            spine_name,
            warnings,
            spine_rule,
            overrun=leaf_index > plan.capacity.max_leaves,
        )
        leaf_port = _allocate_port(
            plan,
            used_ports_from_connections(connections, leaf_name),
            plan.leaf_to_spine_port(spine_index),
            leaf_name,
            warnings,
            leaf_rule,
            overrun=spine_index > plan.capacity.max_spines,
        )
        new_connections.append(Connection(spine_name, spine_port, leaf_name, leaf_port))
        spine_used.add(spine_port)
        connections.append(new_connections[-1])
    return new_connections


def _spine_uplink_connections(
    plan: PortPlan,
    connections: list[Connection],
    stem: str,
    site: str,
    site_index: int,
    spine_name: str,
    spine_index: int,
    warnings: list[str],
) -> list[Connection]:
    """Link a new multi-DC spine to its site's borders (l3ls) or the bbs (l2)."""
    hostname_prefix = stem.removesuffix(f"-{site}")
    spine_rule = _spine_rule(plan, True)
    overrun = spine_index > plan.capacity.max_spines
    new_connections: list[Connection] = []
    for peer_number, spine_port_preferred in enumerate(
        plan.spine_uplink_ports(), start=1
    ):
        if plan.capacity.fabric_mode == "l3ls":
            peer_name = f"{stem}-border{peer_number}"
            peer_preferred = plan.border_to_spine_port(spine_index)
            peer_rule = _PortRule(
                plan.border_reserved_top(), plan.border_protected_ports()
            )
        else:
            peer_name = f"{hostname_prefix}-bb{peer_number}"
            peer_preferred = plan.bb_spine_port(site_index, spine_index)
            edge_top = plan.bb_edge_width() * plan.max_attach_sites()
            if (
                plan.capacity.bb_redundancy == "mlag-peer"
                and plan.capacity.bb_count >= 2
            ):
                peer_port = plan.bb_peer_port()
                peer_rule = _PortRule(peer_port, frozenset((peer_port,)))
            else:
                peer_rule = _PortRule(edge_top, frozenset())
        spine_port = _allocate_port(
            plan,
            used_ports_from_connections(connections, spine_name),
            spine_port_preferred,
            spine_name,
            warnings,
            spine_rule,
        )
        peer_port = _allocate_port(
            plan,
            used_ports_from_connections(connections, peer_name),
            peer_preferred,
            peer_name,
            warnings,
            peer_rule,
            overrun=overrun,
        )
        new_connections.append(Connection(peer_name, peer_port, spine_name, spine_port))
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
            if _MLEAF_NAME_RE.search(endpoint) and endpoints & pair_leaves:
                member_leaves.add(endpoint)
    return member_leaves


def _leaf_pairs(
    connections: list[Connection],
    leaves: list[tuple[int, str, str]],
) -> list[tuple[tuple[int, str], tuple[int, str]]]:
    """Leaf pairs joined by two or more leaf-to-leaf (MLAG peer) links.

    Port numbers are ignored so pairs stay discoverable even if an overrun or
    displaced allocation moved a peer link off its planned MLAG ports.
    """
    leaf_indexes = {name: index for index, name, _ in leaves}
    peer_links: dict[frozenset[str], int] = {}
    for connection in connections:
        if connection.a_node not in leaf_indexes:
            continue
        if connection.b_node not in leaf_indexes:
            continue
        key = frozenset((connection.a_node, connection.b_node))
        if len(key) == 2:
            peer_links[key] = peer_links.get(key, 0) + 1

    pairs: list[tuple[tuple[int, str], tuple[int, str]]] = []
    for names, link_count in peer_links.items():
        if link_count < 2:
            continue
        members = sorted((leaf_indexes[name], name) for name in names)
        pairs.append((members[0], members[1]))
    return sorted(pairs, key=lambda members: members[0][0])


def leaf_mlag_pairs(
    text: str,
    *,
    site: str | None = None,
) -> list[tuple[str, str]]:
    """Return discovered MLAG leaf pairs as ``(leaf_a, leaf_b)`` (1-based index order).

    Same ordering as ``extend --pair N`` (sorted by lowest leaf index).
    """
    multi_prefix = _multi_dc_prefix(text)
    if multi_prefix is not None and site is None:
        # All sites: collect pairs per site in letter order.
        pairs: list[tuple[str, str]] = []
        for letter in _sites(text, multi_prefix):
            leaves = _fabric_nodes(
                text, "leaf", hostname_prefix=multi_prefix, site=letter
            )
            connections = parse_connections(text)
            for odd, even in _leaf_pairs(connections, leaves):
                pairs.append((odd[1], even[1]))
        return pairs
    prefix = multi_prefix if site is not None else None
    leaves = _fabric_nodes(text, "leaf", hostname_prefix=prefix, site=site)
    connections = parse_connections(text)
    return [(odd[1], even[1]) for odd, even in _leaf_pairs(connections, leaves)]


def member_leaves(text: str, *, site: str | None = None) -> list[str]:
    """Return discovered member-leaf hostnames in 1-based ``--mleaf`` order.

    Multi-DC: site letter order, then mleaf index within each site. Single-DC:
    sorted by mleaf index.
    """
    multi_prefix = _multi_dc_prefix(text)
    if multi_prefix is not None and site is None:
        names: list[str] = []
        for letter in _sites(text, multi_prefix):
            names.extend(
                name
                for _, name, _ in _fabric_nodes(
                    text, "mleaf", hostname_prefix=multi_prefix, site=letter
                )
            )
        return names
    prefix = multi_prefix if site is not None else None
    return [
        name
        for _, name, _ in _fabric_nodes(
            text, "mleaf", hostname_prefix=prefix, site=site
        )
    ]


def member_leaf_parents(
    text: str, mleaf: str
) -> tuple[int | None, tuple[str, str] | None]:
    """Return ``(mlag_pair_index, (leaf_a, leaf_b))`` for a member-leaf, if known."""
    connections = parse_connections(text)
    for index, (leaf_a, leaf_b) in enumerate(leaf_mlag_pairs(text), start=1):
        if mleaf in _mleafs_for_pair(connections, leaf_a, leaf_b):
            return index, (leaf_a, leaf_b)
    return None, None


@dataclass(frozen=True)
class ExtendResult:
    """Outcome of an extend, for user-facing reporting (no warnings.warn)."""

    path: Path
    added_nodes: tuple[str, ...]
    warnings: tuple[str, ...]
    free_leaves: int
    free_spines: int
    free_mleaf_slots: tuple[int, ...]

    def free_slots_summary(self) -> str:
        """One-line summary of planned capacity still unused."""
        slots = ", ".join(
            f"pair {number}: {free}"
            for number, free in enumerate(self.free_mleaf_slots, start=1)
        )
        return (
            f"Remaining planned slots: leaves {self.free_leaves}, "
            f"spines {self.free_spines}, member leaves per pair "
            f"{slots or 'no pairs'}"
        )


_IP_ADDR_RE = re.compile(r"^[ \t]+ip_addr:\s*(?P<address>\S+)\s*$", re.MULTILINE)


def _assert_unique_addresses(text: str) -> None:
    """Refuse to write a topology that reuses a management IP."""
    seen: set[str] = set()
    for match in _IP_ADDR_RE.finditer(text):
        address = match.group("address")
        if address in seen:
            raise ValueError(f"extend would duplicate management address {address}")
        seen.add(address)


def topology_sites(path: Path) -> list[str]:
    """Return site letters for a multi-DC topology, or ``[]`` for single-site."""
    text = path.read_text(encoding="utf-8")
    prefix = _multi_dc_prefix(text)
    return [] if prefix is None else _sites(text, prefix)


def _remaining_slots(
    text: str,
    capacity: Capacity,
    site: str | None,
    multi_prefix: str | None,
) -> tuple[int, int, tuple[int, ...]]:
    """Unused planned leaves, spines, and member-leaf slots per leaf pair."""
    prefix = multi_prefix if site is not None else None
    leaves = _fabric_nodes(text, "leaf", hostname_prefix=prefix, site=site)
    spines = _fabric_nodes(text, "spine", hostname_prefix=prefix, site=site)
    connections = parse_connections(text)
    free_slots = tuple(
        max(
            0,
            capacity.max_mleafs_per_pair
            - len(_mleafs_for_pair(connections, odd[1], even[1])),
        )
        for odd, even in _leaf_pairs(connections, leaves)
    )
    return (
        max(0, capacity.max_leaves - len(leaves)),
        max(0, capacity.max_spines - len(spines)),
        free_slots,
    )


def extend_topology(
    path: Path,
    add: str,
    *,
    site: str | None = None,
    pair: int | None = None,
    count: int = 1,
    out: Path | None = None,
    new: bool = False,
) -> ExtendResult:
    """Extend an ACT topology without changing existing link endpoints.

    Returns an :class:`ExtendResult` with the written path, added node names,
    soft-capacity warnings, and remaining planned slots. Nothing is written
    when any step fails (all validation precedes the atomic write).

    Multi-DC topologies (backbone present) require ``site``; every operation
    then touches only that site's nodes and its own border/backbone ports.
    """
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
    multi_prefix = _multi_dc_prefix(text)
    site_name: str | None = None
    site_index: int | None = None
    if multi_prefix is None:
        if site is not None:
            raise ValueError(
                "--site is only valid for multi-DC topologies, not single-site"
            )
        spines = _fabric_nodes(text, "spine")
        leaves = _fabric_nodes(text, "leaf")
        mleafs = _fabric_nodes(text, "mleaf")
        serial_match = _SERIAL_RE.search(text)
    else:
        available = _sites(text, multi_prefix)
        if site is None:
            raise ValueError(
                f"multi-DC topology requires --site (available: {', '.join(available)})"
            )
        available_map = {name.casefold(): name for name in available}
        if site.casefold() not in available_map:
            raise ValueError(
                f"site {site} not found (available: {', '.join(available)})"
            )
        site_name = available_map[site.casefold()]
        site_index = persisted_site_ordinal(text, multi_prefix, site_name)
        scope = {"hostname_prefix": multi_prefix, "site": site_name}
        spines = _fabric_nodes(text, "spine", **scope)
        leaves = _fabric_nodes(text, "leaf", **scope)
        mleafs = _fabric_nodes(text, "mleaf", **scope)
        serial_match = _BB_SERIAL_RE.search(text)
    if not spines:
        raise ValueError("topology has no spine nodes")
    hostname_prefixes = {prefix for _, _, prefix in [*spines, *leaves, *mleafs]}
    if len(hostname_prefixes) != 1:
        raise ValueError("topology fabric node prefixes are inconsistent")
    if serial_match is None:
        raise ValueError("topology has no recognizable fabric serial number")

    hostname_prefix = hostname_prefixes.pop()
    serial_prefix = serial_match.group("prefix")
    # Node-name stem including site, e.g. "demo-B" (multi-DC) or "demo".
    stem = hostname_prefix if site_name is None else f"{hostname_prefix}-{site_name}"
    # Header counts are per-fabric in single-DC; multi-DC sites diverge, so
    # indices come from the site's nodes and the header stays the create baseline.
    base_leaves = capacity.leaves if site_name is None else 0
    base_spines = capacity.spines if site_name is None else 0
    plan = PortPlan(capacity)
    connections = list(original_connections)
    updated_text = text
    leaves_added = 0
    spines_added = 0
    warnings: list[str] = []
    added_nodes: list[str] = []
    multi_dc = site_name is not None

    if add in {"leaf", "pair"}:
        leaves_to_add = count if add == "leaf" else count * 2
        next_leaf = max([base_leaves, *(item[0] for item in leaves)]) + 1
        added_leaf_names: list[str] = []
        for leaf_index in range(next_leaf, next_leaf + leaves_to_add):
            if leaf_index > capacity.max_leaves:
                _warn_soft_capacity(
                    warnings, f"leaf{leaf_index}", "max_leaves", capacity.max_leaves
                )
            leaf_name = f"{stem}-leaf{leaf_index}"
            new_connections = _leaf_mesh_connections(
                plan,
                connections,
                spines,
                leaf_name,
                leaf_index,
                warnings,
                multi_dc,
            )
            updated_text = _insert_node(
                updated_text,
                _node_yaml(
                    hostname_prefix,
                    serial_prefix,
                    "leaf",
                    leaf_index,
                    site_name,
                    site_index,
                ),
            )
            updated_text = _append_connections(updated_text, new_connections)
            added_leaf_names.append(leaf_name)
            added_nodes.append(leaf_name)
            leaves_added += 1

        if add == "pair":
            mlag_ports = plan.leaf_mlag_ports()
            leaf_rule = _leaf_rule(plan)
            for pair_offset in range(0, len(added_leaf_names), 2):
                odd_name, even_name = added_leaf_names[pair_offset : pair_offset + 2]
                peer_connections: list[Connection] = []
                for preferred in mlag_ports:
                    odd_port = _allocate_port(
                        plan,
                        used_ports_from_connections(connections, odd_name),
                        preferred,
                        odd_name,
                        warnings,
                        leaf_rule,
                    )
                    even_port = _allocate_port(
                        plan,
                        used_ports_from_connections(connections, even_name),
                        preferred,
                        even_name,
                        warnings,
                        leaf_rule,
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
        current_spines = max([base_spines, *(item[0] for item in spines)])
        if capacity.fabric_mode in {"l2ls", "l2"} and current_spines >= 2:
            raise ValueError("L2LS fabrics cannot have more than 2 spines")
        next_spine = max([base_spines, *(item[0] for item in spines)]) + 1
        if capacity.fabric_mode in {"l2ls", "l2"} and next_spine + count - 1 > 2:
            raise ValueError("L2LS fabrics cannot have more than 2 spines")
        for spine_index in range(next_spine, next_spine + count):
            if spine_index > capacity.max_spines:
                _warn_soft_capacity(
                    warnings,
                    f"spine{spine_index}",
                    "max_spines",
                    capacity.max_spines,
                )
            spine_name = f"{stem}-spine{spine_index}"
            new_connections = _spine_mesh_connections(
                plan,
                connections,
                leaves,
                spine_name,
                spine_index,
                warnings,
                multi_dc,
            )
            if site_name is not None:
                new_connections.extend(
                    _spine_uplink_connections(
                        plan,
                        connections,
                        stem,
                        site_name,
                        site_index,
                        spine_name,
                        spine_index,
                        warnings,
                    )
                )
            updated_text = _insert_node(
                updated_text,
                _node_yaml(
                    hostname_prefix,
                    serial_prefix,
                    "spine",
                    spine_index,
                    site_name,
                    site_index,
                ),
            )
            updated_text = _append_connections(updated_text, new_connections)
            added_nodes.append(spine_name)
            spines_added += 1

    else:
        assert pair is not None
        leaf_pairs = _leaf_pairs(connections, leaves)
        if pair > len(leaf_pairs):
            raise ValueError(f"leaf pair {pair} does not exist")
        (_, odd_name), (_, even_name) = leaf_pairs[pair - 1]
        next_slot = len(_mleafs_for_pair(connections, odd_name, even_name)) + 1
        next_mleaf = max([0, *(item[0] for item in mleafs)]) + 1
        leaf_rule = _leaf_rule(plan)
        for offset in range(count):
            slot = next_slot + offset
            if slot > capacity.max_mleafs_per_pair:
                _warn_soft_capacity(
                    warnings,
                    f"mleaf slot {slot}",
                    "max_mleafs_per_pair",
                    capacity.max_mleafs_per_pair,
                )
            mleaf_index = next_mleaf + offset
            mleaf_name = f"{stem}-mleaf{mleaf_index}"
            preferred_leaf_port = plan.leaf_mleaf_port(slot)
            odd_port = _allocate_port(
                plan,
                used_ports_from_connections(connections, odd_name),
                preferred_leaf_port,
                odd_name,
                warnings,
                leaf_rule,
                overrun=slot > capacity.max_mleafs_per_pair,
            )
            even_port = _allocate_port(
                plan,
                used_ports_from_connections(connections, even_name),
                preferred_leaf_port,
                even_name,
                warnings,
                leaf_rule,
                overrun=slot > capacity.max_mleafs_per_pair,
            )
            mleaf_connections = [
                Connection(mleaf_name, 1, odd_name, odd_port),
                Connection(mleaf_name, 2, even_name, even_port),
            ]
            updated_text = _insert_node(
                updated_text,
                _node_yaml(
                    hostname_prefix,
                    serial_prefix,
                    "mleaf",
                    mleaf_index,
                    site_name,
                    site_index,
                ),
            )
            updated_text = _append_connections(updated_text, mleaf_connections)
            connections.extend(mleaf_connections)
            added_nodes.append(mleaf_name)

    if site_name is None:
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

    _assert_unique_addresses(updated_text)

    output_path = _resolve_output(path, out, new)
    free_leaves, free_spines, free_mleaf_slots = _remaining_slots(
        updated_text,
        capacity,
        site_name,
        multi_prefix,
    )
    _write_atomic(output_path, updated_text, path.stat().st_mode & 0o777)
    write_png(topology_to_dot(updated_text), output_path.with_suffix(".png"))
    return ExtendResult(
        path=output_path,
        added_nodes=tuple(added_nodes),
        warnings=tuple(warnings),
        free_leaves=free_leaves,
        free_spines=free_spines,
        free_mleaf_slots=free_mleaf_slots,
    )

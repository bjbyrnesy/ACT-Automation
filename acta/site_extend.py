"""Promote single-site topologies and add named sites to multi-DC labs."""

from __future__ import annotations

import re
from dataclasses import replace

from acta.capacity import (
    Capacity,
    format_capacity_header,
    normalize_redundancy,
    parse_capacity_header,
)
from acta.create import node_address, node_block
from acta.mac import generate_mac
from acta.portplan import PortPlan, site_ordinal
from acta.site_names import (
    MAX_SITES,
    backbone_hostname,
    fabric_hostname,
    validate_site_token,
)
from acta.topology import Connection

_NODE_RE = re.compile(r"^  - (?P<name>[^:\n]+):\s*$", re.MULTILINE)
_NODE_BLOCK_RE = re.compile(
    r"(^  - (?P<name>[^:\n]+):\n)(?P<body>(?:      .+\n)+)",
    re.MULTILINE,
)
_SINGLE_FABRIC_RE = re.compile(
    r"^(?P<prefix>.+)-(?P<role>spine|leaf|mleaf|border)(?P<index>[1-9]\d*)$"
)
_BB_NODE_RE = re.compile(r"^(?P<prefix>.+)-bb(?P<index>[1-9]\d*)$")
_SERIAL_LINE_RE = re.compile(
    r"^[ \t]+serial_number:\s*(?P<serial>\S+)\s*$", re.MULTILINE
)
_CAPACITY_LINE_RE = re.compile(r"^#\s*capacity:.*$", re.MULTILINE)


def _node_names(text: str) -> list[str]:
    return [match.group("name") for match in _NODE_RE.finditer(text)]


def _has_backbone(text: str) -> bool:
    return any(_BB_NODE_RE.fullmatch(name) for name in _node_names(text))


def _detect_hostname_prefix(text: str) -> str:
    for name in _node_names(text):
        match = _SINGLE_FABRIC_RE.fullmatch(name)
        if match is not None:
            return match.group("prefix")
        bb_match = _BB_NODE_RE.fullmatch(name)
        if bb_match is not None:
            return bb_match.group("prefix")
    raise ValueError("topology has no fabric or backbone nodes to promote")


def _detect_serial_prefix(text: str, hostname_prefix: str) -> str:
    for match in _SERIAL_LINE_RE.finditer(text):
        serial = match.group("serial")
        for role in ("spine", "leaf", "mleaf", "border", "bb"):
            marker = f"-{role}"
            if marker in serial:
                return serial.split(marker, 1)[0]
        if serial.startswith(f"{hostname_prefix}-"):
            return hostname_prefix
    return hostname_prefix


def _connection_line(connection: Connection) -> str:
    return (
        f"  - connection: [{connection.a_node}:Ethernet{connection.a_port}, "
        f"{connection.b_node}:Ethernet{connection.b_port}]"
    )


def _rename_nodes_and_links(text: str, rename: dict[str, str]) -> str:
    """Rename hostnames in node keys and connection endpoints only.

    Serial/MAC identity strings are left untouched unless ``rekey_identity``
    rewrites them in a later pass.
    """

    def header_replacer(match: re.Match[str]) -> str:
        name = match.group("name")
        return f"  - {rename.get(name, name)}:"

    updated = _NODE_RE.sub(header_replacer, text)

    conn_re = re.compile(r"^  - connection:.*$", re.MULTILINE)

    def conn_replacer(match: re.Match[str]) -> str:
        line = match.group(0)
        for old, new in sorted(
            rename.items(), key=lambda item: len(item[0]), reverse=True
        ):
            line = line.replace(f"{old}:Ethernet", f"{new}:Ethernet")
        return line

    return conn_re.sub(conn_replacer, updated)


def _patch_promoted_nodes(
    text: str,
    *,
    hostname_prefix: str,
    serial_prefix: str,
    site: str,
    site_index: int,
    rekey_identity: bool,
) -> str:
    role_re = re.compile(
        rf"^{re.escape(hostname_prefix)}-{re.escape(site)}-"
        rf"(?P<role>spine|leaf|mleaf|border)(?P<index>[1-9]\d*)$"
    )

    def replacer(match: re.Match[str]) -> str:
        name = match.group("name")
        body = match.group("body")
        identity_match = role_re.fullmatch(name)
        if identity_match is None:
            return match.group(0)
        role = identity_match.group("role")
        index = int(identity_match.group("index"))
        identity = f"{site}-{role}{index}"
        address = node_address(role, index, site_index)
        body = re.sub(
            r"ip_addr:\s*\S+",
            f"ip_addr: 192.168.0.{address}/24",
            body,
            count=1,
        )
        if rekey_identity:
            serial = f"{serial_prefix}-{identity}"
            mac = generate_mac(serial_prefix, identity)
            body = re.sub(
                r"serial_number:\s*\S+",
                f"serial_number: {serial}",
                body,
                count=1,
            )
            body = re.sub(
                r"system_mac_address:\s*\S+",
                f"system_mac_address: {mac}",
                body,
                count=1,
            )
        return f"{match.group(1)}{body}"

    return _NODE_BLOCK_RE.sub(replacer, text)


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


def _backbone_node_yaml(
    hostname_prefix: str,
    serial_prefix: str,
    index: int,
) -> str:
    name = backbone_hostname(hostname_prefix, index)
    identity = f"bb{index}"
    return "\n".join(
        [
            f"  - {name}:",
            "      node_type: veos",
            f"      ip_addr: 192.168.0.{1 + index}/24",
            f"      serial_number: {serial_prefix}-{identity}",
            f"      system_mac_address: {generate_mac(serial_prefix, identity)}",
            "      ztp: false",
        ]
    )


def _append_lines(text: str, lines: list[str]) -> str:
    if not lines:
        return text
    return f"{text.rstrip()}\n" + "\n".join(lines) + "\n"


def _backbone_attach_lines(
    *,
    hostname_prefix: str,
    site: str,
    capacity: Capacity,
    plan: PortPlan,
    site_index: int,
) -> list[str]:
    lines: list[str] = []
    site_prefix = f"{hostname_prefix}-{site}"
    if capacity.fabric_mode in {"l2ls", "l2"}:
        lines.append("  # Backbone — spine <-> backbone (l2ls)")
        for spine in range(1, capacity.spines + 1):
            bb_port = plan.bb_spine_port(site_index, spine)
            for bb, uplink in enumerate(plan.spine_uplink_ports(), start=1):
                lines.append(
                    _connection_line(
                        Connection(
                            f"{site_prefix}-spine{spine}",
                            uplink,
                            backbone_hostname(hostname_prefix, bb),
                            bb_port,
                        )
                    )
                )
    else:
        lines.append("  # Backbone — border <-> backbone")
        for bb, border_port in enumerate(plan.border_bb_ports(), start=1):
            for border in range(1, capacity.border_count + 1):
                lines.append(
                    _connection_line(
                        Connection(
                            f"{site_prefix}-border{border}",
                            border_port,
                            backbone_hostname(hostname_prefix, bb),
                            plan.bb_border_port(site_index, border),
                        )
                    )
                )
    if capacity.bb_redundancy == "mlag-peer" and capacity.bb_count >= 2:
        peer = plan.bb_peer_port()
        lines.append("  # Backbone peer link")
        lines.append(
            _connection_line(
                Connection(
                    backbone_hostname(hostname_prefix, 1),
                    peer,
                    backbone_hostname(hostname_prefix, 2),
                    peer,
                )
            )
        )
    return lines


def _border_fabric_lines(
    *,
    hostname_prefix: str,
    site: str,
    capacity: Capacity,
    plan: PortPlan,
) -> list[str]:
    if capacity.fabric_mode not in {"l3ls", "l3"}:
        return []
    site_prefix = f"{hostname_prefix}-{site}"
    lines = [f"  # Site {site} — border <-> spine"]
    uplinks = plan.spine_uplink_ports()
    for spine in range(1, capacity.spines + 1):
        for border, uplink in enumerate(uplinks, start=1):
            if border > capacity.border_count:
                break
            lines.append(
                _connection_line(
                    Connection(
                        f"{site_prefix}-border{border}",
                        plan.border_to_spine_port(spine),
                        f"{site_prefix}-spine{spine}",
                        uplink,
                    )
                )
            )
    if capacity.border_redundancy == "mlag-peer" and capacity.border_count >= 2:
        lines.append(f"  # Site {site} — border MLAG peer")
        for port in plan.border_mlag_ports():
            lines.append(
                _connection_line(
                    Connection(
                        f"{site_prefix}-border1",
                        port,
                        f"{site_prefix}-border2",
                        port,
                    )
                )
            )
    return lines


def ensure_multi_dc(
    text: str,
    *,
    first_site: str = "A",
    rekey_identity: bool = False,
    bb_redundancy: str | None = None,
    border_redundancy: str | None = None,
    bb_count: int | None = None,
    border_count: int | None = None,
) -> str:
    """Promote a single-site topology to a named first site + backbone hub.

    Multi-DC input (backbone already present) is returned unchanged. Always a
    pure text transform — callers write a new dated file.
    """
    if _has_backbone(text):
        return text

    site = validate_site_token(first_site)
    capacity = parse_capacity_header(text)
    if capacity.fabric_mode is None:
        raise ValueError("capacity header fabric_mode is required to promote a site")

    updates: dict[str, object] = {}
    if bb_redundancy is not None:
        updates["bb_redundancy"] = normalize_redundancy(bb_redundancy)
    if border_redundancy is not None:
        updates["border_redundancy"] = normalize_redundancy(border_redundancy)
    if bb_count is not None:
        updates["bb_count"] = bb_count
    if border_count is not None:
        updates["border_count"] = border_count
    if updates:
        capacity = replace(capacity, **updates)

    hostname_prefix = _detect_hostname_prefix(text)
    serial_prefix = _detect_serial_prefix(text, hostname_prefix)
    site_index = 0

    rename: dict[str, str] = {}
    for name in _node_names(text):
        match = _SINGLE_FABRIC_RE.fullmatch(name)
        if match is None or match.group("prefix") != hostname_prefix:
            continue
        role = match.group("role")
        index = int(match.group("index"))
        rename[name] = fabric_hostname(hostname_prefix, site, f"{role}{index}")

    updated = _rename_nodes_and_links(text, rename)
    updated = _patch_promoted_nodes(
        updated,
        hostname_prefix=hostname_prefix,
        serial_prefix=serial_prefix,
        site=site,
        site_index=site_index,
        rekey_identity=rekey_identity,
    )

    bb_blocks = [
        "  # Backbone routers (IP transport between EVPN domains)",
        *[
            _backbone_node_yaml(hostname_prefix, serial_prefix, index)
            for index in range(1, capacity.bb_count + 1)
        ],
    ]
    # Place backbone nodes at the top of the nodes section.
    nodes_marker = re.search(r"^nodes:\s*$", updated, re.MULTILINE)
    if nodes_marker is None:
        raise ValueError("topology is missing a nodes section")
    insert_at = nodes_marker.end()
    updated = (
        f"{updated[:insert_at]}\n\n"
        + "\n\n".join(bb_blocks)
        + f"\n{updated[insert_at:]}"
    )

    plan = PortPlan(capacity)
    if capacity.fabric_mode == "l3ls":
        border_yaml = []
        for border in range(1, capacity.border_count + 1):
            border_yaml.extend(
                node_block(
                    hostname_prefix,
                    serial_prefix,
                    "border",
                    border,
                    site=site,
                    site_index=site_index,
                )
            )
            border_yaml.append("")
        # Insert borders just before the first spine of this site.
        spine_marker = re.search(
            rf"^  - {re.escape(hostname_prefix)}-{re.escape(site)}-spine1:\s*$",
            updated,
            re.MULTILINE,
        )
        if spine_marker is None:
            raise ValueError("promoted topology is missing spine1")
        body = "\n".join(border_yaml).rstrip()
        block = f"  # Site {site} — Border leaves\n\n{body}"
        updated = (
            f"{updated[: spine_marker.start()].rstrip()}\n\n{block}\n\n"
            f"{updated[spine_marker.start():]}"
        )

    link_lines: list[str] = []
    link_lines.extend(
        _border_fabric_lines(
            hostname_prefix=hostname_prefix,
            site=site,
            capacity=capacity,
            plan=plan,
        )
    )
    link_lines.extend(
        _backbone_attach_lines(
            hostname_prefix=hostname_prefix,
            site=site,
            capacity=capacity,
            plan=plan,
            site_index=site_index,
        )
    )
    updated = _append_lines(updated, link_lines)
    return _replace_capacity(updated, capacity)


def list_sites(text: str, hostname_prefix: str | None = None) -> list[str]:
    """Return sorted unique site tokens present in a multi-DC topology."""
    prefix = hostname_prefix or _detect_hostname_prefix(text)
    site_re = re.compile(
        rf"^{re.escape(prefix)}-(?P<site>[A-Za-z0-9][A-Za-z0-9_-]*)-"
        r"(?:border|spine|leaf|mleaf)[1-9]\d*$"
    )
    found = {
        match.group("site")
        for name in _node_names(text)
        if (match := site_re.fullmatch(name)) is not None
    }
    return sorted(found)


def projected_ceos_count(capacity: Capacity, site_count: int) -> int:
    """Rough cEOS count for RAM messaging (per-site fabric + borders + bbs)."""
    per_site = capacity.spines + capacity.leaves
    if capacity.fabric_mode == "l3ls":
        per_site += capacity.border_count
    return per_site * site_count + capacity.bb_count


__all__ = [
    "MAX_SITES",
    "ensure_multi_dc",
    "list_sites",
    "projected_ceos_count",
    "site_ordinal",
]

"""Graphviz DOT rendering for ACT topologies (parity with former generate.sh)."""

from __future__ import annotations

import itertools
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from acta.capacity import parse_capacity_header
from acta.site_names import (
    dot_safe_id,
    hostname_prefix_of,
    parse_fabric_identity,
)
from acta.topology import Connection, parse_connections

_NODE_BLOCK_RE = re.compile(
    r"^  - (?P<name>[^:\n]+):\n" r"(?P<body>(?:      .+\n)*)",
    re.MULTILINE,
)
_IP_RE = re.compile(r"ip_addr:\s*(?P<ip>[^\s/]+)")

_FILL = {
    "bb": "#d1fae5",
    "border": "#ede9fe",
    "spine": "#dbeafe",
    "leaf": "#fef3c7",
    "mleaf": "#fce7f3",
    "host": "#cffafe",
}
_MLAG_COLOR = "#dc2626"
_BB_COLOR = "#059669"
_HOST_COLOR = "#0891b2"
_HOSTS_PER_ROW = 6
_FABRIC_ROLES = ("bb", "border", "spine", "leaf", "mleaf")
_GENERIC_TYPE_RE = re.compile(r"node_type:\s*generic\b")
_HOST_INDEX_RE = re.compile(r"(?:^|-)host(?P<index>[1-9]\d*)$", re.IGNORECASE)


@dataclass(frozen=True)
class _Node:
    name: str
    role: str
    site: str | None
    index: int
    ip: str
    dot_id: str


def topology_to_dot(topology_source: str) -> str:
    """Return Graphviz DOT matching the former ``generate.sh`` layout."""
    nodes = _parse_nodes(topology_source)
    if not nodes:
        return 'digraph topology {\n  label="empty";\n}\n'

    connections = parse_connections(topology_source)
    by_name = {node.name: node for node in nodes}
    multi = any(node.site is not None for node in nodes)
    if multi:
        return _dot_multi(topology_source, nodes, by_name, connections)
    return _dot_single(topology_source, nodes, by_name, connections)


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


def _parse_nodes(topology_source: str) -> list[_Node]:
    nodes: list[_Node] = []
    host_ordinal = 0
    for match in _NODE_BLOCK_RE.finditer(topology_source):
        name = match.group("name").strip()
        body = match.group("body")
        ip_match = _IP_RE.search(body)
        ip = ip_match.group("ip") if ip_match else ""
        if _GENERIC_TYPE_RE.search(body):
            host_ordinal += 1
            index_match = _HOST_INDEX_RE.search(name)
            index = int(index_match.group("index")) if index_match else host_ordinal
            nodes.append(
                _Node(
                    name=name,
                    role="host",
                    site=None,
                    index=index,
                    ip=ip,
                    dot_id=_host_dot_id(name, index),
                )
            )
            continue
        parsed = _parse_identity(name)
        if parsed is None:
            continue
        site, role, index = parsed
        if role == "bb":
            dot_id = f"bb{index}"
        elif site is None:
            dot_id = f"{role}{index}"
        else:
            dot_id = f"{dot_safe_id(site)}_{role}{index}"
        nodes.append(
            _Node(
                name=name,
                role=role,
                site=site,
                index=index,
                ip=ip,
                dot_id=dot_id,
            )
        )
    return _with_host_sites(nodes, parse_connections(topology_source))


def _host_dot_id(name: str, index: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if safe and safe[0].isalpha():
        return safe
    return f"host{index}_{safe}" if safe else f"host{index}"


def _with_host_sites(nodes: list[_Node], connections: list[Connection]) -> list[_Node]:
    """Attach hosts to a site when all fabric peers share one site letter."""
    by_name = {node.name: node for node in nodes}
    assigned: list[_Node] = []
    for node in nodes:
        if node.role != "host":
            assigned.append(node)
            continue
        peer_sites: set[str] = set()
        for conn in connections:
            if conn.a_node == node.name:
                peer = by_name.get(conn.b_node)
            elif conn.b_node == node.name:
                peer = by_name.get(conn.a_node)
            else:
                continue
            if peer is not None and peer.site is not None:
                peer_sites.add(peer.site)
        site = next(iter(peer_sites)) if len(peer_sites) == 1 else None
        if site == node.site:
            assigned.append(node)
            continue
        assigned.append(
            _Node(
                name=node.name,
                role=node.role,
                site=site,
                index=node.index,
                ip=node.ip,
                dot_id=node.dot_id,
            )
        )
    return assigned


def _parse_identity(hostname: str) -> tuple[str | None, str, int] | None:
    """Return ``(site|None, role, index)`` from an ACT hostname."""
    return parse_fabric_identity(hostname)


def _host_prefix(nodes: list[_Node]) -> str:
    return hostname_prefix_of(nodes[0].name)


def _serial_prefix(source: str, nodes: list[_Node]) -> str:
    match = re.search(r"serial_number:\s*(?P<serial>[^\s-]+)", source)
    if match:
        return match.group("serial")
    return _host_prefix(nodes)


def _title_single(source: str, nodes: list[_Node]) -> str:
    spines = sum(1 for node in nodes if node.role == "spine")
    leaves = sum(1 for node in nodes if node.role == "leaf")
    mleafs = sum(1 for node in nodes if node.role == "mleaf")
    prefix = _serial_prefix(source, nodes)
    title = f"{prefix}: {spines} spine × {leaves} leaf"
    if _has_leaf_mlag(nodes, parse_connections(source)):
        title += " (MLAG)"
    if mleafs:
        title += f" + {mleafs} member{'s' if mleafs != 1 else ''}"
    hosts = sum(1 for node in nodes if node.role == "host")
    if hosts:
        title += f" + {hosts} host{'s' if hosts != 1 else ''}"
    return title


def _title_multi(source: str, nodes: list[_Node]) -> str:
    sites = sorted({node.site for node in nodes if node.site})
    spines = max(
        (
            sum(1 for node in nodes if node.site == site and node.role == "spine")
            for site in sites
        ),
        default=0,
    )
    leaves = max(
        (
            sum(1 for node in nodes if node.site == site and node.role == "leaf")
            for site in sites
        ),
        default=0,
    )
    prefix = _serial_prefix(source, nodes)
    fabric = _fabric_mode(source, nodes)
    title = f"{prefix}: {len(sites)} site × ({spines} spine × {leaves} leaf"
    if _has_leaf_mlag(nodes, parse_connections(source)):
        title += " MLAG"
    title += f") + backbone ({fabric})"
    return title


def _fabric_mode(source: str, nodes: list[_Node]) -> str:
    try:
        mode = parse_capacity_header(source).fabric_mode
    except ValueError:
        mode = None
    if mode:
        return mode
    return "l3ls" if any(node.role == "border" for node in nodes) else "l2ls"


def _ip_label(node: _Node, *, multi: bool) -> str:
    if not node.ip:
        return node.name
    if multi and node.role != "bb":
        octet = node.ip.rsplit(".", 1)[-1]
        return f"{node.name}\\n.{octet}"
    return f"{node.name}\\n{node.ip}"


def _node_decl(node: _Node, *, multi: bool, indent: str = "  ") -> str:
    fill = _FILL.get(node.role, "#dbeafe")
    label = _ip_label(node, multi=multi)
    return f'{indent}{node.dot_id} [label="{_escape(label)}", fillcolor="{fill}"];'


def _has_leaf_mlag(nodes: list[_Node], connections: list[Connection]) -> bool:
    by_name = {node.name: node for node in nodes}
    for conn in connections:
        left = by_name.get(conn.a_node)
        right = by_name.get(conn.b_node)
        if left and right and left.role == "leaf" and right.role == "leaf":
            return True
    return False


def _edge_style(left: _Node, right: _Node, *, multi_site: bool = False) -> str:
    roles = {left.role, right.role}
    mlag_width = "1.5" if multi_site else "2"
    if roles <= {"leaf", "spine", "border"} and len(roles) == 1:
        return (
            f' [style=dashed, color="{_MLAG_COLOR}", '
            f"penwidth={mlag_width}, constraint=false]"
        )
    if roles == {"bb"}:
        return f' [style=dashed, color="{_BB_COLOR}", penwidth=2, constraint=false]'
    if "bb" in roles:
        return f' [color="{_BB_COLOR}", penwidth=1.5]'
    if "host" in roles:
        # constraint=false so dual-home uplinks cannot pull hosts beside leaves.
        return f' [color="{_HOST_COLOR}", penwidth=1.2, constraint=false]'
    return ""


def _ordered_pair(left: _Node, right: _Node) -> tuple[_Node, _Node]:
    """Prefer parent→child edge direction for Graphviz ranking."""
    order = {"bb": 0, "border": 1, "spine": 2, "leaf": 3, "mleaf": 4, "host": 5}
    if order.get(left.role, 9) <= order.get(right.role, 9):
        return left, right
    return right, left


def _sorted_hosts(hosts: list[_Node]) -> list[_Node]:
    return sorted(hosts, key=lambda item: (item.index, item.name))


def _host_rows(hosts: list[_Node]) -> list[list[_Node]]:
    ordered = _sorted_hosts(hosts)
    return [
        ordered[index : index + _HOSTS_PER_ROW]
        for index in range(0, len(ordered), _HOSTS_PER_ROW)
    ]


def _lowest_fabric_nodes(nodes: list[_Node]) -> list[_Node]:
    """Bottom switch tier used to pin host ranks below the fabric."""
    for role in reversed(_FABRIC_ROLES):
        group = [node for node in nodes if node.role == role]
        if group:
            return sorted(group, key=lambda item: (item.index, item.name))
    return []


def _append_host_ranks(
    lines: list[str],
    hosts: list[_Node],
    *,
    fabric_nodes: list[_Node],
    multi: bool,
    indent: str,
) -> None:
    """Place hosts in horizontal rows strictly below fabric switches."""
    rows = _host_rows(hosts)
    if not rows:
        return
    anchors = _lowest_fabric_nodes(fabric_nodes)
    for row in rows:
        lines.append(f"{indent}{{ rank=same;")
        for node in row:
            lines.append(_node_decl(node, multi=multi, indent=f"{indent}  "))
        lines.append(f"{indent}}}")
    # Invisible edges force hosts under the lowest switch tier, then stack rows.
    if anchors:
        lines.append(
            f"{indent}{anchors[0].dot_id} -> {rows[0][0].dot_id} "
            f"[style=invis, weight=100];"
        )
    for upper, lower in itertools.pairwise(rows):
        lines.append(
            f"{indent}{upper[0].dot_id} -> {lower[0].dot_id} "
            f"[style=invis, weight=100];"
        )
    # Keep hosts in a row left-to-right.
    for row in rows:
        if len(row) < 2:
            continue
        chain = " -> ".join(node.dot_id for node in row)
        lines.append(f"{indent}{chain} [style=invis, weight=10];")


def _dot_single(
    source: str,
    nodes: list[_Node],
    by_name: dict[str, _Node],
    connections: list[Connection],
) -> str:
    lines = [
        "digraph topology {",
        f'  label="{_escape(_title_single(source, nodes))}";',
        '  labelloc="t"; fontname="Helvetica"; fontsize=16;',
        "  rankdir=TB; splines=line; nodesep=0.4; ranksep=1.0;",
        (
            '  node [shape=box, style="rounded,filled", '
            'fontname="Helvetica", fontsize=11];'
        ),
        "  edge [dir=none, penwidth=1.2];",
        "",
    ]
    fabric = [node for node in nodes if node.role != "host"]
    for role in ("spine", "leaf", "mleaf"):
        group = sorted(
            (node for node in fabric if node.role == role),
            key=lambda item: item.index,
        )
        if not group:
            continue
        lines.append("  { rank=same;")
        for node in group:
            lines.append(_node_decl(node, multi=False, indent="    "))
        lines.append("  }")
    hosts = [node for node in nodes if node.role == "host"]
    if hosts:
        lines.append("")
        _append_host_ranks(lines, hosts, fabric_nodes=fabric, multi=False, indent="  ")
    lines.append("")
    for conn in connections:
        left = by_name.get(conn.a_node)
        right = by_name.get(conn.b_node)
        if left is None or right is None:
            continue
        parent, child = _ordered_pair(left, right)
        style = _edge_style(parent, child)
        lines.append(f"  {parent.dot_id} -> {child.dot_id}{style};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _dot_multi(
    source: str,
    nodes: list[_Node],
    by_name: dict[str, _Node],
    connections: list[Connection],
) -> str:
    fabric = _fabric_mode(source, nodes)
    lines = [
        "digraph topology {",
        f'  label="{_escape(_title_multi(source, nodes))}";',
        '  labelloc="t"; fontname="Helvetica"; fontsize=18;',
        "  rankdir=TB; compound=true; splines=true;",
        "  nodesep=0.3; ranksep=0.8;",
        (
            '  node [shape=box, style="rounded,filled", '
            'fontname="Helvetica", fontsize=10];'
        ),
        "  edge [dir=none, penwidth=1.0];",
        "",
        "  { rank=min;",
    ]
    for node in sorted(
        (item for item in nodes if item.role == "bb"),
        key=lambda item: item.index,
    ):
        lines.append(
            f'    {node.dot_id} [label="{_escape(_ip_label(node, multi=False))}", '
            f'fillcolor="{_FILL["bb"]}"];'
        )
    lines.append("  }")
    lines.append("")

    sites = sorted({node.site for node in nodes if node.site})
    for site in sites:
        site_nodes = [node for node in nodes if node.site == site]
        lines.append(f"  subgraph cluster_{dot_safe_id(site)} {{")
        lines.append(
            f'    label="Site {site}"; style="rounded,dashed"; color="#6b7280";'
        )
        lines.append('    fontname="Helvetica-Bold"; fontsize=13; margin=12;')
        lines.append("")
        site_fabric = [node for node in site_nodes if node.role != "host"]
        for role in ("border", "spine", "leaf", "mleaf"):
            if role == "border" and fabric != "l3ls":
                continue
            group = sorted(
                (node for node in site_fabric if node.role == role),
                key=lambda item: item.index,
            )
            if not group:
                continue
            lines.append("    { rank=same;")
            for node in group:
                lines.append(_node_decl(node, multi=True, indent="      "))
            lines.append("    }")
        site_hosts = [node for node in site_nodes if node.role == "host"]
        if site_hosts:
            lines.append("")
            _append_host_ranks(
                lines,
                site_hosts,
                fabric_nodes=site_fabric,
                multi=True,
                indent="    ",
            )
        lines.append("")

        for conn in connections:
            left = by_name.get(conn.a_node)
            right = by_name.get(conn.b_node)
            if left is None or right is None:
                continue
            if left.role == "bb" or right.role == "bb":
                continue
            if left.site != site or right.site != site:
                continue
            parent, child = _ordered_pair(left, right)
            style = _edge_style(parent, child, multi_site=True)
            lines.append(f"    {parent.dot_id} -> {child.dot_id}{style};")
        lines.append("  }")
        lines.append("")

    unscoped_hosts = [
        node for node in nodes if node.role == "host" and node.site is None
    ]
    if unscoped_hosts:
        fabric_all = [node for node in nodes if node.role != "host"]
        _append_host_ranks(
            lines,
            unscoped_hosts,
            fabric_nodes=fabric_all,
            multi=True,
            indent="  ",
        )
        lines.append("")
        for conn in connections:
            left = by_name.get(conn.a_node)
            right = by_name.get(conn.b_node)
            if left is None or right is None:
                continue
            if left.role != "host" and right.role != "host":
                continue
            if left.site is not None and right.site is not None:
                continue
            parent, child = _ordered_pair(left, right)
            style = _edge_style(parent, child, multi_site=True)
            lines.append(f"  {parent.dot_id} -> {child.dot_id}{style};")

    for conn in connections:
        left = by_name.get(conn.a_node)
        right = by_name.get(conn.b_node)
        if left is None or right is None:
            continue
        if left.role != "bb" and right.role != "bb":
            continue
        # Site gear → backbone (matches generate.sh); bb peer either way.
        if left.role == "bb" and right.role != "bb":
            left, right = right, left
        style = _edge_style(left, right, multi_site=True)
        lines.append(f"  {left.dot_id} -> {right.dot_id}{style};")

    lines.append("}")
    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

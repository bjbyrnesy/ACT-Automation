from __future__ import annotations

import re
from dataclasses import dataclass

_CONN_RE = re.compile(
    r"connection:\s*\[(?P<a_node>[^:]+):Ethernet(?P<a_port>\d+),\s*"
    r"(?P<b_node>[^:]+):Ethernet(?P<b_port>\d+)\]"
)


@dataclass(frozen=True)
class Connection:
    a_node: str
    a_port: int
    b_node: str
    b_port: int


def parse_connections(text: str) -> list[Connection]:
    out: list[Connection] = []
    for match in _CONN_RE.finditer(text):
        out.append(
            Connection(
                a_node=match.group("a_node").strip(),
                a_port=int(match.group("a_port")),
                b_node=match.group("b_node").strip(),
                b_port=int(match.group("b_port")),
            )
        )
    return out


def used_ports_from_connections(conns: list[Connection], node: str) -> set[int]:
    used: set[int] = set()
    for conn in conns:
        if conn.a_node == node:
            used.add(conn.a_port)
        if conn.b_node == node:
            used.add(conn.b_port)
    return used

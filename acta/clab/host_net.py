"""Opt-in host data-plane addressing helpers (attach --host-net)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

DEFAULT_HOST_NET_SUBNET = "192.168.2.0/24"
DEFAULT_HOST_NET_GATEWAY = "192.168.2.1"

LABEL_ENABLED = "acta.host-net"
LABEL_IP = "acta.host-ip"
LABEL_SUBNET = "acta.host-subnet"
LABEL_GATEWAY = "acta.host-gateway"
LABEL_IFACE = "acta.host-iface"


@dataclass(frozen=True)
class HostNetPlan:
    """Resolved host data-plane network addressing plan."""

    ip: str
    subnet: str
    gateway: str
    iface: str
    dual_homed: bool

    @property
    def prefixlen(self) -> int:
        """Return the IPv4 prefix length of the resolved subnet."""
        return ipaddress.ip_network(self.subnet, strict=False).prefixlen


def validate_host_net(subnet: str, gateway: str, host_ip: str | None) -> None:
    """Validate IPv4 subnet, gateway, and optional explicit host IP."""
    network = ipaddress.ip_network(subnet, strict=False)
    if network.version != 4:
        raise ValueError("host net subnet must be IPv4")
    gw = ipaddress.ip_address(gateway)
    if gw.version != 4:
        raise ValueError(f"gateway {gateway} must be IPv4")
    if gw not in network:
        raise ValueError(f"gateway {gateway} is not in subnet {subnet}")
    if gw in (network.network_address, network.broadcast_address):
        raise ValueError("gateway cannot be network or broadcast address")
    if host_ip is None:
        return
    addr = ipaddress.ip_address(host_ip)
    if addr.version != 4:
        raise ValueError(f"host IP {host_ip} must be IPv4")
    if addr not in network:
        raise ValueError(f"host IP {host_ip} is not in subnet {subnet}")
    if addr in (network.network_address, network.broadcast_address):
        raise ValueError("host IP cannot be network or broadcast address")
    if addr == gw:
        raise ValueError("host IP cannot equal gateway")


def next_host_ip(subnet: str, gateway: str, claimed: set[str]) -> str:
    """Return the lowest available host IPv4 address in subnet."""
    validate_host_net(subnet, gateway, None)
    network = ipaddress.ip_network(subnet, strict=False)
    gw = ipaddress.ip_address(gateway)
    taken = {ipaddress.ip_address(x) for x in claimed}
    for candidate in network.hosts():
        if candidate == gw or candidate in taken:
            continue
        return str(candidate)
    raise ValueError(f"no free host addresses left in {subnet}")


def claimed_ips_from_clab(lab: dict) -> set[str]:
    """Extract claimed host data-plane IPs from containerlab node labels."""
    nodes = ((lab.get("topology") or {}).get("nodes")) or {}
    out: set[str] = set()
    if not isinstance(nodes, dict):
        return out
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        labels = node.get("labels") or {}
        if not isinstance(labels, dict):
            continue
        if str(labels.get(LABEL_ENABLED, "")).lower() not in {"1", "true", "yes"}:
            continue
        ip = str(labels.get(LABEL_IP, "")).strip()
        if ip:
            out.add(ip.split("/", 1)[0])
    return out


def resolve_host_net(
    *,
    enabled: bool,
    host_ip: str | None,
    host_subnet: str | None,
    host_gateway: str | None,
    config: dict[str, str] | None,
    claimed: set[str],
    dual_homed: bool,
) -> HostNetPlan | None:
    """Resolve effective host data-plane plan or None when disabled."""
    if not enabled:
        return None
    cfg = config or {}
    subnet = (
        host_subnet or cfg.get("HOST_NET_SUBNET") or DEFAULT_HOST_NET_SUBNET
    ).strip()
    gateway = (
        host_gateway or cfg.get("HOST_NET_GATEWAY") or DEFAULT_HOST_NET_GATEWAY
    ).strip()
    explicit = host_ip.strip() if host_ip else None
    validate_host_net(subnet, gateway, explicit)
    if explicit:
        if explicit in claimed:
            raise ValueError(f"host IP {explicit} already in use")
        ip = explicit
    else:
        ip = next_host_ip(subnet, gateway, claimed)
    iface = "bond0" if dual_homed else "eth1"
    return HostNetPlan(
        ip=ip, subnet=subnet, gateway=gateway, iface=iface, dual_homed=dual_homed
    )

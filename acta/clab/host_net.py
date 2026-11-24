"""Opt-in host data-plane addressing helpers (attach --host-net)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

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


def _clean(value: object) -> str:
    """Return a stripped string, or ``""`` for null / non-string values."""
    return value.strip() if isinstance(value, str) else ""


def _label_ip(labels: dict) -> str:
    """Return the bare host IP from labels, or ``""`` when missing/malformed."""
    ip = _clean(labels.get(LABEL_IP) or "").split("/", 1)[0]
    if not ip:
        return ""
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return ""
    return ip


def host_net_enabled(labels: object) -> bool:
    """Return True when containerlab node labels opt into host-net."""
    if not isinstance(labels, dict):
        return False
    return str(labels.get(LABEL_ENABLED, "")).strip().lower() in {"1", "true", "yes"}


def _lab_nodes(lab: dict) -> dict:
    nodes = ((lab.get("topology") or {}).get("nodes")) or {}
    return nodes if isinstance(nodes, dict) else {}


def claimed_ips_from_clab(lab: dict) -> set[str]:
    """Extract claimed host data-plane IPs from containerlab node labels."""
    out: set[str] = set()
    for node in _lab_nodes(lab).values():
        if not isinstance(node, dict):
            continue
        labels = node.get("labels")
        if not host_net_enabled(labels):
            continue
        ip = _label_ip(labels)
        if ip:
            out.add(ip)
    return out


def host_net_labels_by_node(lab: dict) -> dict[str, dict]:
    """Return ``{node: labels}`` for every host-net enabled node in ``lab``."""
    return {
        name: node["labels"]
        for name, node in _lab_nodes(lab).items()
        if isinstance(node, dict) and host_net_enabled(node.get("labels"))
    }


def plan_from_labels(labels: dict, *, dual_homed: bool) -> HostNetPlan:
    """Rebuild a ``HostNetPlan`` from persisted ``acta.host-*`` labels."""
    ip = _label_ip(labels)
    if not ip:
        raise ValueError(f"missing or invalid {LABEL_IP} label")
    subnet = _clean(labels.get(LABEL_SUBNET)) or DEFAULT_HOST_NET_SUBNET
    gateway = _clean(labels.get(LABEL_GATEWAY)) or DEFAULT_HOST_NET_GATEWAY
    validate_host_net(subnet, gateway, ip)
    return HostNetPlan(
        ip=ip,
        subnet=subnet,
        gateway=gateway,
        iface="bond0" if dual_homed else "eth1",
        dual_homed=dual_homed,
    )


def host_net_bind_sources(lab: dict) -> list[str]:
    """Return relative ``<stem>.host-net/...`` bind sources used by ``lab``."""
    out: list[str] = []
    for node in _lab_nodes(lab).values():
        if not isinstance(node, dict) or not host_net_enabled(node.get("labels")):
            continue
        for bind in node.get("binds") or []:
            source = PurePosixPath(str(bind).split(":", 1)[0])
            if source.is_absolute() or ".." in source.parts:
                continue
            if source.parts and source.parts[0].endswith(".host-net"):
                out.append(source.as_posix())
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
        _clean(host_subnet)
        or _clean(cfg.get("HOST_NET_SUBNET"))
        or DEFAULT_HOST_NET_SUBNET
    )
    gateway = (
        _clean(host_gateway)
        or _clean(cfg.get("HOST_NET_GATEWAY"))
        or DEFAULT_HOST_NET_GATEWAY
    )
    explicit = _clean(host_ip) or None
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


def host_net_labels(plan: HostNetPlan) -> dict[str, str]:
    """Return containerlab node labels describing the host data-plane plan."""
    return {
        LABEL_ENABLED: "true",
        LABEL_IP: plan.ip,
        LABEL_SUBNET: plan.subnet,
        LABEL_GATEWAY: plan.gateway,
        LABEL_IFACE: plan.iface,
    }


def render_bootstrap(plan: HostNetPlan) -> str:
    """Render an idempotent POSIX sh script that configures the data-plane NIC(s)."""
    addr = f"{plan.ip}/{plan.prefixlen}"
    wait_ifaces = "eth1 eth2" if plan.dual_homed else "eth1"
    lines = [
        "#!/bin/sh",
        "# Generated by acta host-net; safe to re-run (uses `ip ... replace`).",
        "set -eu",
        "",
        "# Wait briefly for containerlab to attach the data-plane interface(s).",
        f"for ifc in {wait_ifaces}; do",
        "    n=0",
        '    until ip link show "$ifc" >/dev/null 2>&1; do',
        "        n=$((n + 1))",
        '        [ "$n" -ge 30 ] && { echo "host-net: $ifc not found" >&2; exit 1; }',
        "        sleep 1",
        "    done",
        "done",
        "",
    ]
    if plan.dual_homed:
        lines += [
            "# LACP bond across eth1 + eth2 (create only if missing).",
            "if ! ip link show bond0 >/dev/null 2>&1; then",
            "    ip link add bond0 type bond mode 802.3ad miimon 100",
            "fi",
            "for ifc in eth1 eth2; do",
            '    ip link set "$ifc" down',
            '    ip link set "$ifc" master bond0',
            '    ip link set "$ifc" up',
            "done",
            "ip link set bond0 up",
        ]
    else:
        lines.append("ip link set eth1 up")
    lines += [
        f"ip addr replace {addr} dev {plan.iface}",
        f"ip route replace default via {plan.gateway} dev {plan.iface}",
        "",
    ]
    return "\n".join(lines)


def render_host_net_env(plan: HostNetPlan) -> str:
    """Render HOST-NET.env (shell-sourceable key=value pairs)."""
    return (
        f"HOST_NET_IP={plan.ip}\n"
        f"HOST_NET_SUBNET={plan.subnet}\n"
        f"HOST_NET_PREFIXLEN={plan.prefixlen}\n"
        f"HOST_NET_GATEWAY={plan.gateway}\n"
        f"HOST_NET_IFACE={plan.iface}\n"
        f"HOST_NET_DUAL_HOMED={'true' if plan.dual_homed else 'false'}\n"
    )


def render_host_net_md(plan: HostNetPlan, *, host: str) -> str:
    """Render HOST-NET.md describing the host data-plane addressing and tools."""
    if plan.dual_homed:
        topo = (
            "## Dual-homed (LACP)\n\n"
            "This host has two data-plane NICs (`eth1`, `eth2`) bonded into "
            f"`{plan.iface}` using LACP (802.3ad). Configure a matching "
            "LACP port-channel on the switch pair (MLAG) via CloudVision "
            "Studios; the bond will not pass traffic until the switch side "
            "negotiates LACP.\n"
        )
    else:
        topo = (
            "## Single-homed\n\n"
            f"This host has one data-plane NIC (`{plan.iface}`). Configure the "
            "connected switch access port via CloudVision Studios.\n"
        )
    return (
        f"# Host data-plane network: {host}\n\n"
        "## Current settings\n\n"
        f"- IP: `{plan.ip}/{plan.prefixlen}`\n"
        f"- Interface: `{plan.iface}`\n"
        f"- Subnet: `{plan.subnet}`\n"
        f"- Gateway: `{plan.gateway}`\n\n"
        "## Management vs data plane\n\n"
        "`eth0` is the containerlab management interface (SSH, out-of-band). "
        f"`{plan.iface}` is the data-plane path into the lab switches; traffic "
        "to lab endpoints and the default route use the data plane.\n\n"
        f"{topo}\n"
        "## Changing the IP\n\n"
        "Temporary (until restart). Flush the old address first; "
        "`ip addr replace` with a different IP adds a second address instead "
        "of swapping it:\n\n"
        "```sh\n"
        f"ip -4 addr flush dev {plan.iface}\n"
        f"ip addr add <new-ip>/{plan.prefixlen} dev {plan.iface}\n"
        f"ip route replace default via <gateway> dev {plan.iface}\n"
        "```\n\n"
        "Persistent: re-run the bootstrap script after editing the values, or "
        "re-attach with a new `--host-ip`.\n\n"
        "## Tools\n\n"
        "- `ping`, `traceroute`, `curl`, `dig`\n"
        "- `lldpcli` (LLDP neighbors)\n"
        "- `mcast-send`, `mcast-receive`, `mcast-status` (multicast testing)\n"
    )


def host_net_bind_dir(clab_path: Path, host: str) -> PurePosixPath:
    """Return the per-host artifact dir relative to the containerlab file.

    containerlab resolves relative bind sources against the topology file's
    directory, so these binds travel with the topology to ``CLAB_HOST``.
    """
    name = clab_path.name
    stem = clab_path.stem
    for suffix in (".clab.yml", ".clab.yaml", ".yml", ".yaml"):
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            break
    return PurePosixPath(f"{stem}.host-net", host)


def host_net_artifact_dir(clab_path: Path, host: str) -> Path:
    """Return the per-host artifact directory next to a containerlab file."""
    return clab_path.parent / host_net_bind_dir(clab_path, host)


def write_host_net_files(
    dir: Path, host: str, plan: HostNetPlan
) -> tuple[Path, Path, Path]:
    """Write bootstrap.sh, HOST-NET.md, HOST-NET.env under ``dir/host``."""
    out = Path(dir) / host
    out.mkdir(parents=True, exist_ok=True)
    bootstrap = out / "bootstrap.sh"
    md = out / "HOST-NET.md"
    env = out / "HOST-NET.env"
    bootstrap.write_text(render_bootstrap(plan), encoding="utf-8")
    bootstrap.chmod(0o755)
    md.write_text(render_host_net_md(plan, host=host), encoding="utf-8")
    env.write_text(render_host_net_env(plan), encoding="utf-8")
    return bootstrap, md, env

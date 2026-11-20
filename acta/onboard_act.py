"""Onboard Running ACT labs to CVaaS via TerminAttr over SSH."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from acta.act_api import ActClient

EOS_USER_DEFAULT = "cvpadmin"
EOS_PASS_DEFAULT = "cvp123!"
CVAAS_PORT_DEFAULT = "443"


def resolve_eos_credentials(
    topology: Mapping[str, Any] | None,
) -> tuple[str, str]:
    """Resolve EOS SSH credentials from a topology ``veos`` block.

    Matches ``onboard.sh``: prefer ``veos.username`` / ``veos.password``, else
    ``cvpadmin`` / ``cvp123!``.
    """
    veos: Mapping[str, Any] = {}
    if isinstance(topology, Mapping):
        raw = topology.get("veos")
        if isinstance(raw, Mapping):
            veos = raw

    username = veos.get("username")
    password = veos.get("password")
    resolved_user = (
        username.strip()
        if isinstance(username, str) and username.strip()
        else EOS_USER_DEFAULT
    )
    resolved_pass = (
        password if isinstance(password, str) and password else EOS_PASS_DEFAULT
    )
    return resolved_user, resolved_pass


def build_terminattr_snippet(
    *,
    cvaas_token: str,
    cvaas_host: str,
    cvaas_port: str = CVAAS_PORT_DEFAULT,
) -> str:
    """Build the EOS CLI snippet pasted by ``onboard.sh``."""
    return (
        "enable\n"
        f'bash echo "{cvaas_token}" > /tmp/cv-onboarding-token\n'
        "configure\n"
        "daemon TerminAttr\n"
        "   exec /usr/bin/TerminAttr "
        "-smashexcludes=ale,flexCounter,hardware,kni,pulse,strata "
        f"-cvaddr={cvaas_host}:{cvaas_port} "
        "-cvauth=token-secure,/tmp/cv-onboarding-token -taillogs\n"
        "   shutdown\n"
        "   no shutdown\n"
        "end\n"
        "write"
    )


def _veos_hostnames_from_topology(topology: Mapping[str, Any] | None) -> set[str]:
    """Return hostnames declared as ``node_type: veos`` under ``nodes``."""
    if not isinstance(topology, Mapping):
        return set()
    nodes = topology.get("nodes")
    if not isinstance(nodes, list):
        return set()

    names: set[str] = set()
    for entry in nodes:
        if not isinstance(entry, Mapping):
            continue
        for hostname, body in entry.items():
            if not isinstance(hostname, str) or not isinstance(body, Mapping):
                continue
            if body.get("node_type") == "veos":
                names.add(hostname)
    return names


def _veos_devices(
    lab: Mapping[str, Any],
    topology: Mapping[str, Any] | None,
) -> list[tuple[str, str]]:
    """Return ``(hostname, internal_ip)`` pairs for vEOS devices in ``lab``."""
    devices = lab.get("devices")
    if not isinstance(devices, Mapping):
        return []
    veos_list = devices.get("veos")
    if not isinstance(veos_list, list):
        return []

    allowed = _veos_hostnames_from_topology(topology)
    out: list[tuple[str, str]] = []
    for device in veos_list:
        if not isinstance(device, Mapping):
            continue
        hostname = device.get("hostname")
        internal_ip = device.get("internal_ip")
        if not isinstance(hostname, str) or not hostname:
            continue
        if not isinstance(internal_ip, str) or not internal_ip:
            continue
        if allowed and hostname not in allowed:
            continue
        out.append((hostname, internal_ip))
    return out


def _pick_lab(
    running: Sequence[Mapping[str, Any]],
    choose_lab: Callable[[list[dict[str, Any]]], Mapping[str, Any]] | None,
) -> Mapping[str, Any]:
    if not running:
        raise RuntimeError(
            "No Running labs found. Deploy or start a lab in the ACT UI, "
            "then re-run onboard."
        )
    if len(running) == 1:
        return running[0]
    if choose_lab is None:
        raise RuntimeError(
            f"Multiple Running labs found ({len(running)}); pass choose_lab "
            "to select one."
        )
    chosen = choose_lab([dict(lab) for lab in running])
    if not isinstance(chosen, Mapping) or "id" not in chosen:
        raise RuntimeError("choose_lab must return a lab mapping with an id")
    return chosen


def run_onboard_act(
    client: ActClient,
    *,
    act_user: str,
    cvaas_token: str,
    cvaas_host: str,
    cvaas_port: str = CVAAS_PORT_DEFAULT,
    run_ssh: Callable[[str, str, str, str], None],
    choose_lab: Callable[[list[dict[str, Any]]], Mapping[str, Any]] | None = None,
) -> tuple[str, str]:
    """List Running labs, resolve EOS password, SSH-paste TerminAttr config.

    ``run_ssh(host, commands, username, password)`` is injected so unit tests
    never open real SSH. Returns ``(eos_username, eos_password)`` resolved from
    the topology.
    """
    running = client.list_running_labs(act_user)
    lab_summary = _pick_lab(running, choose_lab)
    lab_id = lab_summary["id"]
    if not isinstance(lab_id, str) or not lab_id:
        raise RuntimeError("Selected lab is missing an id")

    lab = client.get_lab(lab_id)
    topo_name = lab.get("topology_definition")
    if not isinstance(topo_name, str) or not topo_name:
        topo_name = lab_summary.get("topology_definition")

    topology: Mapping[str, Any] | None = None
    if isinstance(topo_name, str) and topo_name:
        topology = client.get_topology_content(topo_name)

    username, password = resolve_eos_credentials(topology)
    devices = _veos_devices(lab, topology)
    if not devices:
        lab_name = lab.get("name", lab_id)
        raise RuntimeError(f"no vEOS devices found in lab {lab_name} ({lab_id})")

    snippet = build_terminattr_snippet(
        cvaas_token=cvaas_token,
        cvaas_host=cvaas_host,
        cvaas_port=cvaas_port,
    )
    for _hostname, internal_ip in devices:
        run_ssh(internal_ip, snippet, username, password)
    return username, password

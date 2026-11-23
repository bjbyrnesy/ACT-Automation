"""Deploy generated containerlab labs."""

from __future__ import annotations

import ipaddress
import sys
from pathlib import Path

from .destroy import destroy
from .generate import yaml_text
from .support import (
    ANNOTATION_SCRIPT,
    DEPLOY_SCRIPT,
    SUPPORT_SCRIPT,
    fail,
    host_run,
    resolve_clab_runtime,
    resolve_topology_path,
    support_bundle,
    validate_bridge_name,
    validate_lab,
    validate_network_name,
)


def _apply_mgmt_overrides(lab: dict, args) -> bool:
    """Patch ``lab['mgmt']`` from deploy flags. Return True if anything changed."""
    mgmt_network = getattr(args, "mgmt_network", None)
    mgmt_bridge = getattr(args, "mgmt_bridge", None)
    mgmt_subnet = getattr(args, "mgmt_subnet", None)
    mgmt_gateway = getattr(args, "mgmt_gateway", None)
    mgmt_range = getattr(args, "mgmt_range", None)
    mgmt_mtu = getattr(args, "mgmt_mtu", None)
    if not any(
        (mgmt_network, mgmt_bridge, mgmt_subnet, mgmt_gateway, mgmt_range, mgmt_mtu)
    ):
        return False

    mgmt = lab.setdefault("mgmt", {})
    if not isinstance(mgmt, dict):
        fail("Invalid management network configuration.")

    if mgmt_network:
        if "/" in mgmt_network:
            fail(
                "--mgmt-network is the Docker/Podman network name "
                "(e.g. clab or mgmt), not a subnet. Use --mgmt-subnet for CIDR."
            )
        mgmt["network"] = validate_network_name(mgmt_network)
    if mgmt_bridge:
        mgmt["bridge"] = validate_bridge_name(mgmt_bridge)

    subnet = None
    if mgmt_subnet:
        try:
            subnet = ipaddress.ip_network(mgmt_subnet, strict=True)
            if subnet.version != 4 or subnet.prefixlen > 30:
                raise ValueError(
                    "expected an IPv4 network with a prefix of /30 or shorter"
                )
        except ValueError as exc:
            fail(f"Invalid management subnet: {exc}")
        mgmt["ipv4-subnet"] = str(subnet)
    elif mgmt.get("ipv4-subnet"):
        try:
            subnet = ipaddress.ip_network(str(mgmt["ipv4-subnet"]), strict=True)
        except ValueError:
            subnet = None

    if mgmt_gateway is not None:
        if subnet is None:
            fail(
                "--mgmt-gateway requires a management subnet (--mgmt-subnet or in topology)."
            )
        try:
            gateway = ipaddress.IPv4Address(mgmt_gateway)
        except ipaddress.AddressValueError as exc:
            fail(f"Invalid management gateway: {exc}")
        if gateway not in subnet or gateway in (
            subnet.network_address,
            subnet.broadcast_address,
        ):
            fail("gateway must be a usable address in the management subnet")
        mgmt["ipv4-gw"] = str(gateway)

    if mgmt_range is not None:
        if subnet is None:
            fail(
                "--mgmt-range requires a management subnet (--mgmt-subnet or in topology)."
            )
        try:
            pool = ipaddress.ip_network(mgmt_range, strict=True)
        except ValueError as exc:
            fail(f"Invalid management range: {exc}")
        if pool.version != 4 or not pool.subnet_of(subnet):
            fail("management range must be an IPv4 subnet inside the management subnet")
        mgmt["ipv4-range"] = str(pool)

    if mgmt_mtu is not None:
        if not 576 <= mgmt_mtu <= 65535:
            fail("management MTU must be between 576 and 65535")
        mgmt["mtu"] = mgmt_mtu

    return True


def deploy(args):
    path = resolve_topology_path(Path(args.topology), args)
    args.topology = str(path)
    lab = validate_lab(path)
    content = path.read_text()
    if _apply_mgmt_overrides(lab, args):
        content = yaml_text(lab)
    bundle = support_bundle(path.parent, lab)
    if bundle:
        result = host_run(args.host, SUPPORT_SCRIPT, [lab["name"]], bundle)
        if result.returncode:
            fail(f"Could not install lab support files: {result.stderr.strip()}")
    annotation_path = Path(str(path) + ".annotations.json")
    if annotation_path.is_file():
        result = host_run(
            args.host, ANNOTATION_SCRIPT, [lab["name"]], annotation_path.read_text()
        )
        if result.returncode:
            fail(f"Could not install viewer annotations: {result.stderr.strip()}")
        if result.stdout:
            print(result.stdout, end="")
    requested = getattr(args, "runtime", None)
    runtime = resolve_clab_runtime(args.host, requested)
    how = "explicit" if requested in ("docker", "podman") else "auto-detect"
    print(f"Using container runtime: {runtime} ({how})")
    result = host_run(
        args.host,
        DEPLOY_SCRIPT,
        [lab["name"], runtime],
        content,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode:
        fail(f"Deployment failed: {result.stderr.strip()}")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    print(f"Deployed {lab['name']}.")


def redeploy(args):
    """Destroy an existing lab (if present), then deploy the topology again."""
    destroy(args, allow_missing=True)
    deploy(args)

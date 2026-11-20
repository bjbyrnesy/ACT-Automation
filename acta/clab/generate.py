"""Convert ACT topology YAML to containerlab YAML."""

import hashlib
import ipaddress
import json
import re
import shlex
import subprocess
from pathlib import Path

from .layout import topology_layout, viewer_annotations
from .support import (
    DEFAULT_HOST_IMAGE,
    IMAGE,
    MARKER,
    MGMT_VRF,
    NAME,
    NODE,
    act_hostname,
    fail,
    linux_jumphost_node,
    mgmt_service_commands,
    parse_ipv4_list,
    read_yaml,
    validate_network_name,
)

BASE_CONFIG = """! Copyright 2020 Nokia
! Licensed under the BSD 3-Clause License.
! SPDX-License-Identifier: BSD-3-Clause
hostname {{ .ShortName }}
username admin privilege 15 secret admin
!
service routing protocols model multi-agent
!
{{- if .Env.CLAB_MGMT_VRF }}
vrf instance {{ .Env.CLAB_MGMT_VRF }}
!
{{end}}
{{ if .MgmtIPv4Gateway }}ip route {{ if .Env.CLAB_MGMT_VRF }}vrf {{ .Env.CLAB_MGMT_VRF }} {{end}}0.0.0.0/0 {{ .MgmtIPv4Gateway }}{{end}}
{{ if .MgmtIPv6Gateway }}ipv6 route {{ if .Env.CLAB_MGMT_VRF }}vrf {{ .Env.CLAB_MGMT_VRF }} {{end}}::0/0 {{ .MgmtIPv6Gateway }}{{end}}
!
interface {{ .MgmtIntf }}
{{ if .Env.CLAB_MGMT_VRF }} vrf {{ .Env.CLAB_MGMT_VRF }}{{end}}
{{ if .MgmtIPv4Address }}ip address {{ .MgmtIPv4Address }}/{{.MgmtIPv4PrefixLength}}{{end}}
{{ if .MgmtIPv6Address }}ipv6 address {{ .MgmtIPv6Address }}/{{.MgmtIPv6PrefixLength}}{{end}}
!
management api gnmi
   transport grpc default
{{ if .Env.CLAB_MGMT_VRF }}      vrf {{ .Env.CLAB_MGMT_VRF }}{{end}}
!
management api netconf
   transport ssh default
{{ if .Env.CLAB_MGMT_VRF }}      vrf {{ .Env.CLAB_MGMT_VRF }}{{end}}
!
management api http-commands
   no shutdown
{{- if .Env.CLAB_MGMT_VRF }}
   !
   vrf {{ .Env.CLAB_MGMT_VRF }}
      no shutdown
{{end}}
!
end
"""


def management_settings(args, subnet, count):
    try:
        gateway = (
            ipaddress.IPv4Address(args.mgmt_gateway)
            if args.mgmt_gateway
            else subnet.network_address + 1
        )
        if gateway not in subnet or gateway in (
            subnet.network_address,
            subnet.broadcast_address,
        ):
            raise ValueError(
                "gateway must be a usable address in the management subnet"
            )
        pool = (
            ipaddress.ip_network(args.mgmt_range, strict=True)
            if args.mgmt_range
            else subnet
        )
        if pool.version != 4 or not pool.subnet_of(subnet):
            raise ValueError(
                "management range must be an IPv4 subnet inside the management subnet"
            )
        if args.mgmt_bridge:
            from .support import validate_bridge_name

            validate_bridge_name(args.mgmt_bridge)
        if args.mgmt_mtu is not None and not 576 <= args.mgmt_mtu <= 65535:
            raise ValueError("management MTU must be between 576 and 65535")
        first = max(int(pool.network_address) + 1, int(subnet.network_address) + 1)
        last = min(int(pool.broadcast_address) - 1, int(subnet.broadcast_address) - 1)
        addresses = []
        while first <= last and len(addresses) < count:
            if first != int(gateway):
                addresses.append(str(ipaddress.IPv4Address(first)))
            first += 1
        if len(addresses) != count:
            raise ValueError("management address range is too small for all nodes")
    except ValueError as exc:
        fail(f"Invalid management settings: {exc}")
    mgmt = {"ipv4-subnet": str(subnet)}
    for key, value in (
        ("ipv4-gw", args.mgmt_gateway),
        ("ipv4-range", args.mgmt_range),
        ("bridge", args.mgmt_bridge),
        ("mtu", args.mgmt_mtu),
    ):
        if value is not None:
            mgmt[key] = value
    return mgmt, addresses


def yaml_text(data):
    try:
        result = subprocess.run(
            ["yq", "-p=json", "-o=yaml", "-P", "."],
            input=json.dumps(data),
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        fail("yq is required; install Mike Farah yq (v4).")
    except subprocess.CalledProcessError as exc:
        fail(f"Cannot render topology YAML: {exc.stderr.strip()}")
    remarks = {
        "name:": '# Lab name scopes the lab directory; container names use node keys (prefix: "").',
        "prefix:": "# Empty prefix: container name == node name (e.g. blz2-A-spine1).",
        "mgmt:": "# Management network: subnet, optional gateway, address range, bridge, and MTU.",
        "topology:": "# Topology: cEOS settings, individual nodes, and their physical links.",
        "  kinds:": "  # Shared cEOS commands configure management VRF, DNS, and optional NTP.",
        "  nodes:": (
            "  # Device definitions: image, management address, and management VRF.\n"
            "  # The startup config and per-node identity files are relative to this YAML.\n"
            "  # Viewer labels set the node's site group and position."
        ),
        "  links:": "  # Data-plane links connect the two named node interfaces; et maps to EOS Ethernet.",
    }
    lines = []
    for line in result.stdout.splitlines():
        for key, remark in remarks.items():
            if line.startswith(key) and (key == "name:" or line.strip() == key.strip()):
                lines.append(remark)
                break
        lines.append(line)
    return MARKER + "\n".join(lines) + "\n"


def generate(args):
    from .support import resolve_clab_lab_name

    source = Path(args.source)
    args.name = resolve_clab_lab_name(source, args)
    if not args.name:
        fail("Lab name required (--name or CLAB_NAME in .config).")
    if not args.image:
        fail("Image required (--image, CLAB_IMAGE, or EOS_VERSION in .config).")
    if not NAME.fullmatch(args.name):
        fail(
            "Lab name must be lowercase letters, numbers and hyphens, starting with a letter or number (maximum 63 characters)."
        )
    if not IMAGE.fullmatch(args.image):
        fail("Invalid image name.")
    try:
        subnet = ipaddress.ip_network(args.mgmt_subnet, strict=True)
        if "/" not in args.mgmt_subnet or subnet.version != 4 or subnet.prefixlen > 30:
            raise ValueError("expected an IPv4 network with a prefix of /30 or shorter")
    except ValueError as exc:
        fail(f"Invalid management subnet: {exc}")
    name_servers = parse_ipv4_list(args.name_servers, "name-server")
    ntp_servers = parse_ipv4_list(args.ntp_servers or [], "ntp-server")
    header = source.read_text()[:2048]
    if "Generated by acta." not in header and "Generated by generate.sh" not in header:
        fail("Input must be an ACT topology generated by acta.py act create.")
    act = read_yaml(source)
    nodes, links = {}, []
    serial_files = {}
    act_entries = act.get("nodes", [])

    def _typed_count(node_type: str) -> int:
        return sum(
            1
            for entry in act_entries
            if isinstance(entry, dict)
            and len(entry) == 1
            and isinstance(next(iter(entry.values())), dict)
            and next(iter(entry.values())).get("node_type") == node_type
        )

    veos_count = _typed_count("veos")
    generic_count = _typed_count("generic")
    mgmt, addresses = management_settings(
        args, subnet, max(veos_count + generic_count, 1)
    )
    config = getattr(args, "config", None) or {}
    host_image = (
        getattr(args, "host_image", None)
        or config.get("CLAB_HOST_IMAGE")
        or DEFAULT_HOST_IMAGE
    )
    act_to_short = {}
    address_index = 0
    for entry in act_entries:
        if not isinstance(entry, dict) or len(entry) != 1:
            fail("Invalid ACT node.")
        name, data = next(iter(entry.items()))
        if not NODE.fullmatch(name) or not isinstance(data, dict):
            fail(f"Invalid node: {name}")
        hostname = act_hostname(name)
        if hostname in nodes:
            fail(f"Duplicate node name after normalization: {hostname}")
        act_to_short[name] = hostname
        node_type = data.get("node_type")
        if node_type == "generic":
            # Linux jumphost — same hostname as ACT generic node; LLDP on by default.
            nodes[hostname] = linux_jumphost_node(
                host_image, mgmt_ipv4=addresses[address_index]
            )
            address_index += 1
            continue
        if node_type != "veos" or not data.get("serial_number"):
            fail(f"Invalid vEOS node: {name}")
        # Keep full ACT hostnames as containerlab node keys. With prefix:"" the
        # container name is exactly this string (e.g. blz2-A-spine1).
        serial = (
            "CLAB"
            + hashlib.sha256(str(data["serial_number"]).encode())
            .hexdigest()[:12]
            .upper()
        )
        hostname_exec = "Cli -p 15 -c " + shlex.quote(
            "\n".join(
                [
                    "enable",
                    "configure terminal",
                    f"hostname {hostname}",
                    "end",
                    "write memory",
                ]
            )
        )
        nodes[hostname] = {
            "kind": "arista_ceos",
            "image": args.image,
            "env": {
                "CEOS_SERIAL_NUMBER": serial,
                "CLAB_MGMT_VRF": MGMT_VRF,
                "CLAB_HOSTNAME": hostname,
                "INTFTYPE": "et",
            },
            "exec": [hostname_exec],
            "startup-config": "configs/base-config.eos",
            "binds": ["configs/SN/__clabNodeName__.eos:/mnt/flash/ceos-config:ro"],
            "mgmt-ipv4": addresses[address_index],
        }
        address_index += 1
        mac_hash = hashlib.sha256(
            ("clab-mac-" + str(data["serial_number"])).encode()
        ).hexdigest()
        mac = "02" + mac_hash[:10]
        serial_files[hostname] = (
            f"SERIALNUMBER={serial}\nSYSTEMMACADDR={mac[:4]}.{mac[4:8]}.{mac[8:]}\n"
        )
    if not any(node.get("kind") == "arista_ceos" for node in nodes.values()):
        fail("Topology contains no vEOS nodes.")
    used = set()
    for link in act.get("links", []):
        endpoints = link.get("connection", [])
        if not isinstance(endpoints, list) or len(endpoints) != 2:
            fail("Invalid ACT link.")
        converted = []
        for endpoint in endpoints:
            match = re.fullmatch(r"([^:]+):Ethernet([1-9][0-9]*)", str(endpoint))
            if not match or match.group(1) not in act_to_short:
                fail(f"Invalid link endpoint: {endpoint}")
            peer = act_to_short[match.group(1)]
            port = match.group(2)
            iface = "eth" if nodes[peer].get("kind") == "linux" else "et"
            converted.append(f"{peer}:{iface}{port}")
        if any(e in used for e in converted) or converted[0] == converted[1]:
            fail("An interface is used by more than one link.")
        used.update(converted)
        links.append({"endpoints": converted})
    layout = topology_layout(act_to_short, act.get("links", []))
    for act_name, labels in layout.items():
        node = nodes.get(act_to_short[act_name])
        if node is not None and node.get("kind") == "arista_ceos":
            node["labels"] = labels
    # Generated cEOS nodes always use MGMT VRF — DNS/NTP must be VRF-scoped.
    bootstrap = (
        ["enable", "configure terminal"]
        + mgmt_service_commands(name_servers, ntp_servers, mgmt_vrf=MGMT_VRF)
        + ["end", "write memory"]
    )
    bootstrap_exec = "Cli -p 15 -c " + shlex.quote("\n".join(bootstrap))
    # Node-level exec overrides kind-level exec in containerlab.
    for node in nodes.values():
        if node.get("kind") == "arista_ceos":
            node["exec"].append(bootstrap_exec)
    lab = {
        "name": args.name,
        # Empty prefix → container name equals node name (blz2-A-spine1), not
        # clab-<lab>-<node>. See https://containerlab.dev/manual/topo-def-file/
        "prefix": "",
        "mgmt": mgmt,
        "topology": {
            "kinds": {"arista_ceos": {"exec": [bootstrap_exec]}},
            "nodes": nodes,
            "links": links,
        },
    }
    if args.mgmt_network:
        lab["mgmt"]["network"] = validate_network_name(args.mgmt_network)
    if args.output:
        output = Path(args.output)
    elif getattr(args, "source", None):
        output = Path(args.source).with_name(f"{Path(args.source).stem}.clab.yml")
    else:
        output = Path(f"{args.name}.clab.yml")
    config_dir = output.parent / "configs"
    serial_dir = config_dir / "SN"
    if config_dir.is_symlink() or serial_dir.is_symlink():
        fail("Refusing to write through a symlinked config directory.")
    if (config_dir / "base-config.eos").is_symlink():
        fail("Refusing a symlinked base startup config.")
    for node, content in serial_files.items():
        existing = serial_dir / f"{node}.eos"
        if existing.is_symlink():
            fail(f"Refusing symlinked serial file: {existing}")
        if existing.exists() and existing.read_text() != content:
            fail(f"Serial file already exists with different identity: {existing}")
    rendered = yaml_text(lab)
    serial_dir.mkdir(parents=True, exist_ok=True)
    base_path = config_dir / "base-config.eos"
    if not base_path.exists():
        base_path.write_text(BASE_CONFIG)
    for node, content in serial_files.items():
        serial_path = serial_dir / f"{node}.eos"
        if not serial_path.exists():
            serial_path.write_text(content)
    output.write_text(rendered)
    annotations_path = Path(str(output) + ".annotations.json")
    if annotations_path.exists():
        print(f"Preserving existing viewer annotations: {annotations_path}")
    else:
        annotations_path.write_text(
            json.dumps(viewer_annotations(layout, act_to_short), indent=2) + "\n"
        )
        print(f"Wrote {annotations_path}")
    print(f"Wrote {output}")
    print(
        "cEOS serial and system MAC are pinned in per-node ceos-config files; verify them on your host."
    )

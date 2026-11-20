from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from acta.capacity import (
    HARD_PORT_MAX,
    Capacity,
    format_capacity_header,
    validate_create_capacity,
    validate_current_capacity,
)
from acta.config import load_config, save_config
from acta.diagram import topology_to_dot, write_png
from acta.mac import generate_mac
from acta.portplan import PortPlan
from acta.prompt import prompt_value

DEFAULT_EOS_VERSION = "4.35.4M"
_PREFIX_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


def capacity_banner() -> str:
    """Explain how reserved capacity supports later, non-disruptive growth."""
    return (
        "Reserve spare ports now so this topology can grow without moving existing "
        "links.\n"
        "Later, use acta.py act extend --add leaf, acta.py act extend --add spine, or\n"
        "acta.py act extend --add mleaf --pair N within the limits chosen below."
    )


@dataclass(frozen=True)
class FabricSpec:
    """Inputs required to emit an ACT fabric topology."""

    hostname_prefix: str
    serial_prefix: str
    eos_version: str
    capacity: Capacity
    mlag_pairs: bool
    spine_mlag: bool
    member_leaf_pairs: list[int]
    member_leaves_per_pair: int
    dc_count: int = 1


def _validate_spec(spec: FabricSpec) -> None:
    validate_create_capacity(spec.capacity)
    if not 1 <= spec.dc_count <= MAX_DC:
        raise ValueError(f"dc_count must be between 1 and {MAX_DC}")
    mode = spec.capacity.fabric_mode
    if spec.dc_count > 1 and mode not in {"l3ls", "l2ls", "l2"}:
        raise ValueError("multi-DC fabrics require fabric_mode l3ls or l2ls")
    if spec.spine_mlag and spec.capacity.spines != 2:
        raise ValueError("spine MLAG requires exactly two spines")
    if spec.member_leaf_pairs and not spec.mlag_pairs:
        raise ValueError("member leaves require leaf MLAG")
    if spec.member_leaf_pairs and spec.member_leaves_per_pair < 1:
        raise ValueError("member_leaves_per_pair must be >= 1")
    if not spec.member_leaf_pairs and spec.member_leaves_per_pair != 0:
        raise ValueError("member_leaves_per_pair requires member_leaf_pairs")
    if spec.member_leaves_per_pair > spec.capacity.max_mleafs_per_pair:
        raise ValueError("member_leaves_per_pair exceeds reserved member-leaf capacity")
    _validate_address_ceilings(spec)

    pair_count = spec.capacity.leaves // 2
    if len(set(spec.member_leaf_pairs)) != len(spec.member_leaf_pairs):
        raise ValueError("member_leaf_pairs must not contain duplicates")
    if any(pair < 1 or pair > pair_count for pair in spec.member_leaf_pairs):
        raise ValueError(f"member leaf pair must be between 1 and {pair_count}")

    plan = PortPlan(spec.capacity)
    service_ports: list[int] = []
    if spec.mlag_pairs:
        service_ports.extend(plan.leaf_mlag_ports())
    if spec.member_leaf_pairs:
        service_ports.extend(
            plan.leaf_mleaf_port(slot)
            for slot in range(1, spec.member_leaves_per_pair + 1)
        )
    if spec.spine_mlag:
        service_ports.extend(plan.spine_mlag_ports())
    if spec.dc_count > 1:
        service_ports.extend(plan.spine_uplink_ports())
        if spec.capacity.fabric_mode == "l3ls":
            service_ports.extend(plan.border_bb_ports())
        else:
            service_ports.append(plan.bb_peer_port(spec.dc_count))
    if service_ports and max(service_ports) > HARD_PORT_MAX:
        raise ValueError(
            f"planned service ports exceed Ethernet{HARD_PORT_MAX} hard cap"
        )


def _validate_address_ceilings(spec: FabricSpec) -> None:
    """Reject specs whose nodes would overflow their management-IP blocks."""
    multi_dc = spec.dc_count > 1
    spine_limit = address_limit("spine", multi_dc)
    if spec.capacity.max_spines > spine_limit:
        raise ValueError(
            f"max_spines {spec.capacity.max_spines} exceeds the management-address "
            f"limit of {spine_limit} spines"
        )
    leaf_limit = address_limit("leaf", multi_dc)
    if spec.capacity.leaves > leaf_limit:
        raise ValueError(
            f"leaves {spec.capacity.leaves} exceeds the management-address "
            f"limit of {leaf_limit} leaves"
        )
    member_count = len(spec.member_leaf_pairs) * spec.member_leaves_per_pair
    mleaf_limit = address_limit("mleaf", multi_dc)
    if member_count > mleaf_limit:
        scope = "per site" if multi_dc else "in total"
        raise ValueError(
            f"{member_count} member leaves exceeds the management-address "
            f"limit of {mleaf_limit} {scope}"
        )


MAX_DC = 4
SITE_LETTERS = "ABCD"
_BB_COUNT = 2
_BORDER_COUNT = 2
# Multi-DC address layout mirrors generate.sh: backbone at .2/.3, then 62 per site.
_SITE_ADDRESS_BASE = 4
_SITE_ADDRESS_STRIDE = 62
_MULTI_DC_ADDRESS_OFFSETS = {"border": 0, "spine": 2, "leaf": 11, "mleaf": 50}
_SINGLE_DC_ADDRESS_BASES = {"spine": 10, "leaf": 20, "mleaf": 130}
# Per-role index ceilings keep every node inside its own management-IP block
# (generate.sh MAX_SPINES / MAX_LEAVES[_MULTI] / MAX_TOTAL_MEMBER_LEAVES[_MULTI]).
MAX_ADDRESS_SPINES = 9
_SINGLE_DC_ADDRESS_LIMITS = {"spine": MAX_ADDRESS_SPINES, "leaf": 99, "mleaf": 100}
_MULTI_DC_ADDRESS_LIMITS = {
    "border": _BORDER_COUNT,
    "spine": MAX_ADDRESS_SPINES,
    "leaf": 39,
    "mleaf": 12,
}


def site_letter(site_index: int) -> str:
    """Return the site letter for a 0-based site index."""
    return SITE_LETTERS[site_index]


def address_limit(role: str, multi_dc: bool) -> int:
    """Return the highest node index whose management IP stays in its block."""
    limits = _MULTI_DC_ADDRESS_LIMITS if multi_dc else _SINGLE_DC_ADDRESS_LIMITS
    try:
        return limits[role]
    except KeyError:
        scope = "multi-DC" if multi_dc else "single-DC"
        raise ValueError(f"unknown {scope} node role: {role!r}") from None


def node_address(role: str, index: int, site_index: int | None = None) -> int:
    """Return the last octet of the management address for a fabric node.

    Raises ``ValueError`` when ``index`` would overflow the role's address block
    (and so collide with another node's management IP).
    """
    multi_dc = site_index is not None
    limit = address_limit(role, multi_dc)
    if not 1 <= index <= limit:
        scope = "per-site multi-DC" if multi_dc else "single-DC"
        raise ValueError(
            f"{role}{index} exceeds the {scope} management-address limit "
            f"of {limit} {role}s"
        )
    if site_index is None:
        return _SINGLE_DC_ADDRESS_BASES[role] + index
    base = _SITE_ADDRESS_BASE + site_index * _SITE_ADDRESS_STRIDE
    return base + _MULTI_DC_ADDRESS_OFFSETS[role] + index - 1


def node_block(
    hostname_prefix: str,
    serial_prefix: str,
    role: str,
    index: int,
    site: str | None = None,
    site_index: int | None = None,
) -> list[str]:
    """Return the YAML lines for one fabric node (``site`` set for multi-DC).

    Letter sites ``A``–``D`` infer ``site_index`` from ``SITE_LETTERS``. Named
    sites must pass an explicit 0-based ``site_index`` (sorted ordinal).
    """
    identity = f"{role}{index}" if site is None else f"{site}-{role}{index}"
    if site is not None and site_index is None:
        if len(site) == 1 and site in SITE_LETTERS:
            site_index = SITE_LETTERS.index(site)
        else:
            raise ValueError(
                f"site_index is required for named site {site!r} "
                "(letter sites A–D infer index automatically)"
            )
    address = node_address(role, index, site_index)
    return [
        f"  - {hostname_prefix}-{identity}:",
        "      node_type: veos",
        f"      ip_addr: 192.168.0.{address}/24",
        f"      serial_number: {serial_prefix}-{identity}",
        f"      system_mac_address: {generate_mac(serial_prefix, identity)}",
        "      ztp: false",
    ]


def _node_lines(
    spec: FabricSpec,
    role: str,
    index: int,
    site: str | None = None,
) -> list[str]:
    return node_block(spec.hostname_prefix, spec.serial_prefix, role, index, site)


def _connection(
    a_node: str,
    a_port: int,
    b_node: str,
    b_port: int,
) -> str:
    return f"  - connection: [{a_node}:Ethernet{a_port}, " f"{b_node}:Ethernet{b_port}]"


def _title(site: str | None, text: str) -> str:
    return f"  # {text}" if site is None else f"  # Site {site} — {text}"


def _site_node_lines(spec: FabricSpec, site: str | None) -> list[str]:
    """Emit spine, leaf and member-leaf nodes (plus borders) for one site."""
    lines: list[str] = []
    if site is not None and spec.capacity.fabric_mode == "l3ls":
        lines.extend(["", _title(site, "Border leaves")])
        for border in range(1, _BORDER_COUNT + 1):
            lines.extend(["", *_node_lines(spec, "border", border, site)])
    lines.extend(["", _title(site, "Spines")])
    for spine in range(1, spec.capacity.spines + 1):
        lines.extend(["", *_node_lines(spec, "spine", spine, site)])
    lines.extend(["", _title(site, "Leaves")])
    for leaf in range(1, spec.capacity.leaves + 1):
        lines.extend(["", *_node_lines(spec, "leaf", leaf, site)])
    member_count = len(spec.member_leaf_pairs) * spec.member_leaves_per_pair
    if member_count:
        lines.extend(["", _title(site, "Member leaves")])
        for member in range(1, member_count + 1):
            lines.extend(["", *_node_lines(spec, "mleaf", member, site)])
    return lines


def _site_link_lines(spec: FabricSpec, plan: PortPlan, site: str | None) -> list[str]:
    """Emit fabric-internal links for one site (and border links for l3ls)."""
    prefix = spec.hostname_prefix if site is None else f"{spec.hostname_prefix}-{site}"
    lines: list[str] = []
    if site is not None:
        lines.extend(["", _title(site, "spine <-> leaf full mesh")])
    for spine in range(1, spec.capacity.spines + 1):
        for leaf in range(1, spec.capacity.leaves + 1):
            lines.append(
                _connection(
                    f"{prefix}-spine{spine}",
                    plan.spine_to_leaf_port(leaf),
                    f"{prefix}-leaf{leaf}",
                    plan.leaf_to_spine_port(spine),
                )
            )

    if spec.mlag_pairs:
        lines.extend(["", _title(site, "MLAG peer links")])
        mlag_ports = plan.leaf_mlag_ports()
        for odd_leaf in range(1, spec.capacity.leaves, 2):
            even_leaf = odd_leaf + 1
            for port in mlag_ports:
                lines.append(
                    _connection(
                        f"{prefix}-leaf{odd_leaf}",
                        port,
                        f"{prefix}-leaf{even_leaf}",
                        port,
                    )
                )

    if spec.spine_mlag:
        lines.extend(["", _title(site, "Spine MLAG peer links")])
        for port in plan.spine_mlag_ports():
            lines.append(
                _connection(
                    f"{prefix}-spine1",
                    port,
                    f"{prefix}-spine2",
                    port,
                )
            )

    member_count = len(spec.member_leaf_pairs) * spec.member_leaves_per_pair
    if member_count:
        lines.extend(["", _title(site, "Member-leaf uplinks")])
        member = 0
        for pair in spec.member_leaf_pairs:
            odd_leaf = 2 * pair - 1
            even_leaf = 2 * pair
            for slot in range(1, spec.member_leaves_per_pair + 1):
                member += 1
                leaf_port = plan.leaf_mleaf_port(slot)
                lines.append(
                    _connection(
                        f"{prefix}-mleaf{member}",
                        1,
                        f"{prefix}-leaf{odd_leaf}",
                        leaf_port,
                    )
                )
                lines.append(
                    _connection(
                        f"{prefix}-mleaf{member}",
                        2,
                        f"{prefix}-leaf{even_leaf}",
                        leaf_port,
                    )
                )

    if site is not None and spec.capacity.fabric_mode == "l3ls":
        uplinks = plan.spine_uplink_ports()
        lines.extend(["", _title(site, "border <-> spine")])
        for spine in range(1, spec.capacity.spines + 1):
            for border, uplink in enumerate(uplinks, start=1):
                lines.append(
                    _connection(
                        f"{prefix}-border{border}",
                        plan.border_to_spine_port(spine),
                        f"{prefix}-spine{spine}",
                        uplink,
                    )
                )
        lines.extend(["", _title(site, "border MLAG peer")])
        for port in plan.border_mlag_ports():
            lines.append(
                _connection(f"{prefix}-border1", port, f"{prefix}-border2", port)
            )
    return lines


def _backbone_link_lines(spec: FabricSpec, plan: PortPlan) -> list[str]:
    """Emit site <-> backbone links and the bb1/bb2 peer link."""
    prefix = spec.hostname_prefix
    lines: list[str] = []
    if spec.capacity.fabric_mode in {"l2ls", "l2"}:
        lines.extend(["", "  # Backbone — spine <-> backbone (l2ls)"])
        for site_index in range(spec.dc_count):
            site = site_letter(site_index)
            for spine in range(1, spec.capacity.spines + 1):
                bb_port = plan.bb_spine_port(site_index, spine)
                for bb, uplink in enumerate(plan.spine_uplink_ports(), start=1):
                    lines.append(
                        _connection(
                            f"{prefix}-{site}-spine{spine}",
                            uplink,
                            f"{prefix}-bb{bb}",
                            bb_port,
                        )
                    )
    else:
        lines.extend(["", "  # Backbone — border <-> backbone"])
        for site_index in range(spec.dc_count):
            site = site_letter(site_index)
            for bb, border_port in enumerate(plan.border_bb_ports(), start=1):
                for border in range(1, _BORDER_COUNT + 1):
                    lines.append(
                        _connection(
                            f"{prefix}-{site}-border{border}",
                            border_port,
                            f"{prefix}-bb{bb}",
                            plan.bb_border_port(site_index, border),
                        )
                    )
    if spec.capacity.bb_redundancy == "mlag-peer" and spec.capacity.bb_count >= 2:
        peer = plan.bb_peer_port()
        lines.extend(["", "  # Backbone peer link"])
        lines.append(_connection(f"{prefix}-bb1", peer, f"{prefix}-bb2", peer))
    return lines


def emit_act_yaml(spec: FabricSpec) -> str:
    """Emit an ACT topology for one data center or a backbone-joined multi-DC."""
    _validate_spec(spec)
    plan = PortPlan(spec.capacity)
    multi_dc = spec.dc_count > 1
    lines = [
        "###############################################################################",
        "# Generated by acta.",
        *format_capacity_header(spec.capacity).rstrip().splitlines(),
        "###############################################################################",
        "",
        "veos:",
        "  username: cvpadmin",
        "  password: cvp123!",
        f"  version: {spec.eos_version}",
        "  internet_access: true",
        "",
        "settings:",
        "  legacy_eos_versioning: false",
        "",
        "nodes:",
    ]
    sites: list[str | None] = (
        [site_letter(index) for index in range(spec.dc_count)] if multi_dc else [None]
    )
    if multi_dc:
        lines.extend(["", "  # Backbone routers (IP transport between EVPN domains)"])
        for bb in range(1, _BB_COUNT + 1):
            bb_mac = generate_mac(spec.serial_prefix, f"bb{bb}")
            lines.extend(
                [
                    "",
                    f"  - {spec.hostname_prefix}-bb{bb}:",
                    "      node_type: veos",
                    f"      ip_addr: 192.168.0.{1 + bb}/24",
                    f"      serial_number: {spec.serial_prefix}-bb{bb}",
                    f"      system_mac_address: {bb_mac}",
                    "      ztp: false",
                ]
            )
    for site in sites:
        lines.extend(_site_node_lines(spec, site))

    lines.extend(
        [
            "",
            "###############################################################################",
            "# Data-plane links",
            "###############################################################################",
            "links:",
        ]
    )
    for site in sites:
        lines.extend(_site_link_lines(spec, plan, site))
    if multi_dc:
        lines.extend(_backbone_link_lines(spec, plan))
    return "\n".join(lines) + "\n"


def _prompt_int(
    label: str,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    default = max(default, minimum)
    if maximum is not None:
        if maximum < minimum:
            raise ValueError("maximum must be greater than or equal to minimum")
        default = min(default, maximum)

    while True:
        value = prompt_value(label, str(default))
        try:
            number = int(value)
        except ValueError:
            number = minimum - 1
        if number >= minimum and (maximum is None or number <= maximum):
            return number
        if maximum is None:
            requirement = f"at least {minimum}"
        else:
            requirement = f"between {minimum} and {maximum}"
        print(f"  Enter a whole number {requirement}.", file=sys.stderr)


def _prompt_yes_no(label: str, default: bool = False) -> bool:
    default_text = "y" if default else "n"
    while True:
        value = prompt_value(label, default_text).casefold()
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("  Enter y or n.", file=sys.stderr)


def _parse_member_pairs(value: str, pair_count: int) -> list[int]:
    if not value.strip():
        return []

    pairs: list[int] = []
    for item in value.split(","):
        try:
            pair = int(item.strip())
        except ValueError as error:
            raise ValueError(
                "member leaf pairs must be comma-separated numbers"
            ) from error
        if pair < 1 or pair > pair_count:
            raise ValueError(f"member leaf pair must be between 1 and {pair_count}")
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def _configured_int(config: dict[str, str], key: str, default: int) -> int:
    try:
        return int(config.get(key, str(default)))
    except ValueError:
        return default


def _normalize_fabric_mode(value: str) -> str:
    """Map fabric-mode aliases to ``l3ls`` or ``l2ls``."""
    from acta.capacity import normalize_fabric_mode

    mode = normalize_fabric_mode(value)
    if mode is None:
        raise ValueError("fabric mode must be l3ls or l2ls")
    return mode


def _normalize_use_case(value: str) -> str:
    from acta.capacity import normalize_use_case

    case = normalize_use_case(value)
    if case is None:
        raise ValueError("use case must be datacenter or campus")
    return case


def _prompt_fabric_mode(default: str) -> str:
    while True:
        answer = prompt_value(
            "Fabric mode (l3ls=border leaves, l2ls=spine uplinks)",
            default,
        )
        try:
            return _normalize_fabric_mode(answer)
        except ValueError as error:
            print(f"  {error}.", file=sys.stderr)


def _prompt_use_case(default: str) -> str:
    while True:
        answer = prompt_value(
            "Use case (datacenter|campus)",
            default,
        )
        try:
            return _normalize_use_case(answer)
        except ValueError as error:
            print(f"  {error}.", file=sys.stderr)


def _resolve_create_for(requested: str | None, config: dict[str, str]) -> str:
    """Return ``act``, ``clab``, or ``both`` for create output selection."""
    value = (requested or config.get("CREATE_FOR") or "act").strip().casefold()
    if value not in {"act", "clab", "both"}:
        raise ValueError("CREATE_FOR / --for must be act, clab, or both")
    return value


def run_create(
    project_dir: Path,
    *,
    create_for: str | None = None,
    clab_name: str | None = None,
    clab_image: str | None = None,
) -> Path:
    """Interactively collect a fabric spec (1–4 sites) and write its topology."""
    if not sys.stdin.isatty():
        raise RuntimeError("create requires an interactive terminal")

    config_path = project_dir / ".config"
    config = load_config(config_path)
    output_for = _resolve_create_for(create_for, config)

    print("Topology parameters:")
    serial_prefix = prompt_value("Serial prefix")
    hostname_prefix = prompt_value("Hostname prefix", serial_prefix)
    if not serial_prefix.isalnum():
        raise ValueError("serial prefix must be alphanumeric")
    if _PREFIX_RE.fullmatch(hostname_prefix) is None:
        raise ValueError(
            "hostname prefix must be alphanumeric with optional internal dashes"
        )

    dc_count = _prompt_int(
        f"Number of sites (1-{MAX_DC})",
        _configured_int(config, "DC_COUNT", 1),
        minimum=1,
        maximum=MAX_DC,
    )
    multi_dc = dc_count > 1
    cached_use = config.get("USE_CASE") or "datacenter"
    try:
        cached_use = _normalize_use_case(cached_use)
    except ValueError:
        cached_use = "datacenter"
    use_case = _prompt_use_case(cached_use)

    fabric_mode: str | None = None
    if multi_dc:
        cached_mode = config.get("FABRIC_MODE") or "l3ls"
        try:
            cached_mode = _normalize_fabric_mode(cached_mode)
        except ValueError:
            cached_mode = "l3ls"
        fabric_mode = _prompt_fabric_mode(cached_mode)

    spine_label = "Spines per site" if multi_dc else "Number of spines"
    leaf_label = "Leaves per site" if multi_dc else "Number of leaves"
    spine_ceiling = address_limit("spine", multi_dc)
    leaf_ceiling = address_limit("leaf", multi_dc)
    if fabric_mode in {"l2ls", "l2"}:
        spine_ceiling = min(spine_ceiling, 2)

    while True:
        spines = _prompt_int(
            spine_label,
            _configured_int(config, "SPINE_COUNT", 2),
            maximum=spine_ceiling,
        )
        leaves = _prompt_int(
            leaf_label,
            _configured_int(config, "LEAF_COUNT", 4),
            maximum=leaf_ceiling,
        )
        try:
            validate_current_capacity(spines, leaves)
            if fabric_mode in {"l2ls", "l2"} and spines > 2:
                raise ValueError("L2LS fabric spines hard-capped at 2")
            break
        except ValueError as error:
            print(f"  {error}; choose smaller current counts", file=sys.stderr)

    print()
    print(capacity_banner())
    max_spine_ceiling = min(HARD_PORT_MAX, MAX_ADDRESS_SPINES, spine_ceiling)
    if fabric_mode in {"l2ls", "l2"}:
        max_spine_ceiling = min(max_spine_ceiling, 2)
    max_leaf_ceiling = min(HARD_PORT_MAX, leaf_ceiling)
    while True:
        max_spines = _prompt_int(
            "Maximum spines" + (" per site" if multi_dc else ""),
            max(
                spines, _configured_int(config, "MAX_SPINES", min(4, max_spine_ceiling))
            ),
            minimum=spines,
            maximum=max_spine_ceiling,
        )
        max_leaves = _prompt_int(
            "Maximum leaves" + (" per site" if multi_dc else ""),
            max(
                leaves, _configured_int(config, "MAX_LEAVES", min(8, max_leaf_ceiling))
            ),
            minimum=leaves,
            maximum=max_leaf_ceiling,
        )
        max_mleafs_per_pair = _prompt_int(
            "Maximum member leaves per leaf pair",
            max(
                2,
                _configured_int(config, "MEMBER_LEAVES_PER_PAIR", 0),
                _configured_int(config, "MAX_MLEAFS_PER_PAIR", 2),
            ),
            minimum=0,
            maximum=HARD_PORT_MAX,
        )
        capacity = Capacity(
            fabric_mode=fabric_mode,
            max_spines=max_spines,
            max_leaves=max_leaves,
            max_mleafs_per_pair=max_mleafs_per_pair,
            spines=spines,
            leaves=leaves,
            use_case=use_case,
        )
        try:
            validate_create_capacity(capacity)
            break
        except ValueError as error:
            print(f"  {error}; choose smaller capacity limits", file=sys.stderr)

    mlag_pairs = _prompt_yes_no(
        "Pair leaves into MLAG pairs (y/n)",
        config.get("MLAG_PAIRS", "n").casefold() in {"y", "yes"},
    )
    spine_mlag = spines == 2 and _prompt_yes_no(
        "Add MLAG peer-links between spines (y/n)",
        default=True,
    )

    member_leaf_pairs: list[int] = []
    member_leaves_per_pair = 0
    if mlag_pairs and leaves >= 2 and max_mleafs_per_pair:
        pair_count = leaves // 2
        while True:
            pair_text = prompt_value(
                f"Leaf pairs receiving member leaves (1-{pair_count}, comma-separated)",
                config.get("MEMBER_LEAF_PAIRS", ""),
            )
            try:
                member_leaf_pairs = _parse_member_pairs(pair_text, pair_count)
                break
            except ValueError as error:
                print(f"  {error}", file=sys.stderr)
        if member_leaf_pairs:
            member_leaves_per_pair = _prompt_int(
                "Member leaves per selected pair",
                max(
                    1,
                    _configured_int(config, "MEMBER_LEAVES_PER_PAIR", 2),
                ),
                maximum=max_mleafs_per_pair,
            )

    eos_version = prompt_value(
        "EOS version",
        config.get("EOS_VERSION") or DEFAULT_EOS_VERSION,
    )
    spec = FabricSpec(
        hostname_prefix=hostname_prefix,
        serial_prefix=serial_prefix,
        eos_version=eos_version,
        capacity=capacity,
        mlag_pairs=mlag_pairs,
        spine_mlag=spine_mlag,
        member_leaf_pairs=member_leaf_pairs,
        member_leaves_per_pair=member_leaves_per_pair,
        dc_count=dc_count,
    )
    topology = emit_act_yaml(spec)
    output_path = (
        project_dir / f"topology-{serial_prefix}-{date.today().isoformat()}.yml"
    )
    output_path.write_text(topology, encoding="utf-8")
    diagram_path = output_path.with_suffix(".png")
    diagram_written = write_png(topology_to_dot(topology), diagram_path)

    clab_path: Path | None = None
    resolved_clab_name = clab_name
    if output_for in {"clab", "both"}:
        from acta.clab.support import argparse_namespace, materialize_clab_from_act

        # Lab name tracks the fabric hostname prefix (blz2); containers use
        # full ACT hostnames via generate prefix:"" (blz2-A-spine1).
        resolved_clab_name = (clab_name or hostname_prefix or serial_prefix).casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", resolved_clab_name):
            resolved_clab_name = serial_prefix.casefold()
        config["CLAB_NAME"] = resolved_clab_name
        if clab_image:
            config["CLAB_IMAGE"] = clab_image
        clab_args = argparse_namespace(
            config=config,
            name=resolved_clab_name,
            image=clab_image or None,
            mgmt_network=config.get("CLAB_MGMT_NETWORK") or None,
        )
        clab_path = materialize_clab_from_act(output_path, clab_args)

    config.update(
        {
            "DC_COUNT": str(dc_count),
            "SPINE_COUNT": str(spines),
            "LEAF_COUNT": str(leaves),
            "MLAG_PAIRS": "y" if mlag_pairs else "n",
            "EOS_VERSION": eos_version,
            "MEMBER_LEAF_PAIRS": ",".join(map(str, member_leaf_pairs)),
            "MEMBER_LEAVES_PER_PAIR": (
                str(member_leaves_per_pair) if member_leaf_pairs else ""
            ),
            "FABRIC_MODE": fabric_mode or "",
            "USE_CASE": use_case,
            "MAX_SPINES": str(max_spines),
            "MAX_LEAVES": str(max_leaves),
            "MAX_MLEAFS_PER_PAIR": str(max_mleafs_per_pair),
            "CREATE_FOR": output_for,
        }
    )
    if resolved_clab_name:
        config["CLAB_NAME"] = resolved_clab_name
    save_config(config_path, config)
    print(f"Wrote {output_path.name}")
    if diagram_written:
        print(f"Wrote {diagram_path.name}")
    if clab_path is not None:
        print(f"Wrote {clab_path.name}")
    act_name = output_path.name
    print("Next:")
    if output_for in {"act", "both"}:
        print(f"  ACT:          acta.py act upload {act_name}")
    if output_for in {"clab", "both"} and clab_path is not None:
        print(f"  containerlab: acta.py clab deploy {clab_path.name}")
    print(f"  grow later:   acta.py act extend {act_name} --add leaf")
    return output_path

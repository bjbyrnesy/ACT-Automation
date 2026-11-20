from __future__ import annotations

import re
from dataclasses import dataclass

HARD_PORT_MAX = 16
USE_CASES = frozenset({"datacenter", "campus"})
FABRIC_MODES = frozenset({"l3ls", "l2ls"})
REDUNDANCY_MODES = frozenset({"mlag-peer", "evpn-aa"})
BACKBONE_MODES = frozenset({"hub"})

_HEADER_RE = re.compile(
    r"^#\s*capacity:\s*(?P<body>.+)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Capacity:
    fabric_mode: str | None
    max_spines: int
    max_leaves: int
    max_mleafs_per_pair: int
    spines: int
    leaves: int
    use_case: str | None = None
    bb_redundancy: str = "mlag-peer"
    border_redundancy: str = "mlag-peer"
    bb_count: int = 2
    border_count: int = 2
    backbone_mode: str = "hub"


def normalize_fabric_mode(value: str | None) -> str | None:
    """Normalize fabric mode; map legacy ``l2`` / ``campus`` to ``l2ls``."""
    if value is None:
        return None
    folded = value.strip().casefold()
    if folded in {"", "none"}:
        return None
    if folded in {"l3ls", "l3"}:
        return "l3ls"
    if folded in {"l2ls", "l2", "campus"}:
        # ``campus`` was a legacy FABRIC_MODE alias for L2 leaf-spine.
        return "l2ls"
    raise ValueError("fabric mode must be l3ls or l2ls")


def normalize_use_case(value: str | None) -> str | None:
    """Normalize use case to ``datacenter`` or ``campus``."""
    if value is None:
        return None
    folded = value.strip().casefold().replace(" ", "").replace("-", "").replace("_", "")
    if folded in {"", "none"}:
        return None
    if folded in {"datacenter", "dc", "data"}:
        return "datacenter"
    if folded in {"campus"}:
        return "campus"
    raise ValueError("use case must be datacenter or campus")


def normalize_redundancy(value: str | None, *, default: str = "mlag-peer") -> str:
    """Normalize backbone/border redundancy to ``mlag-peer`` or ``evpn-aa``."""
    if value is None or not str(value).strip():
        return default
    folded = str(value).strip().casefold().replace("_", "-")
    if folded in {"mlag-peer", "mlag", "peer"}:
        return "mlag-peer"
    if folded in {"evpn-aa", "evpnaa", "aa", "esi"}:
        return "evpn-aa"
    raise ValueError("redundancy must be mlag-peer or evpn-aa")


def normalize_backbone_mode(value: str | None, *, default: str = "hub") -> str:
    """Normalize backbone mode (near-term: ``hub`` only)."""
    if value is None or not str(value).strip():
        return default
    folded = str(value).strip().casefold()
    if folded in BACKBONE_MODES:
        return folded
    raise ValueError("backbone_mode must be hub")


def _parse_body(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in body.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key] = value
    return out


def parse_capacity_header(text: str) -> Capacity:
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        raise ValueError(
            "missing # capacity: header "
            "(only topologies written by acta.py act create can be extended)"
        )
    merged: dict[str, str] = {}
    for match in matches:
        merged.update(_parse_body(match.group("body")))
    required = (
        "max_spines",
        "max_leaves",
        "max_mleafs_per_pair",
        "spines",
        "leaves",
    )
    missing = [k for k in required if k not in merged]
    if missing:
        raise ValueError(f"capacity header missing keys: {', '.join(missing)}")
    mode = normalize_fabric_mode(merged.get("fabric_mode"))
    use_case = None
    if "use_case" in merged:
        use_case = normalize_use_case(merged.get("use_case"))
    bb_redundancy = normalize_redundancy(merged.get("bb_redundancy"))
    border_redundancy = normalize_redundancy(merged.get("border_redundancy"))
    bb_count = int(merged.get("bb_count") or 2)
    border_count = int(merged.get("border_count") or 2)
    backbone_mode = normalize_backbone_mode(merged.get("backbone_mode"))
    return Capacity(
        fabric_mode=mode,
        max_spines=int(merged["max_spines"]),
        max_leaves=int(merged["max_leaves"]),
        max_mleafs_per_pair=int(merged["max_mleafs_per_pair"]),
        spines=int(merged["spines"]),
        leaves=int(merged["leaves"]),
        use_case=use_case,
        bb_redundancy=bb_redundancy,
        border_redundancy=border_redundancy,
        bb_count=bb_count,
        border_count=border_count,
        backbone_mode=backbone_mode,
    )


def format_capacity_header(cap: Capacity) -> str:
    mode = normalize_fabric_mode(cap.fabric_mode) or "none"
    use_case = normalize_use_case(cap.use_case) or "none"
    bb_redundancy = normalize_redundancy(cap.bb_redundancy)
    border_redundancy = normalize_redundancy(cap.border_redundancy)
    backbone_mode = normalize_backbone_mode(cap.backbone_mode)
    line1 = (
        f"# capacity: fabric_mode={mode} use_case={use_case} "
        f"max_spines={cap.max_spines} "
        f"max_leaves={cap.max_leaves} max_mleafs_per_pair={cap.max_mleafs_per_pair}"
    )
    line2 = (
        f"# capacity: spines={cap.spines} leaves={cap.leaves} "
        f"backbone_mode={backbone_mode} "
        f"bb_redundancy={bb_redundancy} bb_count={cap.bb_count} "
        f"border_redundancy={border_redundancy} border_count={cap.border_count}"
    )
    return f"{line1}\n{line2}\n"


def validate_reserved_port_budget(cap: Capacity) -> None:
    """Ensure all reserved topology slots fit within the hardware port limit."""
    leaf_port_max = cap.max_spines + 2 + cap.max_mleafs_per_pair
    if leaf_port_max > HARD_PORT_MAX:
        raise ValueError(
            f"reserved leaf ports exceed the {HARD_PORT_MAX}-port hard cap"
        )

    spine_port_max = cap.max_leaves + (2 if cap.max_spines >= 2 else 0)
    if spine_port_max > HARD_PORT_MAX:
        raise ValueError(
            f"reserved spine ports exceed the {HARD_PORT_MAX}-port hard cap"
        )


def validate_create_capacity(cap: Capacity) -> None:
    mode = normalize_fabric_mode(cap.fabric_mode)
    if cap.max_leaves < cap.leaves:
        raise ValueError("max_leaves must be >= current leaves")
    if cap.max_spines < cap.spines:
        raise ValueError("max_spines must be >= current spines")
    if mode == "l2ls" and cap.max_spines > 2:
        raise ValueError("L2LS fabric max_spines hard-capped at 2")
    if mode == "l2ls" and cap.spines > 2:
        raise ValueError("L2LS fabric spines hard-capped at 2")
    if cap.max_spines > HARD_PORT_MAX or cap.max_leaves > HARD_PORT_MAX:
        raise ValueError(f"planned width cannot exceed {HARD_PORT_MAX} ports")
    bb_redundancy = normalize_redundancy(cap.bb_redundancy)
    border_redundancy = normalize_redundancy(cap.border_redundancy)
    normalize_backbone_mode(cap.backbone_mode)
    if bb_redundancy == "evpn-aa" and cap.bb_count < 2:
        raise ValueError("evpn-aa backbone requires bb_count >= 2")
    if border_redundancy == "evpn-aa" and cap.border_count < 2:
        raise ValueError("evpn-aa borders require border_count >= 2")
    if cap.bb_count < 1:
        raise ValueError("bb_count must be >= 1")
    if cap.border_count < 1:
        raise ValueError("border_count must be >= 1")
    validate_reserved_port_budget(cap)


def validate_current_capacity(spines: int, leaves: int) -> None:
    """Ensure current counts leave room for the minimum reserved-port budget."""
    capacity = Capacity(None, spines, leaves, 0, spines, leaves)
    try:
        validate_create_capacity(capacity)
    except ValueError as error:
        raise ValueError(f"current counts leave no valid capacity: {error}") from error


def host_attach_roles(use_case: str | None) -> frozenset[str]:
    """Return switch roles allowed for host attachment under ``use_case``."""
    case = normalize_use_case(use_case) or "datacenter"
    if case == "campus":
        return frozenset({"leaf", "mleaf", "border", "spine"})
    return frozenset({"leaf", "mleaf", "border"})

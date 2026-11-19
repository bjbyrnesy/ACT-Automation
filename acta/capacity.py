from __future__ import annotations

import re
from dataclasses import dataclass

HARD_PORT_MAX = 16

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
            "(only topologies written by acta.py create can be extended)"
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
    mode = merged.get("fabric_mode")
    if mode in ("", "none"):
        mode = None
    return Capacity(
        fabric_mode=mode,
        max_spines=int(merged["max_spines"]),
        max_leaves=int(merged["max_leaves"]),
        max_mleafs_per_pair=int(merged["max_mleafs_per_pair"]),
        spines=int(merged["spines"]),
        leaves=int(merged["leaves"]),
    )


def format_capacity_header(cap: Capacity) -> str:
    mode = cap.fabric_mode or "none"
    line1 = (
        f"# capacity: fabric_mode={mode} max_spines={cap.max_spines} "
        f"max_leaves={cap.max_leaves} max_mleafs_per_pair={cap.max_mleafs_per_pair}"
    )
    line2 = f"# capacity: spines={cap.spines} leaves={cap.leaves}"
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
    if cap.max_leaves < cap.leaves:
        raise ValueError("max_leaves must be >= current leaves")
    if cap.max_spines < cap.spines:
        raise ValueError("max_spines must be >= current spines")
    if cap.fabric_mode == "l2" and cap.max_spines > 2:
        raise ValueError("L2 fabric max_spines hard-capped at 2")
    if cap.fabric_mode == "l2" and cap.spines > 2:
        raise ValueError("L2 fabric spines hard-capped at 2")
    if cap.max_spines > HARD_PORT_MAX or cap.max_leaves > HARD_PORT_MAX:
        raise ValueError(f"planned width cannot exceed {HARD_PORT_MAX} ports")
    validate_reserved_port_budget(cap)


def validate_current_capacity(spines: int, leaves: int) -> None:
    """Ensure current counts leave room for the minimum reserved-port budget."""
    capacity = Capacity(None, spines, leaves, 0, spines, leaves)
    try:
        validate_create_capacity(capacity)
    except ValueError as error:
        raise ValueError(f"current counts leave no valid capacity: {error}") from error

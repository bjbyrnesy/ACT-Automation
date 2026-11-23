"""Attach-target inventory for the Web UI (MLAG pairs + member leaves)."""

from __future__ import annotations

import re
from typing import Any

from acta.extend import leaf_mlag_pairs, member_leaf_parents, member_leaves
from acta.site_names import fabric_prefix_from_names, parse_fabric_identity

_NODE_KEY_RE = re.compile(r"^  - ([A-Za-z0-9][\w.-]*):\s*$", re.MULTILINE)


def _site_of(name: str, *, prefix: str | None) -> str | None:
    parsed = parse_fabric_identity(name, prefix=prefix)
    if parsed is None:
        return None
    site, _role, _index = parsed
    return site


def attach_targets_from_yaml(text: str) -> dict[str, Any]:
    """Return 1-based MLAG / mleaf choices with human-readable labels.

    Index order matches ``acta attach --mlag-pair`` / ``--mleaf`` and
    ``acta show``.
    """
    pairs = leaf_mlag_pairs(text)
    mleaf_names = member_leaves(text)
    # Prefer bb* when discovering prefix so named sites (msp/mso) parse correctly.
    prefix = fabric_prefix_from_names(_NODE_KEY_RE.findall(text))

    mlag_pairs: list[dict[str, Any]] = []
    for index, (leaf_a, leaf_b) in enumerate(pairs, start=1):
        site = _site_of(leaf_a, prefix=prefix)
        site_bit = f"Site {site}" if site else "fabric"
        mlag_pairs.append(
            {
                "index": index,
                "leaf_a": leaf_a,
                "leaf_b": leaf_b,
                "site": site,
                "label": f"{index} · {site_bit} · {leaf_a} ↔ {leaf_b}",
            }
        )

    mleafs: list[dict[str, Any]] = []
    for index, name in enumerate(mleaf_names, start=1):
        site = _site_of(name, prefix=prefix)
        site_bit = f"Site {site}" if site else "fabric"
        pair_index, parents = member_leaf_parents(text, name)
        parent_bit = ""
        if parents:
            parent_bit = f" · uplinks {parents[0]} / {parents[1]}"
        pair_bit = f" · pair {pair_index}" if pair_index is not None else ""
        mleafs.append(
            {
                "index": index,
                "name": name,
                "site": site,
                "mlag_pair": pair_index,
                "leaf_a": parents[0] if parents else None,
                "leaf_b": parents[1] if parents else None,
                "label": f"{index} · {site_bit} · {name}{pair_bit}{parent_bit}",
            }
        )

    return {"mlag_pairs": mlag_pairs, "mleafs": mleafs}

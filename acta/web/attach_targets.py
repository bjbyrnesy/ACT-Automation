"""Attach-target inventory for the Web UI (MLAG pairs, mleafs, campus spines)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from acta.attach import attached_hosts
from acta.capacity import host_attach_roles, parse_capacity_header
from acta.extend import leaf_mlag_pairs, member_leaf_parents, member_leaves
from acta.site_names import fabric_prefix_from_names, parse_fabric_identity

_NODE_KEY_RE = re.compile(r"^  - ([A-Za-z0-9][\w.-]*):\s*$", re.MULTILINE)
_SPINE_RE = re.compile(r"(?:^|-)spine(?P<index>[1-9]\d*)$")


def _site_of(name: str, *, prefix: str | None) -> str | None:
    parsed = parse_fabric_identity(name, prefix=prefix)
    if parsed is None:
        return None
    site, _role, _index = parsed
    return site


def _spine_index(name: str) -> int:
    match = _SPINE_RE.search(name)
    return int(match.group("index")) if match else 0


def attach_targets_from_yaml(text: str) -> dict[str, Any]:
    """Return 1-based MLAG / mleaf / spine choices with human-readable labels.

    Index order matches ``acta attach --mlag-pair`` / ``--mleaf`` and
    ``acta show``. Spines (and spine MLAG pairs) appear only when the
    topology use case allows host attach to spine (campus).
    """
    pairs = leaf_mlag_pairs(text)
    mleaf_names = member_leaves(text)
    # Prefer bb* when discovering prefix so named sites (msp/mso) parse correctly.
    node_names = _NODE_KEY_RE.findall(text)
    prefix = fabric_prefix_from_names(node_names)

    try:
        use_case = parse_capacity_header(text).use_case
    except ValueError:
        use_case = None
    allow_spine = "spine" in host_attach_roles(use_case)

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

    spines: list[dict[str, Any]] = []
    spine_pairs: list[dict[str, Any]] = []
    if allow_spine:
        by_site: dict[str | None, list[str]] = defaultdict(list)
        for name in node_names:
            if _SPINE_RE.search(name):
                by_site[_site_of(name, prefix=prefix)].append(name)
        pair_index = 0
        for site in sorted(
            by_site.keys(), key=lambda value: (value is None, value or "")
        ):
            names = sorted(by_site[site], key=_spine_index)
            site_bit = f"Site {site}" if site else "fabric"
            for name in names:
                spines.append(
                    {
                        "name": name,
                        "site": site,
                        "label": f"{site_bit} · {name}",
                    }
                )
            if len(names) == 2:
                pair_index += 1
                spine_a, spine_b = names
                spine_pairs.append(
                    {
                        "index": pair_index,
                        "spine_a": spine_a,
                        "spine_b": spine_b,
                        "site": site,
                        "label": f"{pair_index} · {site_bit} · {spine_a} ↔ {spine_b}",
                    }
                )

    return {
        "mlag_pairs": mlag_pairs,
        "mleafs": mleafs,
        "spines": spines,
        "spine_pairs": spine_pairs,
        "hosts": attached_hosts(text),
        "use_case": use_case,
    }

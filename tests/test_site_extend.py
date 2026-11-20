from __future__ import annotations

import re

from acta.capacity import Capacity, parse_capacity_header
from acta.create import FabricSpec, emit_act_yaml
from acta.site_extend import ensure_multi_dc
from acta.topology import parse_connections


def _single(fabric_mode: str = "l3ls", **cap_kwargs) -> str:
    capacity = Capacity(
        fabric_mode=fabric_mode,
        max_spines=2 if fabric_mode == "l2ls" else 4,
        max_leaves=8,
        max_mleafs_per_pair=0,
        spines=2,
        leaves=2,
        **cap_kwargs,
    )
    return emit_act_yaml(
        FabricSpec(
            hostname_prefix="demo",
            serial_prefix="demo",
            eos_version="4.35.4M",
            capacity=capacity,
            mlag_pairs=True,
            spine_mlag=False,
            member_leaf_pairs=[],
            member_leaves_per_pair=0,
        )
    )


def _serials(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"^  - (?P<name>[^:\n]+):\n(?:      .+\n)*?"
        r"      serial_number: (?P<serial>\S+)\n",
        re.MULTILINE,
    )
    return {
        match.group("name"): match.group("serial") for match in pattern.finditer(text)
    }


def _macs(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"^  - (?P<name>[^:\n]+):\n(?:      .+\n)*?"
        r"      system_mac_address: (?P<mac>\S+)\n",
        re.MULTILINE,
    )
    return {match.group("name"): match.group("mac") for match in pattern.finditer(text)}


def test_promote_single_site_to_named_site_with_bb_hub():
    original = _single("l3ls")
    promoted = ensure_multi_dc(original, first_site="aus")
    assert "demo-aus-spine1:" in promoted
    assert "demo-spine1:" not in promoted
    assert "demo-bb1:" in promoted
    assert "demo-aus-border1:" in promoted
    cap = parse_capacity_header(promoted)
    assert cap.bb_redundancy == "mlag-peer"
    assert cap.border_count == 2
    links = {(c.a_node, c.b_node) for c in parse_connections(promoted)}
    assert ("demo-aus-spine1", "demo-aus-leaf1") in links or (
        "demo-aus-leaf1",
        "demo-aus-spine1",
    ) in {
        (a, b)
        for a, b, *_ in [(c.a_node, c.b_node) for c in parse_connections(promoted)]
    }
    endpoints = {frozenset((c.a_node, c.b_node)) for c in parse_connections(promoted)}
    assert frozenset(("demo-aus-spine1", "demo-aus-leaf1")) in endpoints
    assert frozenset(("demo-aus-border1", "demo-bb1")) in endpoints
    assert frozenset(("demo-bb1", "demo-bb2")) in endpoints


def test_promote_preserves_serial_and_mac_by_default():
    original = _single("l3ls")
    old_serials = _serials(original)
    old_macs = _macs(original)
    promoted = ensure_multi_dc(original, first_site="aus")
    new_serials = _serials(promoted)
    new_macs = _macs(promoted)
    assert new_serials["demo-aus-spine1"] == old_serials["demo-spine1"]
    assert new_macs["demo-aus-spine1"] == old_macs["demo-spine1"]
    assert new_serials["demo-aus-leaf2"] == old_serials["demo-leaf2"]


def test_promote_rekey_identity_rewrites_serial_and_mac():
    original = _single("l3ls")
    old_serials = _serials(original)
    old_macs = _macs(original)
    promoted = ensure_multi_dc(original, first_site="aus", rekey_identity=True)
    new_serials = _serials(promoted)
    new_macs = _macs(promoted)
    assert new_serials["demo-aus-spine1"] != old_serials["demo-spine1"]
    assert new_macs["demo-aus-spine1"] != old_macs["demo-spine1"]
    assert new_serials["demo-aus-spine1"] == "demo-aus-spine1"


def test_promote_mlag_peer_has_peer_link_evpn_aa_does_not():
    mlag = ensure_multi_dc(_single("l3ls"), first_site="A")
    aa = ensure_multi_dc(
        _single("l3ls", bb_redundancy="evpn-aa", border_redundancy="evpn-aa"),
        first_site="A",
        bb_redundancy="evpn-aa",
        border_redundancy="evpn-aa",
        bb_count=2,
        border_count=2,
    )
    mlag_peers = {
        frozenset((c.a_node, c.b_node))
        for c in parse_connections(mlag)
        if "bb" in c.a_node and "bb" in c.b_node
    }
    aa_peers = {
        frozenset((c.a_node, c.b_node))
        for c in parse_connections(aa)
        if "bb" in c.a_node and "bb" in c.b_node
    }
    assert frozenset(("demo-bb1", "demo-bb2")) in mlag_peers
    assert frozenset(("demo-bb1", "demo-bb2")) not in aa_peers
    border_peers = {
        frozenset((c.a_node, c.b_node))
        for c in parse_connections(aa)
        if "border" in c.a_node and "border" in c.b_node
    }
    assert not border_peers


def test_promote_l2_wires_spines_to_bb():
    promoted = ensure_multi_dc(_single("l2ls"), first_site="dfw")
    assert "demo-dfw-spine1:" in promoted
    assert "-border" not in promoted
    endpoints = {frozenset((c.a_node, c.b_node)) for c in parse_connections(promoted)}
    assert frozenset(("demo-dfw-spine1", "demo-bb1")) in endpoints


def test_ensure_multi_dc_is_noop_for_existing_multi_dc():
    multi = emit_act_yaml(
        FabricSpec(
            hostname_prefix="demo",
            serial_prefix="demo",
            eos_version="4.35.4M",
            capacity=Capacity("l3ls", 4, 8, 0, 2, 2),
            mlag_pairs=True,
            spine_mlag=False,
            member_leaf_pairs=[],
            member_leaves_per_pair=0,
            dc_count=2,
        )
    )
    assert ensure_multi_dc(multi, first_site="aus") == multi

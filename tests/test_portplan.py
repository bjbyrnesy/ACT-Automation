import pytest

from acta.capacity import Capacity
from acta.portplan import PortPlan, site_ordinal


def _cap(**kwargs) -> Capacity:
    base = {
        "fabric_mode": "l3ls",
        "max_spines": 4,
        "max_leaves": 8,
        "max_mleafs_per_pair": 2,
        "spines": 2,
        "leaves": 4,
    }
    base.update(kwargs)
    return Capacity(**base)


def test_mesh_ports_use_indices():
    plan = PortPlan(_cap())
    assert plan.spine_to_leaf_port(3) == 3
    assert plan.leaf_to_spine_port(2) == 2


def test_service_ports_sit_after_reserved_blocks():
    plan = PortPlan(_cap(max_spines=4, max_leaves=8))
    assert plan.leaf_mlag_ports() == (5, 6)
    assert plan.leaf_mleaf_port(1) == 7
    assert plan.leaf_mleaf_port(2) == 8
    assert plan.spine_mlag_ports() == (9, 10)


def test_next_free_prefers_planned_then_scans():
    plan = PortPlan(_cap())
    assert plan.next_free_port({1, 2, 3}, prefer=4) == 4
    assert plan.next_free_port({1, 2, 3, 4}, prefer=4) == 5


def test_next_free_raises_at_hard_cap():
    plan = PortPlan(_cap())
    used = set(range(1, 17))
    with pytest.raises(ValueError, match="16"):
        plan.next_free_port(used)


def test_multi_dc_uplinks_sit_after_reserved_blocks():
    plan = PortPlan(_cap(max_spines=4, max_leaves=8))
    assert plan.spine_mlag_ports() == (9, 10)
    assert plan.spine_uplink_ports() == (11, 12)
    assert plan.border_mlag_ports() == (5, 6)
    assert plan.border_bb_ports() == (7, 8)
    assert plan.bb_border_port(1, 2) == 4
    # Peer reserved after max attach sites (not current dc_count).
    assert plan.bb_peer_port(2) == plan.bb_peer_port(8)
    assert plan.bb_peer_port() == 15


def test_l2_backbone_ports_use_reserved_spine_width():
    plan = PortPlan(_cap(fabric_mode="l2ls", max_spines=2))
    assert plan.bb_spine_port(1, 1) == 3
    assert plan.bb_peer_port(3) == 15
    assert plan.max_attach_sites() == 7


def test_site_ordinal_is_sorted_name_order():
    sites = ("dfw", "aus", "ord")
    assert site_ordinal("aus", sites) == 0
    assert site_ordinal("dfw", sites) == 1
    assert site_ordinal("ord", sites) == 2
    assert PortPlan(_cap()).bb_border_port(site_ordinal("aus", sites), 1) == 1
    assert PortPlan(_cap()).bb_border_port(site_ordinal("ord", sites), 2) == 6


def test_bb_ports_cover_eight_sites_without_peer_collision():
    plan = PortPlan(_cap(bb_redundancy="evpn-aa", border_count=2, bb_count=2))
    assert plan.max_attach_sites() == 8
    assert plan.bb_border_port(7, 2) == 16
    with pytest.raises(ValueError, match="backbone capacity|hard max"):
        plan.bb_border_port(8, 1)


def test_evpn_aa_set_size_three_scales_uplinks():
    plan = PortPlan(
        _cap(
            bb_redundancy="evpn-aa",
            border_redundancy="evpn-aa",
            bb_count=3,
            border_count=3,
            max_spines=4,
            max_leaves=8,
        )
    )
    assert plan.spine_uplink_ports() == (11, 12, 13)
    assert plan.border_bb_ports() == (7, 8, 9)
    assert plan.bb_border_port(0, 3) == 3
    assert plan.bb_border_port(1, 1) == 4
    with pytest.raises(ValueError, match="bb peer"):
        plan.bb_peer_port()


def test_peer_port_stable_when_site_count_grows():
    plan = PortPlan(_cap())
    assert plan.bb_peer_port(2) == plan.bb_peer_port(7)
    # Site ports stay below the reserved peer.
    assert plan.bb_border_port(6, 2) < plan.bb_peer_port()


def test_bb_port_exhaustion_is_clear():
    plan = PortPlan(_cap(border_count=2))
    with pytest.raises(ValueError, match="Ethernet|hard max|capacity"):
        plan.bb_border_port(plan.max_attach_sites(), 1)


def test_allocate_port_overrun_goes_above_reserved_and_skips_protected():
    plan = PortPlan(_cap(max_spines=4, max_leaves=8))
    protected = plan.leaf_protected_ports()
    top = plan.leaf_reserved_top()
    assert plan.allocate_port({1, 2}, 5, reserved_top=top, protected=protected) == 5
    assert (
        plan.allocate_port(
            {1, 2}, 5, reserved_top=top, protected=protected, overrun=True
        )
        == top + 1
    )
    full_above = set(range(top + 1, 17))
    assert (
        plan.allocate_port(
            full_above, 5, reserved_top=top, protected=protected, overrun=True
        )
        == 1
    )
    with pytest.raises(ValueError, match="16"):
        plan.allocate_port(
            full_above | {1, 2, 3, 4},
            5,
            reserved_top=top,
            protected=protected,
            overrun=True,
        )

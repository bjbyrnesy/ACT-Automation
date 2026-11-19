import pytest

from acta.capacity import Capacity
from acta.portplan import PortPlan


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
    assert plan.bb_peer_port(2) == 5


def test_l2_backbone_ports_use_reserved_spine_width():
    plan = PortPlan(_cap(fabric_mode="l2", max_spines=2))
    assert plan.bb_spine_port(1, 1) == 3
    assert plan.bb_peer_port(3) == 7


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

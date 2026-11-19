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

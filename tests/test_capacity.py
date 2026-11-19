import pytest

from acta.capacity import (
    HARD_PORT_MAX,
    Capacity,
    format_capacity_header,
    parse_capacity_header,
    validate_create_capacity,
    validate_current_capacity,
)


def test_hard_port_max_is_16():
    assert HARD_PORT_MAX == 16


def test_round_trip_header():
    cap = Capacity(
        fabric_mode="l3ls",
        max_spines=4,
        max_leaves=8,
        max_mleafs_per_pair=2,
        spines=2,
        leaves=4,
    )
    text = format_capacity_header(cap)
    assert "max_spines=4" in text
    got = parse_capacity_header(text)
    assert got == cap


def test_parse_missing_header_raises():
    with pytest.raises(ValueError, match=r"capacity.*acta\.py create"):
        parse_capacity_header("nodes:\n")


def test_validate_rejects_max_leaves_below_current():
    cap = Capacity(
        fabric_mode=None,
        max_spines=2,
        max_leaves=2,
        max_mleafs_per_pair=0,
        spines=2,
        leaves=4,
    )
    with pytest.raises(ValueError, match="max_leaves"):
        validate_create_capacity(cap)


def test_validate_l2_rejects_spines_above_2():
    cap = Capacity(
        fabric_mode="l2",
        max_spines=3,
        max_leaves=4,
        max_mleafs_per_pair=0,
        spines=2,
        leaves=4,
    )
    with pytest.raises(ValueError, match="L2"):
        validate_create_capacity(cap)


def test_validate_rejects_reserved_leaf_ports_above_hard_cap():
    cap = Capacity(
        fabric_mode=None,
        max_spines=16,
        max_leaves=8,
        max_mleafs_per_pair=1,
        spines=2,
        leaves=4,
    )

    with pytest.raises(ValueError, match="reserved leaf ports.*16-port hard cap"):
        validate_create_capacity(cap)


def test_validate_current_capacity_rejects_impossible_spine_count():
    with pytest.raises(
        ValueError, match="current counts leave no valid capacity.*16-port hard cap"
    ):
        validate_current_capacity(spines=15, leaves=2)

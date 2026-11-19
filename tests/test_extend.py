from pathlib import Path

import pytest

from acta.capacity import Capacity, parse_capacity_header
from acta.create import FabricSpec, emit_act_yaml
from acta.extend import extend_topology
from acta.topology import parse_connections


def _write_base(tmp_path: Path) -> Path:
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode=None,
            max_spines=4,
            max_leaves=8,
            max_mleafs_per_pair=2,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
    )
    path = tmp_path / "topology-demo.yml"
    path.write_text(emit_act_yaml(spec))
    return path


def test_add_leaf_preserves_existing_endpoints(tmp_path: Path):
    path = _write_base(tmp_path)
    before = {
        (connection.a_node, connection.a_port, connection.b_node, connection.b_port)
        for connection in parse_connections(path.read_text())
    }
    extend_topology(path, add="leaf")
    after_connections = parse_connections(path.read_text())
    after = {
        (connection.a_node, connection.a_port, connection.b_node, connection.b_port)
        for connection in after_connections
    }
    assert before <= after
    assert {
        endpoint
        for endpoint in after - before
        if "demo-leaf3" in (endpoint[0], endpoint[2])
    } == {
        ("demo-spine1", 3, "demo-leaf3", 1),
        ("demo-spine2", 3, "demo-leaf3", 2),
    }
    assert parse_capacity_header(path.read_text()).leaves == 3


def test_warns_when_leaf_exceeds_soft_capacity(tmp_path: Path):
    with pytest.warns(UserWarning, match=r"leaf9 exceeds.*max_leaves=8"):
        extend_topology(_write_base(tmp_path), add="leaf", count=7)


def test_add_spine_meshes_to_all_leaves_and_preserves_endpoints(tmp_path: Path):
    path = _write_base(tmp_path)
    before = {
        (connection.a_node, connection.a_port, connection.b_node, connection.b_port)
        for connection in parse_connections(path.read_text())
    }

    extend_topology(path, add="spine")

    after = {
        (connection.a_node, connection.a_port, connection.b_node, connection.b_port)
        for connection in parse_connections(path.read_text())
    }
    assert before <= after
    assert after - before == {
        ("demo-spine3", 1, "demo-leaf1", 3),
        ("demo-spine3", 2, "demo-leaf2", 3),
    }
    assert parse_capacity_header(path.read_text()).spines == 3


def test_add_pair_adds_two_meshed_leaves_and_peer_links(tmp_path: Path):
    path = _write_base(tmp_path)

    extend_topology(path, add="pair")

    connections = parse_connections(path.read_text())
    added = [
        connection
        for connection in connections
        if "demo-leaf3" in (connection.a_node, connection.b_node)
        or "demo-leaf4" in (connection.a_node, connection.b_node)
    ]
    assert len(added) == 6
    assert {
        (
            connection.a_node,
            connection.a_port,
            connection.b_node,
            connection.b_port,
        )
        for connection in added
        if {connection.a_node, connection.b_node} == {"demo-leaf3", "demo-leaf4"}
    } == {
        ("demo-leaf3", 5, "demo-leaf4", 5),
        ("demo-leaf3", 6, "demo-leaf4", 6),
    }
    assert parse_capacity_header(path.read_text()).leaves == 4


def test_add_mleaf_uses_next_slot_under_pair(tmp_path: Path):
    path = _write_base(tmp_path)

    extend_topology(path, add="mleaf", pair=1, count=2)

    connections = parse_connections(path.read_text())
    assert {
        (
            connection.a_node,
            connection.a_port,
            connection.b_node,
            connection.b_port,
        )
        for connection in connections
        if connection.a_node.startswith("demo-mleaf")
    } == {
        ("demo-mleaf1", 1, "demo-leaf1", 7),
        ("demo-mleaf1", 2, "demo-leaf2", 7),
        ("demo-mleaf2", 1, "demo-leaf1", 8),
        ("demo-mleaf2", 2, "demo-leaf2", 8),
    }


def test_pair_index_uses_discovered_peer_links_after_standalone_leaf(
    tmp_path: Path,
):
    path = _write_base(tmp_path)
    extend_topology(path, add="leaf")
    extend_topology(path, add="pair")

    extend_topology(path, add="mleaf", pair=2)

    connections = parse_connections(path.read_text())
    assert {
        connection.b_node
        for connection in connections
        if connection.a_node == "demo-mleaf1"
    } == {"demo-leaf4", "demo-leaf5"}


def test_unrelated_mleaf_substring_does_not_consume_pair_slot(tmp_path: Path):
    path = _write_base(tmp_path)
    text = path.read_text()
    path.write_text(
        f"{text.rstrip()}\n"
        "  - connection: [demo-not-mleaf-backup:Ethernet1, "
        "demo-leaf1:Ethernet10]\n"
    )

    extend_topology(path, add="mleaf", pair=1)

    assert ("demo-mleaf1", 1, "demo-leaf1", 7) in {
        (
            connection.a_node,
            connection.a_port,
            connection.b_node,
            connection.b_port,
        )
        for connection in parse_connections(path.read_text())
    }


def test_l2_rejects_third_spine(tmp_path: Path):
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode="l2",
            max_spines=2,
            max_leaves=8,
            max_mleafs_per_pair=0,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
    )
    path = tmp_path / "topology-l2.yml"
    path.write_text(emit_act_yaml(spec))

    with pytest.raises(ValueError, match="L2"):
        extend_topology(path, add="spine")


def test_mleaf_requires_pair(tmp_path: Path):
    with pytest.raises(ValueError, match="pair"):
        extend_topology(_write_base(tmp_path), add="mleaf")


def test_mleaf_rejects_pair_without_two_leaves(tmp_path: Path):
    with pytest.raises(ValueError, match="pair 2"):
        extend_topology(_write_base(tmp_path), add="mleaf", pair=2)


def test_warns_when_spine_exceeds_soft_capacity(tmp_path: Path):
    with pytest.warns(UserWarning, match=r"spine5 exceeds.*max_spines=4"):
        extend_topology(_write_base(tmp_path), add="spine", count=3)


def test_warns_when_mleaf_exceeds_soft_capacity(tmp_path: Path):
    with pytest.warns(
        UserWarning, match=r"mleaf slot 3 exceeds.*max_mleafs_per_pair=2"
    ):
        extend_topology(_write_base(tmp_path), add="mleaf", pair=1, count=3)


def _write_multi_dc(tmp_path: Path, fabric_mode: str = "l3ls") -> Path:
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode=fabric_mode,
            max_spines=2 if fabric_mode == "l2" else 4,
            max_leaves=8,
            max_mleafs_per_pair=2,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
        dc_count=2,
    )
    path = tmp_path / f"topology-multi-{fabric_mode}.yml"
    path.write_text(emit_act_yaml(spec))
    return path


def _endpoint_set(path: Path) -> set[tuple[str, int, str, int]]:
    return {
        (c.a_node, c.a_port, c.b_node, c.b_port)
        for c in parse_connections(path.read_text())
    }


def test_multi_dc_extend_requires_site(tmp_path: Path):
    with pytest.raises(ValueError, match="--site"):
        extend_topology(_write_multi_dc(tmp_path), add="leaf")


def test_multi_dc_extend_rejects_unknown_site(tmp_path: Path):
    with pytest.raises(ValueError, match="site Z"):
        extend_topology(_write_multi_dc(tmp_path), add="leaf", site="Z")


def test_single_dc_extend_rejects_site(tmp_path: Path):
    with pytest.raises(ValueError, match="single-site"):
        extend_topology(_write_base(tmp_path), add="leaf", site="A")


def test_multi_dc_extend_site_b_leaf_leaves_site_a_unchanged(tmp_path: Path):
    path = _write_multi_dc(tmp_path)
    before = _endpoint_set(path)
    text_before = path.read_text()

    extend_topology(path, add="leaf", site="B")

    after = _endpoint_set(path)
    assert before <= after
    added = after - before
    assert added == {
        ("demo-B-spine1", 3, "demo-B-leaf3", 1),
        ("demo-B-spine2", 3, "demo-B-leaf3", 2),
    }
    text = path.read_text()
    assert "demo-B-leaf3:" in text
    assert "demo-A-leaf3:" not in text
    assert "ip_addr: 192.168.0.79/24" in text  # B base 66 + 11 + 3 - 1
    assert "serial_number: demo-B-leaf3" in text
    # Capacity header is per-site baseline; unchanged for multi-DC.
    assert parse_capacity_header(text) == parse_capacity_header(text_before)
    # A can still grow independently to leaf3.
    extend_topology(path, add="leaf", site="A")
    assert "demo-A-leaf3:" in path.read_text()


def test_multi_dc_extend_pair_and_mleaf_scoped_to_site(tmp_path: Path):
    path = _write_multi_dc(tmp_path)
    extend_topology(path, add="mleaf", pair=1, site="B")
    links = _endpoint_set(path)
    assert ("demo-B-mleaf1", 1, "demo-B-leaf1", 7) in links
    assert ("demo-B-mleaf1", 2, "demo-B-leaf2", 7) in links
    assert not any("A-mleaf" in item[0] for item in links)
    extend_topology(path, add="pair", site="A")
    assert "demo-A-leaf3:" in path.read_text()
    assert "demo-B-leaf3:" not in path.read_text()


def test_multi_dc_l3ls_spine_links_to_borders(tmp_path: Path):
    path = _write_multi_dc(tmp_path)
    before = _endpoint_set(path)
    extend_topology(path, add="spine", site="B")
    added = _endpoint_set(path) - before
    assert ("demo-B-border1", 3, "demo-B-spine3", 11) in added
    assert ("demo-B-border2", 3, "demo-B-spine3", 12) in added
    assert ("demo-B-spine3", 1, "demo-B-leaf1", 3) in added
    assert all("demo-A-" not in item[0] + item[2] for item in added)


def test_multi_dc_l2_spine_limit_is_per_site(tmp_path: Path):
    path = _write_multi_dc(tmp_path, "l2")
    with pytest.raises(ValueError, match="L2"):
        extend_topology(path, add="spine", site="B")

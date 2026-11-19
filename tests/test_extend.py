from datetime import date
from pathlib import Path

import pytest

from acta.capacity import Capacity, parse_capacity_header
from acta.create import FabricSpec, emit_act_yaml
from acta.extend import extend_topology
from acta.topology import parse_connections


def _write_base(tmp_path: Path, **capacity: int) -> Path:
    cap = {
        "fabric_mode": None,
        "max_spines": 4,
        "max_leaves": 8,
        "max_mleafs_per_pair": 2,
        "spines": 2,
        "leaves": 2,
    }
    cap.update(capacity)
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(**cap),
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


def test_leaf_exceeding_soft_capacity_is_reported_in_result(tmp_path: Path):
    result = extend_topology(_write_base(tmp_path), add="leaf", count=7)
    assert any("leaf9 exceeds" in w and "max_leaves=8" in w for w in result.warnings)
    assert result.added_nodes[-1] == "demo-leaf9"
    assert result.free_leaves == 0


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


def test_spine_exceeding_soft_capacity_is_reported_in_result(tmp_path: Path):
    result = extend_topology(_write_base(tmp_path), add="spine", count=3)
    assert any("spine5 exceeds" in w and "max_spines=4" in w for w in result.warnings)
    assert result.added_nodes == ("demo-spine3", "demo-spine4", "demo-spine5")


def test_mleaf_exceeding_soft_capacity_is_reported_in_result(tmp_path: Path):
    result = extend_topology(_write_base(tmp_path), add="mleaf", pair=1, count=3)
    assert any(
        "mleaf slot 3 exceeds" in w and "max_mleafs_per_pair=2" in w
        for w in result.warnings
    )


def test_result_reports_added_nodes_and_free_slots(tmp_path: Path):
    path = _write_base(tmp_path)
    result = extend_topology(path, add="mleaf", pair=1)
    assert result.path == path
    assert result.added_nodes == ("demo-mleaf1",)
    assert result.warnings == ()
    assert (result.free_leaves, result.free_spines) == (6, 2)
    assert result.free_mleaf_slots == (1,)
    assert "leaves 6" in result.free_slots_summary()
    assert "pair 1: 1" in result.free_slots_summary()


def _ports_by_node(path: Path) -> dict[str, list[int]]:
    ports: dict[str, list[int]] = {}
    for c in parse_connections(path.read_text()):
        ports.setdefault(c.a_node, []).append(c.a_port)
        ports.setdefault(c.b_node, []).append(c.b_port)
    return ports


def test_spine_overrun_does_not_take_mlag_or_mleaf_ports(tmp_path: Path):
    path = _write_base(tmp_path, max_spines=2)
    extend_topology(path, add="spine")
    extend_topology(path, add="pair")
    extend_topology(path, add="mleaf", pair=2)
    ports = _ports_by_node(path)
    for node, node_ports in ports.items():
        assert len(node_ports) == len(set(node_ports)), node
    # leaf1 MLAG ports (3, 4) and member-leaf slots (5, 6) stay planned.
    links = _endpoint_set(path)
    assert ("demo-leaf1", 3, "demo-leaf2", 3) in links
    assert ("demo-leaf1", 4, "demo-leaf2", 4) in links
    assert ("demo-spine3", 1, "demo-leaf1", 7) in links
    assert {
        ("demo-mleaf1", 1, "demo-leaf3", 5),
        ("demo-mleaf1", 2, "demo-leaf4", 5),
    } <= links


def test_leaf_overrun_ports_sit_above_spine_reserved_blocks(tmp_path: Path):
    path = _write_base(tmp_path)
    extend_topology(path, add="leaf", count=7)
    links = _endpoint_set(path)
    # max_leaves=8 -> spine ports 9, 10 are the reserved MLAG block.
    assert ("demo-spine1", 11, "demo-leaf9", 1) in links
    assert ("demo-spine2", 11, "demo-leaf9", 2) in links


def test_pair_discovered_when_peer_links_use_non_planned_ports(tmp_path: Path):
    path = _write_base(tmp_path)
    text = path.read_text().replace(
        "demo-leaf1:Ethernet5, demo-leaf2:Ethernet5",
        "demo-leaf1:Ethernet12, demo-leaf2:Ethernet12",
    )
    path.write_text(text)
    extend_topology(path, add="mleaf", pair=1)
    assert ("demo-mleaf1", 1, "demo-leaf1", 7) in _endpoint_set(path)


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


def _snapshot(directory: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(directory.iterdir()) if p.is_file()}


def test_extend_hitting_hard_port_cap_writes_nothing(tmp_path: Path):
    path = _write_base(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(ValueError, match="no free Ethernet ports"):
        extend_topology(path, add="leaf", count=15)

    assert _snapshot(tmp_path) == before


def test_out_refuses_existing_path_and_leaves_both_untouched(tmp_path: Path):
    path = _write_base(tmp_path)
    existing = tmp_path / "keep.yml"
    existing.write_text("keep me\n")
    before = _snapshot(tmp_path)

    with pytest.raises(FileExistsError, match="already exists"):
        extend_topology(path, add="leaf", out=existing)

    assert _snapshot(tmp_path) == before


def test_out_and_new_are_mutually_exclusive(tmp_path: Path):
    with pytest.raises(ValueError, match="mutually exclusive"):
        extend_topology(
            _write_base(tmp_path), add="leaf", out=tmp_path / "x.yml", new=True
        )


def test_new_writes_unique_dated_name_and_keeps_input(tmp_path: Path):
    path = _write_base(tmp_path)
    original = path.read_text()
    today = date.today().isoformat()

    first = extend_topology(path, add="leaf", new=True).path
    second = extend_topology(path, add="leaf", new=True).path

    assert first.name == f"topology-demo-{today}.yml"
    assert second.name == f"topology-demo-{today}-2.yml"
    assert path.read_text() == original
    assert "demo-leaf3:" in first.read_text()


def test_new_does_not_double_date_an_already_dated_stem(tmp_path: Path):
    path = tmp_path / "topology-demo-2026-01-02.yml"
    path.write_text(_write_base(tmp_path).read_text())
    today = date.today().isoformat()

    result = extend_topology(path, add="leaf", new=True)

    assert result.path.name == f"topology-demo-{today}.yml"


def _write_multi_dc_members(tmp_path: Path) -> Path:
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode="l3ls",
            max_spines=2,
            max_leaves=8,
            max_mleafs_per_pair=2,
            spines=2,
            leaves=4,
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[1, 2],
        member_leaves_per_pair=2,
        dc_count=2,
    )
    path = tmp_path / "topology-multi-members.yml"
    path.write_text(emit_act_yaml(spec))
    return path


def test_multi_dc_mleaf_beyond_per_site_ip_block_is_rejected_atomically(
    tmp_path: Path,
):
    path = _write_multi_dc_members(tmp_path)
    before = _snapshot(tmp_path)

    # Site B already has mleaf1-4; mleaf13 would spill past its 12-address block.
    with pytest.raises(ValueError, match=r"mleaf13 exceeds.*limit of 12"):
        extend_topology(path, add="mleaf", pair=1, site="B", count=9)

    assert _snapshot(tmp_path) == before


def test_multi_dc_mleaf_up_to_per_site_ip_limit_has_unique_addresses(tmp_path: Path):
    path = _write_multi_dc_members(tmp_path)
    extend_topology(path, add="mleaf", pair=1, site="B", count=8)
    addresses = [
        line.split()[-1] for line in path.read_text().splitlines() if "ip_addr:" in line
    ]
    assert len(addresses) == len(set(addresses))


def test_single_dc_too_many_spines_is_rejected_atomically(tmp_path: Path):
    path = _write_base(tmp_path)
    before = _snapshot(tmp_path)

    # spine10 would land on .20, next to the .21+ leaf block.
    with pytest.raises(ValueError, match=r"spine10 exceeds.*limit of 9"):
        extend_topology(path, add="spine", count=8)

    assert _snapshot(tmp_path) == before


def test_single_dc_nine_spines_have_unique_addresses(tmp_path: Path):
    path = _write_base(tmp_path)
    extend_topology(path, add="spine", count=7)
    addresses = [
        line.split()[-1] for line in path.read_text().splitlines() if "ip_addr:" in line
    ]
    assert len(addresses) == len(set(addresses))
    assert "demo-spine9:" in path.read_text()

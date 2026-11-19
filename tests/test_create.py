from dataclasses import replace

import pytest

from acta.capacity import Capacity
from acta.create import FabricSpec, emit_act_yaml
from acta.mac import generate_mac
from acta.topology import parse_connections


def test_emit_includes_capacity_and_mesh_without_spare_links():
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
    text = emit_act_yaml(spec)
    assert "max_spines=4" in text
    assert "demo-spine1:" in text
    conns = parse_connections(text)
    # 2 spines * 2 leaves = 4 mesh + 2 MLAG peer links = 6
    assert len(conns) == 6
    # reserved leaf3 on spine must not appear
    assert not any(
        conn.a_port == 3 or conn.b_port == 3 for conn in conns if "spine" in conn.a_node
    )


def test_generate_mac_matches_generate_sh_algorithm():
    assert generate_mac("demo", "spine1") == "00:1c:73:7d:de:96"


def test_emit_uses_reserved_member_leaf_ports():
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="serial",
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
        member_leaf_pairs=[1],
        member_leaves_per_pair=2,
    )

    text = emit_act_yaml(spec)

    assert "ip_addr: 192.168.0.131/24" in text
    assert "serial_number: serial-mleaf2" in text
    assert "connection: [demo-mleaf1:Ethernet1, demo-leaf1:Ethernet7]" in text
    assert "connection: [demo-mleaf2:Ethernet2, demo-leaf2:Ethernet8]" in text


def test_emit_rejects_multi_dc():
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode=None,
            max_spines=2,
            max_leaves=2,
            max_mleafs_per_pair=0,
            spines=2,
            leaves=2,
        ),
        mlag_pairs=False,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
    )

    with pytest.raises(ValueError, match="single-DC"):
        emit_act_yaml(replace(spec, dc_count=2))

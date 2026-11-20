from pathlib import Path

from acta.capacity import Capacity
from acta.create import FabricSpec, emit_act_yaml
from acta.diagram import topology_to_dot, write_png


def _single(**kwargs) -> str:
    return emit_act_yaml(
        FabricSpec(
            hostname_prefix="demo",
            serial_prefix="demo",
            eos_version="4.35.4M",
            capacity=Capacity(
                fabric_mode=None,
                max_spines=4,
                max_leaves=8,
                max_mleafs_per_pair=2,
                spines=2,
                leaves=4,
            ),
            mlag_pairs=True,
            spine_mlag=True,
            member_leaf_pairs=[1],
            member_leaves_per_pair=1,
            **kwargs,
        )
    )


def _multi(fabric_mode: str = "l3ls") -> str:
    return emit_act_yaml(
        FabricSpec(
            hostname_prefix="demo",
            serial_prefix="demo",
            eos_version="4.35.4M",
            capacity=Capacity(
                fabric_mode=fabric_mode,
                max_spines=2 if fabric_mode == "l2" else 4,
                max_leaves=8,
                max_mleafs_per_pair=0,
                spines=2,
                leaves=2,
            ),
            mlag_pairs=True,
            spine_mlag=False,
            member_leaf_pairs=[],
            member_leaves_per_pair=0,
            dc_count=2,
        )
    )


def test_single_dc_dot_uses_ranks_and_mlag_style():
    dot = topology_to_dot(_single())
    assert "digraph topology" in dot
    assert "rank=same" in dot
    assert 'fillcolor="#dbeafe"' in dot
    assert 'fillcolor="#fef3c7"' in dot
    assert 'fillcolor="#fce7f3"' in dot
    assert "style=dashed" in dot
    assert "demo: 2 spine × 4 leaf (MLAG) + 1 member" in dot
    assert "spine1 -> leaf1" in dot


def test_multi_dc_dot_uses_site_clusters_and_backbone():
    dot = topology_to_dot(_multi("l3ls"))
    assert "subgraph cluster_A" in dot
    assert "subgraph cluster_B" in dot
    assert "rank=min" in dot
    assert "bb1" in dot
    assert 'fillcolor="#d1fae5"' in dot
    assert 'fillcolor="#ede9fe"' in dot
    assert "backbone (l3ls)" in dot
    assert "A_border1 -> bb1" in dot or "A_border1 -> bb2" in dot


def test_write_png_renders_with_graphviz(tmp_path: Path):
    png = tmp_path / "topo.png"
    assert write_png(topology_to_dot(_single()), png) is True
    assert png.is_file()
    assert png.stat().st_size > 1000

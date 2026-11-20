import shutil
from pathlib import Path

import pytest

from acta.attach import attach_host_act
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
                max_spines=2 if fabric_mode == "l2ls" else 4,
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


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz dot not installed")
def test_write_png_renders_with_graphviz(tmp_path: Path):
    png = tmp_path / "topo.png"
    assert write_png(topology_to_dot(_single()), png) is True
    assert png.is_file()
    assert png.stat().st_size > 1000


def test_dot_includes_attached_hosts(tmp_path: Path):
    path = tmp_path / "topology-demo.yml"
    path.write_text(_single(), encoding="utf-8")
    attach_host_act(
        path,
        "jumpbox",
        mlag_pair=1,
        et=11,
        sync_sibling=False,
    )
    text = path.read_text(encoding="utf-8")
    dot = topology_to_dot(text)
    assert "jumpbox" in dot
    assert 'fillcolor="#cffafe"' in dot
    assert " + 1 host" in dot
    assert "constraint=false" in dot
    assert "mleaf1 -> jumpbox [style=invis" in dot
    assert "leaf1 -> jumpbox" in dot
    assert "leaf2 -> jumpbox" in dot
    # Host rank block is emitted after the mleaf fabric rank.
    mleaf_rank = dot.find("mleaf1 [label=")
    host_rank = dot.find("jumpbox [label=")
    assert mleaf_rank != -1 and host_rank != -1 and host_rank > mleaf_rank


def test_multi_dot_places_host_in_site_cluster(tmp_path: Path):
    path = tmp_path / "topology-multi.yml"
    path.write_text(_multi("l3ls"), encoding="utf-8")
    attach_host_act(
        path,
        "demo-host1",
        to=["demo-A-leaf1:Ethernet10"],
        sync_sibling=False,
    )
    dot = topology_to_dot(path.read_text(encoding="utf-8"))
    assert "demo-host1" in dot
    # Host node and its uplink should land inside Site A, not a free-floating max rank.
    site_a = dot.split("subgraph cluster_A")[1].split("subgraph cluster_B")[0]
    assert "demo_host1" in site_a or "demo-host1" in site_a
    assert "A_leaf1 -> demo_host1" in site_a
    assert "constraint=false" in site_a
    assert "style=invis" in site_a


def test_hosts_wrap_into_multiple_rows(tmp_path: Path):
    path = tmp_path / "topology-demo.yml"
    path.write_text(_single(), encoding="utf-8")
    for index in range(1, 8):
        leaf = f"demo-leaf{(index % 4) + 1}"
        attach_host_act(
            path,
            f"h{index}",
            to=[leaf],
            sync_sibling=False,
        )
    from acta.diagram import _HOSTS_PER_ROW, topology_to_dot

    dot = topology_to_dot(path.read_text(encoding="utf-8"))
    assert _HOSTS_PER_ROW == 6
    assert "h1 -> h2 -> h3 -> h4 -> h5 -> h6 [style=invis" in dot
    assert "h1 -> h7 [style=invis" in dot

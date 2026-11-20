"""Tests for acta.py show and attach host."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from acta.attach import attach_host_act, attached_hosts, run_attach
from acta.capacity import Capacity, host_attach_roles, parse_capacity_header
from acta.create import FabricSpec, emit_act_yaml
from acta.extend import leaf_mlag_pairs, member_leaves
from acta.show_topo import run_show


def _topo(
    tmp_path: Path,
    *,
    use_case: str = "datacenter",
    mlag: bool = True,
    member_leaf_pairs: list[int] | None = None,
    member_leaves_per_pair: int = 0,
) -> Path:
    pairs = member_leaf_pairs if member_leaf_pairs is not None else []
    per_pair = member_leaves_per_pair if pairs else 0
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
            leaves=4,
            use_case=use_case,
        ),
        mlag_pairs=mlag,
        spine_mlag=False,
        member_leaf_pairs=pairs,
        member_leaves_per_pair=per_pair,
    )
    path = tmp_path / "topology-demo.yml"
    path.write_text(emit_act_yaml(spec), encoding="utf-8")
    return path


def test_host_attach_roles_by_use_case():
    assert "spine" not in host_attach_roles("datacenter")
    assert "spine" in host_attach_roles("campus")
    assert "bb" not in host_attach_roles("campus")


def test_leaf_mlag_pairs_order_matches_extend_pair_index(tmp_path: Path):
    path = _topo(tmp_path)
    text = path.read_text(encoding="utf-8")
    pairs = leaf_mlag_pairs(text)
    assert pairs
    assert pairs[0] == ("demo-leaf1", "demo-leaf2")


def test_attached_hosts_lists_generic_nodes_in_order(tmp_path: Path):
    path = _topo(tmp_path)
    attach_host_act(path, "jump-a", to=["demo-leaf1:Ethernet10"], sync_sibling=False)
    attach_host_act(path, "jump-b", to=["demo-leaf2:Ethernet10"], sync_sibling=False)
    text = path.read_text(encoding="utf-8")
    assert attached_hosts(text) == ["jump-a", "jump-b"]
    # Non-generic fabric nodes must not appear.
    assert "demo-leaf1" not in attached_hosts(text)


def test_attach_single_host_to_leaf(tmp_path: Path):
    path = _topo(tmp_path)
    result = attach_host_act(
        path,
        "demo-host1",
        to=["demo-leaf1:Ethernet10"],
        sync_sibling=False,
    )
    text = path.read_text(encoding="utf-8")
    assert "node_type: generic" in text
    assert "generic:" in text
    assert "demo-host1:Ethernet1, demo-leaf1:Ethernet10" in text
    assert result.host == "demo-host1"
    cap = parse_capacity_header(text)
    assert cap.use_case == "datacenter"


def test_sync_host_into_clab_enables_lldp(tmp_path: Path):
    from acta.attach import sync_host_into_clab
    from acta.clab.support import MARKER

    act = _topo(tmp_path)
    attach_host_act(
        act,
        "jump1",
        to=["demo-leaf1:Ethernet10"],
        sync_sibling=False,
    )
    clab = tmp_path / "demo.clab.yml"
    clab.write_text(
        MARKER
        + "name: demo\n"
        + "mgmt:\n"
        + "  ipv4-subnet: 172.100.100.0/22\n"
        + "topology:\n"
        + "  nodes:\n"
        + "    demo-leaf1:\n"
        + "      kind: arista_ceos\n"
        + "      mgmt-ipv4: 172.100.100.2\n"
        + "  links: []\n",
        encoding="utf-8",
    )
    sync_host_into_clab(
        clab,
        "jump1",
        act_text=act.read_text(encoding="utf-8"),
        image="ghcr.io/srl-labs/network-multitool:v0.10.0",
    )
    text = clab.read_text(encoding="utf-8")
    assert text.startswith(MARKER.rstrip("\n"))
    assert "kind: linux" in text
    assert "lldpd" in text
    assert "jump1" in text
    assert "mgmt-ipv4:" in text


def test_sync_host_fallback_keeps_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import importlib

    from acta.attach import sync_host_into_clab
    from acta.clab.support import MARKER

    act = _topo(tmp_path)
    attach_host_act(
        act,
        "jump1",
        to=["demo-leaf1:Ethernet10"],
        sync_sibling=False,
    )
    clab = tmp_path / "demo.clab.yml"
    clab.write_text(
        MARKER
        + "name: demo\n"
        + "mgmt:\n"
        + "  ipv4-subnet: 172.100.100.0/22\n"
        + "topology:\n"
        + "  nodes:\n"
        + "    demo-leaf1:\n"
        + "      kind: arista_ceos\n"
        + "  links: []\n",
        encoding="utf-8",
    )

    def boom(_data):
        raise ValueError("yq missing")

    # acta.clab.generate is shadowed by the generate() function on the package.
    gen_mod = importlib.import_module("acta.clab.generate")
    monkeypatch.setattr(gen_mod, "yaml_text", boom)
    sync_host_into_clab(
        clab,
        "jump1",
        act_text=act.read_text(encoding="utf-8"),
        image="ghcr.io/srl-labs/network-multitool:v0.10.0",
    )
    text = clab.read_text(encoding="utf-8")
    assert text.startswith(MARKER.rstrip("\n"))
    assert "jump1" in text


def test_show_lists_ssh_reachable(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    from acta.show_topo import render_show

    path = _topo(tmp_path)
    attach_host_act(
        path,
        "jumpbox",
        to=["demo-leaf1:Ethernet10"],
        sync_sibling=False,
    )
    clab = path.with_suffix(".clab.yml")
    clab.write_text(
        "name: demo\n"
        "topology:\n"
        "  nodes:\n"
        "    demo-leaf1:\n"
        "      mgmt-ipv4: 10.255.0.1\n"
        "    jumpbox:\n"
        "      kind: linux\n"
        "      mgmt-ipv4: 10.255.0.2\n",
        encoding="utf-8",
    )
    render_show(
        path,
        plain=True,
        skip_probe=False,
        probe=lambda ip: ip in {"10.255.0.1", "10.255.0.2"},
    )
    out = capsys.readouterr().out
    assert "SSH reachable" in out
    assert "admin@10.255.0.1" in out
    assert "root@10.255.0.2" in out
    assert "jumpbox" in out


def test_probe_ssh_falls_back_to_podman_machine(monkeypatch: pytest.MonkeyPatch):
    from acta import show_topo

    monkeypatch.setattr(show_topo, "tcp_ssh_open", lambda ip, **_: False)
    monkeypatch.setattr(show_topo, "_podman_machine_available", lambda: True)
    monkeypatch.setattr(
        show_topo,
        "_probe_ips_via_podman_machine",
        lambda ips: {"172.100.100.19"} if "172.100.100.19" in ips else set(),
    )
    reachable = show_topo.probe_ssh_reachable(
        {"blz2-host1": "172.100.100.19", "blz2-A-leaf1": "172.100.100.6"}
    )
    assert reachable == {"blz2-host1": "172.100.100.19"}


def test_attach_mlag_pair(tmp_path: Path):
    path = _topo(tmp_path)
    result = attach_host_act(
        path,
        "demo-host2",
        mlag_pair=1,
        et=11,
        sync_sibling=False,
    )
    text = path.read_text(encoding="utf-8")
    assert "demo-host2:Ethernet1, demo-leaf1:Ethernet11" in text
    assert "demo-host2:Ethernet2, demo-leaf2:Ethernet11" in text
    assert len(result.links) == 2


def test_attach_mlag_pair_without_et_uses_same_port(tmp_path: Path):
    from acta.attach import _next_free_port

    path = _topo(tmp_path)
    before = path.read_text(encoding="utf-8")
    shared_free = _next_free_port(before, "demo-leaf1")
    assert shared_free == _next_free_port(before, "demo-leaf2")
    # Occupy that port on leaf1 only so independent alloc would diverge.
    path.write_text(
        before
        + f"\n  - connection: [filler:Ethernet1, demo-leaf1:Ethernet{shared_free}]\n",
        encoding="utf-8",
    )
    result = attach_host_act(
        path,
        "demo-host-shared",
        mlag_pair=1,
        sync_sibling=False,
    )
    updated = path.read_text(encoding="utf-8")
    ports = [line.rsplit("Ethernet", 1)[-1] for line in result.links]
    assert ports[0] == ports[1]
    assert int(ports[0]) != shared_free
    assert f"demo-leaf1:Ethernet{ports[0]}" in updated
    assert f"demo-leaf2:Ethernet{ports[0]}" in updated


def test_member_leaves_order_and_attach_mleaf(tmp_path: Path):
    path = _topo(
        tmp_path,
        member_leaf_pairs=[1],
        member_leaves_per_pair=2,
    )
    text = path.read_text(encoding="utf-8")
    mleafs = member_leaves(text)
    assert mleafs == ["demo-mleaf1", "demo-mleaf2"]

    result = attach_host_act(
        path,
        "demo-host-m1",
        mleaf=1,
        et=3,
        sync_sibling=False,
    )
    updated = path.read_text(encoding="utf-8")
    assert "demo-host-m1:Ethernet1, demo-mleaf1:Ethernet3" in updated
    assert len(result.links) == 1


def test_attach_rejects_spine_on_datacenter(tmp_path: Path):
    path = _topo(tmp_path, use_case="datacenter")
    with pytest.raises(ValueError, match="forbids attaching hosts to spine"):
        attach_host_act(
            path,
            "demo-host3",
            to=["demo-spine1"],
            sync_sibling=False,
        )


def test_attach_spine_warns_on_campus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    path = _topo(tmp_path, use_case="campus")
    run_attach(
        "host",
        "demo-host4",
        path,
        to=["demo-spine1:Ethernet14"],
        project_dir=tmp_path,
    )
    err = capsys.readouterr().err
    assert "discouraged" in err
    assert "demo-host4" in path.read_text(encoding="utf-8")


def test_show_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _topo(
        tmp_path,
        member_leaf_pairs=[1],
        member_leaves_per_pair=1,
    )
    assert run_show(path, plain=True) == 0
    out = capsys.readouterr().out
    assert "MLAG" in out or "mlag" in out.casefold() or "leaf-a" in out.casefold()
    assert "demo-leaf1" in out
    assert "Member leaves" in out
    assert "--mleaf" in out
    assert "demo-mleaf1" in out
    assert "Attached hosts" in out
    assert path.with_suffix(".png").is_file() or "Graphviz" in out


def test_show_lists_attached_hosts(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _topo(tmp_path)
    attach_host_act(
        path,
        "jumpbox",
        mlag_pair=1,
        et=11,
        sync_sibling=False,
    )
    assert run_show(path, plain=True) == 0
    out = capsys.readouterr().out
    assert "jumpbox" in out
    assert "demo-leaf1:Ethernet11" in out
    assert "demo-leaf2:Ethernet11" in out
    assert "Attached hosts" in out
    png = path.with_suffix(".png")
    assert png.is_file() or shutil.which("dot") is None
    from acta.diagram import topology_to_dot

    dot = topology_to_dot(path.read_text(encoding="utf-8"))
    assert "jumpbox" in dot


def test_show_writes_png_for_multi_site(tmp_path: Path):
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="demo",
        eos_version="4.35.4M",
        capacity=Capacity(
            fabric_mode="l3ls",
            max_spines=4,
            max_leaves=8,
            max_mleafs_per_pair=0,
            spines=2,
            leaves=2,
            use_case="datacenter",
        ),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
        dc_count=2,
    )
    path = tmp_path / "topology-multi.yml"
    path.write_text(emit_act_yaml(spec), encoding="utf-8")
    assert run_show(path, plain=True) == 0
    if shutil.which("dot") is None:
        pytest.skip("Graphviz dot not installed")
    assert path.with_suffix(".png").is_file()


def test_cli_show_and_attach_help():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    for cmd in (["show", "--help"], ["attach", "--help"]):
        proc = subprocess.run(
            [sys.executable, str(root / "acta.py"), *cmd],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr

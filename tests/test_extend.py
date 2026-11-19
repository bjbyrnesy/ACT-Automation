from pathlib import Path

from acta.capacity import Capacity
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
    assert any(
        "leaf3" in f"{a_node}{b_node}" for a_node, _, b_node, _ in after - before
    )

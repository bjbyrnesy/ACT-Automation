from acta.topology import parse_connections, used_ports_from_connections

SAMPLE = """
# capacity: fabric_mode=none max_spines=4 max_leaves=8 max_mleafs_per_pair=0
# capacity: spines=2 leaves=2
links:
  - connection: [demo-spine1:Ethernet1, demo-leaf1:Ethernet1]
  - connection: [demo-spine1:Ethernet2, demo-leaf2:Ethernet1]
  - connection: [demo-spine2:Ethernet1, demo-leaf1:Ethernet2]
"""


def test_parse_connections():
    conns = parse_connections(SAMPLE)
    assert len(conns) == 3
    assert (conns[0].a_node, conns[0].a_port) == ("demo-spine1", 1)


def test_used_ports():
    conns = parse_connections(SAMPLE)
    assert used_ports_from_connections(conns, "demo-spine1") == {1, 2}
    assert used_ports_from_connections(conns, "demo-leaf1") == {1, 2}

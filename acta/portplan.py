from __future__ import annotations

from dataclasses import dataclass

from acta.capacity import HARD_PORT_MAX, Capacity

# Multi-DC port layout (single-DC layouts only use the blocks above the line).
#
# Spine, in order of increasing port number:
#   1..max_leaves                      leaf mesh (port == leaf index)
#   max_leaves+1, +2                   spine MLAG peer (reserved even if unused)
#   max_leaves+3, +4                   site uplink: border1/border2 (l3ls) or
#                                      bb1/bb2 (l2)
# Border leaf (l3ls only):
#   1..max_spines                      spine mesh (port == spine index)
#   max_spines+1, +2                   border MLAG peer
#   max_spines+3, +4                   backbone bb1/bb2
# Backbone router:
#   l3ls: 2*site_index + border_index, peer at 2*dc_count + 1
#   l2:   site_index*max_spines + spine_index, peer at dc_count*max_spines + 1
# Every uplink port sits after the reserved service blocks, so growing leaves or
# spines inside max_* never slides an existing bb/border endpoint.
SPINE_UPLINK_OFFSET = 2  # uplinks start after the 2-port spine MLAG block
BORDER_BB_OFFSET = 2  # border bb ports start after the 2-port border MLAG block


@dataclass(frozen=True)
class PortPlan:
    capacity: Capacity

    def spine_to_leaf_port(self, leaf_index: int) -> int:
        return leaf_index

    def leaf_to_spine_port(self, spine_index: int) -> int:
        return spine_index

    def leaf_mlag_ports(self) -> tuple[int, int]:
        base = self.capacity.max_spines
        return (base + 1, base + 2)

    def leaf_mleaf_port(self, mleaf_slot: int) -> int:
        if mleaf_slot < 1:
            raise ValueError("mleaf_slot must be >= 1")
        return self.capacity.max_spines + 2 + mleaf_slot

    def spine_mlag_ports(self) -> tuple[int, int]:
        base = self.capacity.max_leaves
        return (base + 1, base + 2)

    def spine_uplink_ports(self) -> tuple[int, int]:
        """Multi-DC spine ports toward border1/border2 (l3ls) or bb1/bb2 (l2)."""
        base = self.capacity.max_leaves + SPINE_UPLINK_OFFSET
        return (base + 1, base + 2)

    def border_to_spine_port(self, spine_index: int) -> int:
        return spine_index

    def border_mlag_ports(self) -> tuple[int, int]:
        base = self.capacity.max_spines
        return (base + 1, base + 2)

    def border_bb_ports(self) -> tuple[int, int]:
        """Border ports toward bb1 and bb2."""
        base = self.capacity.max_spines + BORDER_BB_OFFSET
        return (base + 1, base + 2)

    def bb_border_port(self, site_index: int, border_index: int) -> int:
        """bb port for border leaf ``border_index`` (1-2) of 0-based site."""
        return 2 * site_index + border_index

    def bb_spine_port(self, site_index: int, spine_index: int) -> int:
        """bb port for spine ``spine_index`` of a 0-based site (l2 fabrics)."""
        return site_index * self.capacity.max_spines + spine_index

    def bb_peer_port(self, dc_count: int) -> int:
        if self.capacity.fabric_mode == "l2":
            return dc_count * self.capacity.max_spines + 1
        return 2 * dc_count + 1

    def next_free_port(self, used: set[int], prefer: int | None = None) -> int:
        if prefer is not None and 1 <= prefer <= HARD_PORT_MAX and prefer not in used:
            return prefer
        for port in range(1, HARD_PORT_MAX + 1):
            if port not in used:
                return port
        raise ValueError(f"no free Ethernet ports left (hard max {HARD_PORT_MAX})")

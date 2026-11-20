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
        if self.capacity.fabric_mode in {"l2ls", "l2"}:
            return dc_count * self.capacity.max_spines + 1
        return 2 * dc_count + 1

    def leaf_reserved_top(self) -> int:
        """Highest port in a leaf's reserved mesh/MLAG/member-leaf blocks."""
        cap = self.capacity
        return cap.max_spines + 2 + cap.max_mleafs_per_pair

    def leaf_protected_ports(self) -> frozenset[int]:
        """Leaf MLAG and member-leaf slot ports that mesh growth must not take."""
        slots = range(1, self.capacity.max_mleafs_per_pair + 1)
        return frozenset(
            (*self.leaf_mlag_ports(), *(self.leaf_mleaf_port(slot) for slot in slots))
        )

    def spine_reserved_top(self, multi_dc: bool) -> int:
        """Highest port in a spine's reserved mesh/MLAG/uplink blocks."""
        top = self.capacity.max_leaves
        if self.capacity.max_spines >= 2:
            top += 2
        return top + (2 if multi_dc else 0)

    def spine_protected_ports(self, multi_dc: bool) -> frozenset[int]:
        """Spine MLAG (and multi-DC uplink) ports that mesh growth must not take."""
        ports = set(self.spine_mlag_ports())
        if multi_dc:
            ports.update(self.spine_uplink_ports())
        return frozenset(ports)

    def border_reserved_top(self) -> int:
        """Highest port in a border leaf's reserved mesh/MLAG/backbone blocks."""
        return self.capacity.max_spines + BORDER_BB_OFFSET + 2

    def border_protected_ports(self) -> frozenset[int]:
        """Border MLAG and backbone ports that spine mesh growth must not take."""
        return frozenset((*self.border_mlag_ports(), *self.border_bb_ports()))

    def allocate_port(
        self,
        used: set[int],
        preferred: int,
        *,
        reserved_top: int,
        protected: frozenset[int] = frozenset(),
        overrun: bool = False,
    ) -> int:
        """Pick a free port without stealing reserved service blocks.

        In-range requests take ``preferred`` when free. Overrun requests (index
        past the planned soft max) and displaced requests first look *above*
        ``reserved_top``; only then do they reuse free ports outside ``protected``
        (never an MLAG, member-leaf, or uplink block).
        """
        if not overrun and 1 <= preferred <= HARD_PORT_MAX and preferred not in used:
            return preferred
        for port in range(reserved_top + 1, HARD_PORT_MAX + 1):
            if port not in used:
                return port
        for port in range(1, min(reserved_top, HARD_PORT_MAX) + 1):
            if port not in used and port not in protected:
                return port
        raise ValueError(f"no free Ethernet ports left (hard max {HARD_PORT_MAX})")

    def next_free_port(self, used: set[int], prefer: int | None = None) -> int:
        if prefer is not None and 1 <= prefer <= HARD_PORT_MAX and prefer not in used:
            return prefer
        for port in range(1, HARD_PORT_MAX + 1):
            if port not in used:
                return port
        raise ValueError(f"no free Ethernet ports left (hard max {HARD_PORT_MAX})")

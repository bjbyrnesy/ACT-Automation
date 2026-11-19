from __future__ import annotations

from dataclasses import dataclass

from acta.capacity import HARD_PORT_MAX, Capacity


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

    def next_free_port(self, used: set[int], prefer: int | None = None) -> int:
        if prefer is not None and 1 <= prefer <= HARD_PORT_MAX and prefer not in used:
            return prefer
        for port in range(1, HARD_PORT_MAX + 1):
            if port not in used:
                return port
        raise ValueError(f"no free Ethernet ports left (hard max {HARD_PORT_MAX})")

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from acta.capacity import HARD_PORT_MAX, Capacity
from acta.site_names import MAX_SITES, validate_site_token

# Multi-DC port layout (single-DC layouts only use the blocks above the line).
#
# Spine, in order of increasing port number:
#   1..max_leaves                      leaf mesh (port == leaf index)
#   max_leaves+1, +2                   spine MLAG peer (reserved even if unused)
#   max_leaves+3..                     site uplink: borders (l3ls) or bbs (l2)
# Border leaf (l3ls only):
#   1..max_spines                      spine mesh (port == spine index)
#   max_spines+1, +2                   border MLAG peer
#   max_spines+3..                     backbone bb1..bb_count
# Backbone router:
#   l3ls: site_ordinal*border_count + border_index; peer after max-site block
#   l2:   site_ordinal*max_spines + spine_index; peer after max-site block
# Site ordinal = sorted site-name order. Peer is reserved for MAX_SITES (clamped
# to the Ethernet16 budget) so later site adds never renumber existing endpoints.
SPINE_UPLINK_OFFSET = 2  # uplinks start after the 2-port spine MLAG block
BORDER_BB_OFFSET = 2  # border bb ports start after the 2-port border MLAG block


def site_ordinal(site: str, sites: Sequence[str]) -> int:
    """0-based ordinal of ``site`` in sorted unique site-name order."""
    ordered = sorted({validate_site_token(name) for name in sites})
    token = validate_site_token(site)
    try:
        return ordered.index(token)
    except ValueError as exc:
        raise ValueError(f"site {site!r} is not in the site list") from exc


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

    def spine_uplink_count(self) -> int:
        """How many spine uplink ports toward borders (l3ls) or bbs (l2)."""
        if self.capacity.fabric_mode in {"l2ls", "l2"}:
            return self.capacity.bb_count
        return self.capacity.border_count

    def spine_uplink_ports(self) -> tuple[int, ...]:
        """Multi-DC spine ports toward border1..N (l3ls) or bb1..N (l2)."""
        base = self.capacity.max_leaves + SPINE_UPLINK_OFFSET
        count = self.spine_uplink_count()
        ports = tuple(base + offset for offset in range(1, count + 1))
        for port in ports:
            self._require_port(port, what="spine uplink")
        return ports

    def border_to_spine_port(self, spine_index: int) -> int:
        return spine_index

    def border_mlag_ports(self) -> tuple[int, int]:
        base = self.capacity.max_spines
        return (base + 1, base + 2)

    def border_bb_ports(self) -> tuple[int, ...]:
        """Border ports toward bb1..bb_count."""
        base = self.capacity.max_spines + BORDER_BB_OFFSET
        ports = tuple(base + offset for offset in range(1, self.capacity.bb_count + 1))
        for port in ports:
            self._require_port(port, what="border backbone uplink")
        return ports

    def bb_edge_width(self) -> int:
        """Ports consumed on each bb per attached site."""
        if self.capacity.fabric_mode in {"l2ls", "l2"}:
            return self.capacity.max_spines
        return self.capacity.border_count

    def max_attach_sites(self) -> int:
        """How many sites fit on one bb within Ethernet16 + peer reservation."""
        width = self.bb_edge_width()
        if width < 1:
            raise ValueError("backbone edge width must be >= 1")
        needs_peer = (
            self.capacity.bb_redundancy == "mlag-peer" and self.capacity.bb_count >= 2
        )
        budget = HARD_PORT_MAX - (1 if needs_peer else 0)
        return min(MAX_SITES, budget // width)

    def bb_border_port(self, site_index: int, border_index: int) -> int:
        """bb port for border leaf ``border_index`` (1-N) of 0-based site."""
        if border_index < 1 or border_index > self.capacity.border_count:
            raise ValueError(
                f"border_index must be 1..{self.capacity.border_count} "
                f"(got {border_index})"
            )
        if site_index < 0 or site_index >= self.max_attach_sites():
            raise ValueError(
                f"site index {site_index} exceeds backbone capacity "
                f"({self.max_attach_sites()} sites max on Ethernet1..{HARD_PORT_MAX})"
            )
        port = site_index * self.capacity.border_count + border_index
        return self._require_port(port, what="backbone border uplink")

    def bb_spine_port(self, site_index: int, spine_index: int) -> int:
        """bb port for spine ``spine_index`` of a 0-based site (l2 fabrics)."""
        if spine_index < 1 or spine_index > self.capacity.max_spines:
            raise ValueError(
                f"spine_index must be 1..{self.capacity.max_spines} "
                f"(got {spine_index})"
            )
        if site_index < 0 or site_index >= self.max_attach_sites():
            raise ValueError(
                f"site index {site_index} exceeds backbone capacity "
                f"({self.max_attach_sites()} sites max on Ethernet1..{HARD_PORT_MAX})"
            )
        port = site_index * self.capacity.max_spines + spine_index
        return self._require_port(port, what="backbone spine uplink")

    def bb_peer_port(self, dc_count: int | None = None) -> int:
        """Stable bb peer port after the reserved max-site block.

        ``dc_count`` is accepted for call-site compatibility but ignored: the
        peer is reserved for ``max_attach_sites()`` so later adds do not renumber.
        """
        del dc_count  # reserved width is independent of current site count
        if self.capacity.bb_redundancy != "mlag-peer" or self.capacity.bb_count < 2:
            raise ValueError(
                "bb peer port is only defined for mlag-peer with bb_count>=2"
            )
        width = self.bb_edge_width()
        port = width * self.max_attach_sites() + 1
        return self._require_port(port, what="backbone peer")

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
        if multi_dc:
            top += self.spine_uplink_count()
        return top

    def spine_protected_ports(self, multi_dc: bool) -> frozenset[int]:
        """Spine MLAG (and multi-DC uplink) ports that mesh growth must not take."""
        ports = set(self.spine_mlag_ports())
        if multi_dc:
            ports.update(self.spine_uplink_ports())
        return frozenset(ports)

    def border_reserved_top(self) -> int:
        """Highest port in a border leaf's reserved mesh/MLAG/backbone blocks."""
        return self.capacity.max_spines + BORDER_BB_OFFSET + self.capacity.bb_count

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

    def _require_port(self, port: int, *, what: str) -> int:
        if port < 1 or port > HARD_PORT_MAX:
            raise ValueError(
                f"{what} needs Ethernet{port} but hard max is {HARD_PORT_MAX}"
            )
        return port

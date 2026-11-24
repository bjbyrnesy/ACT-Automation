/** Deterministic CV-style layout for ACT fabric topologies. */

import {
  fabricModeOf,
  roleRank,
  type GraphLink,
  type TopologyGraph,
} from "./graph";
import type { NodeRole, TopologyNode } from "./summary";

export type Side = "top" | "bottom" | "left" | "right";

/** Port chrome kind — host attachments are colored differently from fabric/uplinks. */
export type PortKind = "fabric" | "peer" | "uplink" | "host";

export type LaidPort = {
  port: number;
  side: Side;
  x: number;
  y: number;
  /** Port chrome size; defaults to PORT_W/PORT_H when omitted. */
  w?: number;
  h?: number;
  peerName: string;
  kind: PortKind;
};

export type LaidNode = {
  name: string;
  role: NodeRole;
  site: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  subtitle: string | null;
  ports: LaidPort[];
};

export type LaidPoint = { x: number; y: number };

export type LaidLink = {
  id: string;
  /** Polyline from port face → stub → stub → port face (or 2 pts for peers). */
  points: LaidPoint[];
  kind: "fabric" | "peer" | "uplink" | "host";
  aName: string;
  bName: string;
  aPort: number;
  bPort: number;
};

export type LaidBundle = {
  id: string;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  vertical: boolean;
};

export type LaidDomain = {
  id: string;
  kind: "site" | "mlag";
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type CvLayout = {
  width: number;
  height: number;
  title: string;
  nodes: LaidNode[];
  links: LaidLink[];
  bundles: LaidBundle[];
  domains: LaidDomain[];
};

const NODE_W = 118;
const NODE_H = 52;
/** Wider than leaves so downlink + host ports fit with small spine chrome. */
const SPINE_W = 160;
/**
 * Member leaves sit in the peer corridor (≤ PEER_GAP) so they do not cover
 * leaf bottom ports used by dual-home access links.
 */
const MLEAF_W = 80;
/** Narrower than fabric switches; wide enough for ``mleaf1:et10`` + Tux slot. */
const HOST_W = 88;
const PORT_W = 22;
const PORT_H = 14;
/** Compact ports on spines only (peers + downlinks + host). */
const SPINE_PORT_W = 16;
const SPINE_PORT_H = 10;
/** Default horizontal gap between non-peer devices. */
const H_GAP = 52;
/** Gap inside an MLAG/peer pair (leaf and border pairs). */
const PEER_GAP = 80;
/** Wider peer gap for spines — room for centerline host drops. */
const SPINE_PEER_GAP = 140;
/** Gap between adjacent MLAG domains on the leaf row. */
const PAIR_GAP = 40;
const V_GAP = 96;
/** Leaf row → first member leaf (room for dual-home Po stubs + ellipse). */
const MLEAF_DROP = 52;
/** Vertical gap between stacked member leaves under one pair. */
const MLEAF_STACK_GAP = 28;
/** Member leaf → host row. */
const HOST_DROP = 36;
const SITE_PAD = 32;
const SITE_GAP = 56;
const MARGIN = 36;
const MLAG_PAD = 14;
/** Tiny stub past the port face (just enough to own the center, then angle). */
const PORT_STUB = 1;
/**
 * Dual-homed leaf→mleaf vertical run before the join — long enough that a
 * horizontal Po ellipse can wrap both stubs without covering the ports.
 */
const MLEAF_PO_STUB = 16;

type PairKey = string;

function pairKey(a: string, b: string): PairKey {
  return a < b ? `${a}::${b}` : `${b}::${a}`;
}

function deviceW(role: NodeRole): number {
  if (role === "host") return HOST_W;
  if (role === "mleaf") return MLEAF_W;
  if (role === "spine") return SPINE_W;
  return NODE_W;
}

function portSize(role: NodeRole): { w: number; h: number } {
  if (role === "spine") return { w: SPINE_PORT_W, h: SPINE_PORT_H };
  return { w: PORT_W, h: PORT_H };
}

function diagramTitle(graph: TopologyGraph): string {
  const { summary } = graph;
  const prefix = summary.title ?? "lab";
  const sites = summary.sites.filter((s) => s !== "core" && s !== "fabric");
  const multi = sites.length > 1;
  const spines = summary.byRole.spine;
  const leaves = summary.byRole.leaf;
  const mode = fabricModeOf(graph);
  const hasLeafMlag = graph.links.some((link) => {
    const a = graph.byName[link.aNode];
    const b = graph.byName[link.bNode];
    return (
      !!a &&
      !!b &&
      a.role === "leaf" &&
      b.role === "leaf" &&
      (a.site ?? "") === (b.site ?? "")
    );
  });
  if (multi) {
    const perSiteSpines = Math.round(spines / sites.length) || spines;
    const perSiteLeaves = Math.round(leaves / sites.length) || leaves;
    let title = `${prefix}: ${sites.length} site × (${perSiteSpines} spine × ${perSiteLeaves} leaf`;
    if (hasLeafMlag) title += " MLAG";
    title += `) + backbone (${mode})`;
    if (summary.byRole.host) {
      title += ` + ${summary.byRole.host} host${summary.byRole.host === 1 ? "" : "s"}`;
    }
    return title;
  }
  let title = `${prefix}: ${spines} spine × ${leaves} leaf`;
  if (hasLeafMlag) title += " (MLAG)";
  if (summary.byRole.mleaf) {
    title += ` + ${summary.byRole.mleaf} member${summary.byRole.mleaf === 1 ? "" : "s"}`;
  }
  if (summary.byRole.host) {
    title += ` + ${summary.byRole.host} host${summary.byRole.host === 1 ? "" : "s"}`;
  }
  return title;
}

function nodeIndex(name: string): number {
  const m = /(\d+)$/.exec(name);
  return m ? Number(m[1]) : 0;
}

function rowWidth(count: number): number {
  if (count <= 0) return 0;
  return count * NODE_W + (count - 1) * H_GAP;
}

function peerGapFor(group: TopologyNode[]): number {
  if (group.length !== 2) return H_GAP;
  if (group[0].role === "spine") return SPINE_PEER_GAP;
  return PEER_GAP;
}

/** Row width with wide peer gaps inside pairs and PAIR_GAP between domains. */
function peerGroupsWidth(groups: TopologyNode[][]): number {
  if (!groups.length) return 0;
  let width = 0;
  for (let i = 0; i < groups.length; i += 1) {
    const group = groups[i];
    const gap = peerGapFor(group);
    for (let ni = 0; ni < group.length; ni += 1) {
      width += deviceW(group[ni].role);
      if (ni < group.length - 1) width += gap;
    }
    if (i < groups.length - 1) width += PAIR_GAP;
  }
  return width;
}

function sortNodes(nodes: TopologyNode[]): TopologyNode[] {
  return [...nodes].sort((a, b) => {
    const rr = roleRank(a.role) - roleRank(b.role);
    if (rr !== 0) return rr;
    return nodeIndex(a.name) - nodeIndex(b.name) || a.name.localeCompare(b.name);
  });
}

/** Pair sorted nodes as (1–2), (3–4), … for MLAG layout when links are absent. */
function consecutivePairs(nodes: TopologyNode[]): TopologyNode[][] {
  const sorted = sortNodes(nodes);
  const pairs: TopologyNode[][] = [];
  for (let i = 0; i < sorted.length; i += 2) {
    if (i + 1 < sorted.length) {
      pairs.push([sorted[i], sorted[i + 1]]);
    } else {
      pairs.push([sorted[i]]);
    }
  }
  return pairs;
}

/** Same-role MLAG/peer pairs from peer links; else consecutive index pairs. */
function rolePairs(
  role: NodeRole,
  nodes: TopologyNode[],
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): TopologyNode[][] {
  const peer = new Map<string, Set<string>>();
  for (const link of links) {
    const a = byName[link.aNode];
    const b = byName[link.bNode];
    if (!a || !b) continue;
    if (a.role !== role || b.role !== role) continue;
    if ((a.site ?? "") !== (b.site ?? "")) continue;
    (peer.get(a.name) ?? peer.set(a.name, new Set()).get(a.name)!).add(b.name);
    (peer.get(b.name) ?? peer.set(b.name, new Set()).get(b.name)!).add(a.name);
  }

  if (peer.size === 0) {
    // Borders/spines/bb often MLAG without peer links present in older YAML.
    return consecutivePairs(nodes);
  }

  const remaining = sortNodes(nodes);
  const pairs: TopologyNode[][] = [];
  while (remaining.length) {
    const first = remaining.shift()!;
    const mates = peer.get(first.name);
    const mateName = mates
      ? [...mates].find((name) => remaining.some((n) => n.name === name))
      : undefined;
    if (mateName) {
      const idx = remaining.findIndex((n) => n.name === mateName);
      const mate = remaining.splice(idx, 1)[0];
      pairs.push(
        nodeIndex(first.name) <= nodeIndex(mate.name)
          ? [first, mate]
          : [mate, first],
      );
    } else {
      pairs.push([first]);
    }
  }
  return pairs;
}

/** Place grouped peer pairs with PEER_GAP inside pairs. */
function placePeerGroups(
  groups: TopologyNode[][],
  y: number,
  siteLeft: number,
  siteWidth: number,
  positions: Map<string, Pos>,
): void {
  if (!groups.length) return;
  const totalW = peerGroupsWidth(groups);
  let x = siteLeft + (siteWidth - totalW) / 2;
  for (let gi = 0; gi < groups.length; gi += 1) {
    const group = groups[gi];
    const gap = peerGapFor(group);
    for (let ni = 0; ni < group.length; ni += 1) {
      positions.set(group[ni].name, { x, y });
      x += deviceW(group[ni].role);
      if (ni < group.length - 1) x += gap;
    }
    if (gi < groups.length - 1) x += PAIR_GAP;
  }
}

/** Parent leaf names for a member leaf (same-site uplinks). */
function mleafParentNames(
  mleafName: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): string[] {
  const parents = new Set<string>();
  for (const link of links) {
    const a = byName[link.aNode];
    const b = byName[link.bNode];
    if (!a || !b) continue;
    if (link.aNode === mleafName && b.role === "leaf") parents.add(b.name);
    if (link.bNode === mleafName && a.role === "leaf") parents.add(a.name);
  }
  return [...parents].sort();
}

/** Deepest mleaf stack under any parent pair (for site box height). */
function mleafStackDepth(
  mleafs: TopologyNode[],
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): number {
  if (!mleafs.length) return 0;
  const counts = new Map<string, number>();
  let loose = 0;
  for (const m of mleafs) {
    const parents = mleafParentNames(m.name, links, byName);
    if (!parents.length) {
      loose += 1;
      continue;
    }
    const key = parents.join("|");
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Math.max(loose, ...counts.values(), 0);
}

/**
 * Center each mleaf stack under its parent leaf pair; stack multiples vertically.
 * Returns the Y of the top of the host row (below lowest mleaf + HOST_DROP).
 */
function placeMleafStacks(
  mleafs: TopologyNode[],
  leafRowY: number,
  siteLeft: number,
  siteWidth: number,
  positions: Map<string, Pos>,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): number {
  if (!mleafs.length) return leafRowY + NODE_H + HOST_DROP;

  type Stack = { mleafs: TopologyNode[]; cx: number };
  const stacks = new Map<string, Stack>();
  const loose: TopologyNode[] = [];

  for (const m of sortNodes(mleafs)) {
    const parents = mleafParentNames(m.name, links, byName);
    if (!parents.length) {
      loose.push(m);
      continue;
    }
    const key = parents.join("|");
    let stack = stacks.get(key);
    if (!stack) {
      const parentPos = parents
        .map((name) => positions.get(name))
        .filter((p): p is Pos => p != null);
      const cx =
        parentPos.length > 0
          ? (Math.min(...parentPos.map((p) => p.x)) +
              Math.max(...parentPos.map((p) => p.x + NODE_W))) /
            2
          : siteLeft + siteWidth / 2;
      stack = { mleafs: [], cx };
      stacks.set(key, stack);
    }
    stack.mleafs.push(m);
  }

  const startY = leafRowY + NODE_H + MLEAF_DROP;
  let maxDepth = 0;

  for (const stack of stacks.values()) {
    const sorted = sortNodes(stack.mleafs);
    maxDepth = Math.max(maxDepth, sorted.length);
    for (let i = 0; i < sorted.length; i += 1) {
      positions.set(sorted[i].name, {
        x: stack.cx - MLEAF_W / 2,
        y: startY + i * (NODE_H + MLEAF_STACK_GAP),
      });
    }
  }

  if (loose.length) {
    maxDepth = Math.max(maxDepth, 1);
    const rowW = loose.length * NODE_W + (loose.length - 1) * H_GAP;
    let x = siteLeft + (siteWidth - rowW) / 2;
    const y = startY + Math.max(0, maxDepth - 1) * (NODE_H + MLEAF_STACK_GAP);
    const looseY = stacks.size ? y : startY;
    for (const m of loose) {
      positions.set(m.name, { x, y: looseY });
      x += NODE_W + H_GAP;
    }
    if (!stacks.size) maxDepth = 1;
  }

  if (maxDepth === 0) return startY + HOST_DROP;
  return (
    startY +
    maxDepth * NODE_H +
    Math.max(0, maxDepth - 1) * MLEAF_STACK_GAP +
    HOST_DROP
  );
}

/** Access switches attached to a host (leaves, mleafs, and/or spines). */
function hostAccessSwitches(
  hostName: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): { leaves: string[]; mleafs: string[]; spines: string[] } {
  const leaves: string[] = [];
  const mleafs: string[] = [];
  const spines: string[] = [];
  for (const link of links) {
    const other =
      link.aNode === hostName
        ? link.bNode
        : link.bNode === hostName
          ? link.aNode
          : null;
    if (!other) continue;
    const node = byName[other];
    if (node?.role === "leaf" && !leaves.includes(other)) leaves.push(other);
    if (node?.role === "mleaf" && !mleafs.includes(other)) mleafs.push(other);
    if (node?.role === "spine" && !spines.includes(other)) spines.push(other);
  }
  return { leaves, mleafs, spines };
}

/** Parent switch for a host (prefer mleaf, else leaf, else spine). */
function hostParentName(
  hostName: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): string | null {
  const { leaves, mleafs, spines } = hostAccessSwitches(
    hostName,
    links,
    byName,
  );
  if (mleafs.length) return mleafs[0];
  if (leaves.length) return leaves[0];
  if (spines.length) return spines[0];
  return null;
}

/**
 * Switch-side Ethernet number for a host uplink (odd → left rail, even → right).
 */
function hostParentPort(
  hostName: string,
  parentName: string,
  links: GraphLink[],
): number | null {
  for (const link of links) {
    if (link.aNode === hostName && link.bNode === parentName) return link.bPort;
    if (link.bNode === hostName && link.aNode === parentName) return link.aPort;
  }
  return null;
}

/** Same-role peer mates (MLAG pairs) for a given role. */
function roleMateMap(
  role: NodeRole,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): Map<string, string> {
  const mates = new Map<string, string>();
  for (const link of links) {
    const a = byName[link.aNode];
    const b = byName[link.bNode];
    if (!a || !b || a.role !== role || b.role !== role) continue;
    if (!isPeerPair(a, b)) continue;
    mates.set(a.name, b.name);
    mates.set(b.name, a.name);
  }
  return mates;
}

/** Leaf ↔ leaf peer mates (MLAG pairs). */
function leafMateMap(
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): Map<string, string> {
  return roleMateMap("leaf", links, byName);
}

/**
 * Dual-homed to both leaves of one MLAG pair (never to mleafs).
 * Returns leaves ordered left→right by X when positions are known.
 */
function mlagDualHomeLeaves(
  hostName: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
  positions: Map<string, Pos>,
  mates: Map<string, string>,
): [string, string] | null {
  const { leaves, mleafs } = hostAccessSwitches(hostName, links, byName);
  if (mleafs.length || leaves.length !== 2) return null;
  const [a, b] = leaves;
  if (mates.get(a) !== b) return null;
  const ap = positions.get(a);
  const bp = positions.get(b);
  if (ap && bp) {
    return ap.x <= bp.x ? [a, b] : [b, a];
  }
  return nodeIndex(a) <= nodeIndex(b) ? [a, b] : [b, a];
}

/**
 * Dual-homed to both spines of one MLAG pair.
 * Returns spines ordered left→right by X when positions are known.
 */
function mlagDualHomeSpines(
  hostName: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
  positions: Map<string, Pos>,
  mates: Map<string, string>,
): [string, string] | null {
  const { spines, leaves, mleafs } = hostAccessSwitches(
    hostName,
    links,
    byName,
  );
  if (leaves.length || mleafs.length || spines.length !== 2) return null;
  const [a, b] = spines;
  if (mates.get(a) !== b) return null;
  const ap = positions.get(a);
  const bp = positions.get(b);
  if (ap && bp) {
    return ap.x <= bp.x ? [a, b] : [b, a];
  }
  return nodeIndex(a) <= nodeIndex(b) ? [a, b] : [b, a];
}

/** Bottom of the fabric column that shares ``parent``'s X (stacked mleafs). */
function columnFabricBottom(
  parentPos: Pos,
  positions: Map<string, Pos>,
  byName: Record<string, TopologyNode>,
): number {
  let bottom = parentPos.y + NODE_H;
  for (const [name, pos] of positions) {
    const node = byName[name];
    if (!node || isHostRole(node.role)) continue;
    if (Math.abs(pos.x - parentPos.x) < 2) {
      bottom = Math.max(bottom, pos.y + NODE_H);
    }
  }
  return bottom;
}

/** Lowest fabric/mleaf Y under an MLAG leaf pair's horizontal span. */
function pairColumnBottom(
  leftLeaf: string,
  rightLeaf: string,
  positions: Map<string, Pos>,
  byName: Record<string, TopologyNode>,
): number {
  const lp = positions.get(leftLeaf);
  const rp = positions.get(rightLeaf);
  if (!lp || !rp) return 0;
  const L = Math.min(lp.x, rp.x);
  const R = Math.max(lp.x, rp.x) + NODE_W;
  let bottom = Math.max(lp.y, rp.y) + NODE_H;
  for (const [name, pos] of positions) {
    const node = byName[name];
    if (!node || isHostRole(node.role)) continue;
    const mid = pos.x + deviceW(node.role) / 2;
    if (mid >= L - 1 && mid <= R + 1) {
      bottom = Math.max(bottom, pos.y + NODE_H);
    }
  }
  return bottom;
}

/** True when a member leaf sits under this leaf pair's span. */
function pairHasMleaf(
  leftLeaf: string,
  rightLeaf: string,
  positions: Map<string, Pos>,
  byName: Record<string, TopologyNode>,
): boolean {
  const lp = positions.get(leftLeaf);
  const rp = positions.get(rightLeaf);
  if (!lp || !rp) return false;
  const L = Math.min(lp.x, rp.x);
  const R = Math.max(lp.x, rp.x) + NODE_W;
  for (const [name, pos] of positions) {
    if (byName[name]?.role !== "mleaf") continue;
    const mid = pos.x + MLEAF_W / 2;
    if (mid >= L - 1 && mid <= R + 1) return true;
  }
  return false;
}

/** Short peer label for host subtitles (``blz-MSP-mleaf2`` → ``mleaf2``). */
function shortParentLabel(name: string): string {
  // Prefer mleaf over leaf so ``…-mleaf1`` does not collapse to ``leaf1``.
  const m = /-((?:mleaf|leaf)\d+)$/i.exec(name);
  return m ? m[1].toLowerCase() : name;
}

/** Host subtitle via-parent, e.g. ``mleaf1:et7`` or ``leaf1:et9 · leaf2:et9``. */
function hostViaLabel(
  hostName: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
  positions: Map<string, Pos>,
): string | null {
  const mates = leafMateMap(links, byName);
  const dual = mlagDualHomeLeaves(hostName, links, byName, positions, mates);
  if (dual) {
    const [left, right] = dual;
    const lp = hostParentPort(hostName, left, links);
    const rp = hostParentPort(hostName, right, links);
    const l = shortParentLabel(left);
    const r = shortParentLabel(right);
    if (lp != null && rp != null) return `${l}:et${lp} · ${r}:et${rp}`;
    return `${l}+${r}`;
  }
  const parent = hostParentName(hostName, links, byName);
  if (!parent) return null;
  const label = shortParentLabel(parent);
  const port = hostParentPort(hostName, parent, links);
  return port != null ? `${label}:et${port}` : label;
}

/**
 * Place hosts in a host band below fabric — never level with switches.
 *
 * Per leaf MLAG pair, pack non-overlapping columns left→right and stack
 * within each column:
 *   leaf1 | mleaf-L | dual | mleaf-R | leaf2
 *
 * Spine singles/duals use columns under the spine X / pair centerline in
 * the same host band (not at spine-row Y).
 */
function placeHostsUnderParents(
  hosts: TopologyNode[],
  hostRowY: number,
  siteLeft: number,
  siteWidth: number,
  positions: Map<string, Pos>,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): number {
  if (!hosts.length) return hostRowY;

  const HOST_H_GAP = 20;
  const COL_GAP = 12;
  const mates = leafMateMap(links, byName);
  const spineMates = roleMateMap("spine", links, byName);
  let maxBottom = hostRowY;

  type DualGroup = {
    left: string;
    right: string;
    hosts: TopologyNode[];
  };
  type MleafAttach = { host: TopologyNode; port: number };
  type SeatCol = { id: string; hosts: TopologyNode[] };

  const dualByPair = new Map<string, DualGroup>();
  const spineDualByPair = new Map<string, DualGroup>();
  const leafSingles = new Map<string, TopologyNode[]>();
  const spineSingles = new Map<string, TopologyNode[]>();
  const mleafSingles = new Map<string, MleafAttach[]>();
  const loose: TopologyNode[] = [];

  for (const host of sortNodes(hosts)) {
    const dual = mlagDualHomeLeaves(host.name, links, byName, positions, mates);
    if (dual) {
      const [left, right] = dual;
      const key = `${left}|${right}`;
      let group = dualByPair.get(key);
      if (!group) {
        group = { left, right, hosts: [] };
        dualByPair.set(key, group);
      }
      group.hosts.push(host);
      continue;
    }

    const spineDual = mlagDualHomeSpines(
      host.name,
      links,
      byName,
      positions,
      spineMates,
    );
    if (spineDual) {
      const [left, right] = spineDual;
      const key = `${left}|${right}`;
      let group = spineDualByPair.get(key);
      if (!group) {
        group = { left, right, hosts: [] };
        spineDualByPair.set(key, group);
      }
      group.hosts.push(host);
      continue;
    }

    const { leaves, mleafs, spines } = hostAccessSwitches(
      host.name,
      links,
      byName,
    );
    if (mleafs.length) {
      const parent = mleafs[0];
      const port = hostParentPort(host.name, parent, links) ?? 1;
      const list = mleafSingles.get(parent) ?? [];
      list.push({ host, port });
      mleafSingles.set(parent, list);
      continue;
    }
    if (leaves.length) {
      const parent = leaves[0];
      const list = leafSingles.get(parent) ?? [];
      list.push(host);
      leafSingles.set(parent, list);
      continue;
    }
    if (spines.length) {
      const parent = spines[0];
      const list = spineSingles.get(parent) ?? [];
      list.push(host);
      spineSingles.set(parent, list);
      continue;
    }
    loose.push(host);
  }

  const stackAtX = (
    list: TopologyNode[],
    x: number,
    startY: number,
  ): number => {
    let y = startY;
    for (const host of list) {
      positions.set(host.name, { x, y });
      y += NODE_H + HOST_H_GAP;
    }
    return list.length ? y - HOST_H_GAP + NODE_H : startY;
  };

  const stackCentered = (
    list: TopologyNode[],
    cx: number,
    startY: number,
  ): number => stackAtX(list, cx - HOST_W / 2, startY);

  /** Pack seat columns evenly under [left, right], expand slightly if needed. */
  const packColumns = (
    cols: SeatCol[],
    pairLeft: number,
    pairRight: number,
    startY: number,
  ): number => {
    const active = cols.filter((c) => c.hosts.length > 0);
    if (!active.length) return startY;
    const n = active.length;
    const need = n * HOST_W + (n - 1) * COL_GAP;
    const pairW = Math.max(HOST_W, pairRight - pairLeft);
    const span = Math.max(pairW, need);
    const origin = (pairLeft + pairRight) / 2 - span / 2;
    const step = n <= 1 ? 0 : (span - HOST_W) / (n - 1);
    let bottom = startY;
    for (let i = 0; i < n; i += 1) {
      const x = n === 1 ? origin + (span - HOST_W) / 2 : origin + i * step;
      bottom = Math.max(
        bottom,
        stackAtX(sortNodes(active[i].hosts), x, startY),
      );
    }
    return bottom;
  };

  // Group leaf-pair work by pair key so columns share one band Y.
  type PairBucket = {
    left: string;
    right: string;
    leaf1: TopologyNode[];
    leaf2: TopologyNode[];
    mleafL: TopologyNode[];
    mleafR: TopologyNode[];
    duals: TopologyNode[];
  };
  const pairBuckets = new Map<string, PairBucket>();

  const ensurePair = (left: string, right: string): PairBucket => {
    const lp = positions.get(left);
    const rp = positions.get(right);
    const ordered =
      lp && rp && lp.x > rp.x ? [right, left] : [left, right];
    const key = `${ordered[0]}|${ordered[1]}`;
    let bucket = pairBuckets.get(key);
    if (!bucket) {
      bucket = {
        left: ordered[0],
        right: ordered[1],
        leaf1: [],
        leaf2: [],
        mleafL: [],
        mleafR: [],
        duals: [],
      };
      pairBuckets.set(key, bucket);
    }
    return bucket;
  };

  for (const group of dualByPair.values()) {
    ensurePair(group.left, group.right).duals.push(...group.hosts);
  }

  for (const [leafName, list] of leafSingles) {
    const mate = mates.get(leafName);
    if (mate) {
      const bucket = ensurePair(leafName, mate);
      if (leafName === bucket.left) bucket.leaf1.push(...list);
      else bucket.leaf2.push(...list);
    } else {
      // Lone leaf: single column under that leaf.
      const leafPos = positions.get(leafName);
      if (!leafPos) continue;
      const startY =
        columnFabricBottom(leafPos, positions, byName) + HOST_DROP;
      maxBottom = Math.max(
        maxBottom,
        stackCentered(sortNodes(list), leafPos.x + NODE_W / 2, startY),
      );
    }
  }

  for (const [mleafName, items] of mleafSingles) {
    const parents = mleafParentNames(mleafName, links, byName);
    if (parents.length >= 2) {
      const bucket = ensurePair(parents[0], parents[1]);
      for (const item of items) {
        if (item.port % 2 === 1) bucket.mleafL.push(item.host);
        else bucket.mleafR.push(item.host);
      }
    } else if (parents.length === 1) {
      const parentPos = positions.get(parents[0]);
      const mPos = positions.get(mleafName);
      if (!parentPos || !mPos) continue;
      const startY =
        columnFabricBottom(mPos, positions, byName) + HOST_DROP;
      const left = items
        .filter((i) => i.port % 2 === 1)
        .map((i) => i.host);
      const right = items
        .filter((i) => i.port % 2 === 0)
        .map((i) => i.host);
      maxBottom = Math.max(
        maxBottom,
        packColumns(
          [
            { id: "mL", hosts: left },
            { id: "mR", hosts: right },
          ],
          mPos.x,
          mPos.x + MLEAF_W,
          startY,
        ),
      );
    }
  }

  for (const bucket of pairBuckets.values()) {
    const lp = positions.get(bucket.left);
    const rp = positions.get(bucket.right);
    if (!lp || !rp) continue;
    const pairLeft = Math.min(lp.x, rp.x);
    const pairRight = Math.max(lp.x, rp.x) + NODE_W;
    const startY =
      pairColumnBottom(bucket.left, bucket.right, positions, byName) +
      HOST_DROP;
    maxBottom = Math.max(
      maxBottom,
      packColumns(
        [
          { id: "leaf1", hosts: bucket.leaf1 },
          { id: "mleafL", hosts: bucket.mleafL },
          { id: "dual", hosts: bucket.duals },
          { id: "mleafR", hosts: bucket.mleafR },
          { id: "leaf2", hosts: bucket.leaf2 },
        ],
        pairLeft,
        pairRight,
        startY,
      ),
    );
  }

  // Spine singles + duals — host-band column on the spine-pair centerline
  // (middle of the peer gap), so links drop straight down the center corridor.
  {
    type SpineCenter = { cx: number; hosts: TopologyNode[] };
    const centers = new Map<string, SpineCenter>();
    const addCenter = (key: string, cx: number, list: TopologyNode[]) => {
      let bucket = centers.get(key);
      if (!bucket) {
        bucket = { cx, hosts: [] };
        centers.set(key, bucket);
      }
      bucket.hosts.push(...list);
    };

    for (const [spineName, list] of spineSingles) {
      const spinePos = positions.get(spineName);
      if (!spinePos) continue;
      const mate = spineMates.get(spineName);
      const matePos = mate ? positions.get(mate) : undefined;
      if (mate && matePos) {
        const left = spinePos.x <= matePos.x ? spineName : mate;
        const right = left === spineName ? mate : spineName;
        const lp = positions.get(left)!;
        const rp = positions.get(right)!;
        const cx = (lp.x + rp.x + SPINE_W) / 2;
        addCenter(`${left}|${right}`, cx, list);
      } else {
        addCenter(spineName, spinePos.x + SPINE_W / 2, list);
      }
    }

    for (const group of spineDualByPair.values()) {
      const lp = positions.get(group.left);
      const rp = positions.get(group.right);
      if (!lp || !rp) continue;
      const cx = (lp.x + rp.x + SPINE_W) / 2;
      addCenter(`${group.left}|${group.right}`, cx, group.hosts);
    }

    for (const bucket of centers.values()) {
      let startY = hostRowY;
      for (const [name, pos] of positions) {
        const node = byName[name];
        if (!node || !isHostRole(node.role)) continue;
        const mid = pos.x + HOST_W / 2;
        if (Math.abs(mid - bucket.cx) < HOST_W) {
          startY = Math.max(startY, pos.y + NODE_H + HOST_H_GAP);
        }
      }
      maxBottom = Math.max(
        maxBottom,
        stackCentered(sortNodes(bucket.hosts), bucket.cx, startY),
      );
    }
  }

  if (loose.length) {
    const rowW = loose.length * HOST_W + (loose.length - 1) * HOST_H_GAP;
    let x = siteLeft + (siteWidth - rowW) / 2;
    for (const host of loose) {
      positions.set(host.name, { x, y: hostRowY });
      x += HOST_W + HOST_H_GAP;
    }
    maxBottom = Math.max(maxBottom, hostRowY + NODE_H);
  }

  return maxBottom;
}

function isPeerPair(
  a: TopologyNode,
  b: TopologyNode,
): boolean {
  return (
    a.role === b.role &&
    (a.site ?? "") === (b.site ?? "") &&
    (a.role === "leaf" || a.role === "spine" || a.role === "border" || a.role === "bb")
  );
}

function isHostRole(role: NodeRole): boolean {
  return role === "host";
}

function isLeafMleafLink(
  a: TopologyNode,
  b: TopologyNode,
): boolean {
  return (
    (a.role === "leaf" && b.role === "mleaf") ||
    (a.role === "mleaf" && b.role === "leaf")
  );
}

function linkKind(
  a: TopologyNode,
  b: TopologyNode,
): LaidLink["kind"] {
  if (isHostRole(a.role) || isHostRole(b.role)) return "host";
  if (isPeerPair(a, b)) return "peer";
  if (a.role === "bb" || b.role === "bb") return "uplink";
  return "fabric";
}

/** Leaf and border pairs with peer links are MLAG domains (Po + dashed box). */
function isMlagDomainPair(a: TopologyNode, b: TopologyNode): boolean {
  return (
    isPeerPair(a, b) &&
    a.role === b.role &&
    (a.role === "leaf" || a.role === "border")
  );
}

function showPoForBundle(
  mode: "l3ls" | "l2ls",
  a: TopologyNode,
  b: TopologyNode,
  count: number,
): boolean {
  if (count < 2) return false;
  // Leaf / border MLAG peer port-channels (both fabric modes).
  if (isMlagDomainPair(a, b)) return true;
  if (mode === "l3ls") return false;
  // L2LS extras: spine peers and leaf↔spine LAGs
  if (a.role === "spine" && b.role === "spine" && isPeerPair(a, b)) return true;
  const roles = new Set([a.role, b.role]);
  return roles.has("leaf") && roles.has("spine");
}

function showMlagDomain(
  _mode: "l3ls" | "l2ls",
  a: TopologyNode,
  b: TopologyNode,
): boolean {
  return isMlagDomainPair(a, b);
}

type Pos = { x: number; y: number };

/** Lay out ACT topology in a CV-ish hierarchical grid. */
export function layoutCvDiagram(graph: TopologyGraph): CvLayout {
  const mode = fabricModeOf(graph);
  const byName = graph.byName;
  const title = diagramTitle(graph);

  const siteKeys = graph.summary.sites.filter((s) => s !== "core");
  const multi = siteKeys.some((s) => s !== "fabric");
  const sites = multi
    ? siteKeys.filter((s) => s !== "fabric")
    : siteKeys.length
      ? siteKeys
      : ["fabric"];

  const bb = sortNodes(graph.summary.nodes.filter((n) => n.role === "bb"));
  const bbGroups = rolePairs("bb", bb, graph.links, byName);
  const positions = new Map<string, Pos>();

  // Measure each site column width from leaf-pair rows.
  type SitePlan = {
    key: string;
    borderGroups: TopologyNode[][];
    spineGroups: TopologyNode[][];
    leafGroups: TopologyNode[][];
    mleaf: TopologyNode[];
    host: TopologyNode[];
    width: number;
    height: number;
  };

  const plans: SitePlan[] = sites.map((key) => {
    const members =
      key === "fabric"
        ? graph.summary.nodes.filter((n) => n.role !== "bb")
        : (graph.summary.bySite[key] ?? []).filter((n) => n.role !== "bb");
    const borderGroups = rolePairs(
      "border",
      members.filter((n) => n.role === "border"),
      graph.links,
      byName,
    );
    const spineGroups = rolePairs(
      "spine",
      members.filter((n) => n.role === "spine"),
      graph.links,
      byName,
    );
    const leafGroups = rolePairs(
      "leaf",
      members.filter((n) => n.role === "leaf"),
      graph.links,
      byName,
    );
    const mleaf = sortNodes(members.filter((n) => n.role === "mleaf"));
    // Hosts may still be site-less; attach by uplink into this site.
    const memberNames = new Set(members.map((n) => n.name));
    const host = sortNodes(
      graph.summary.nodes.filter((n) => {
        if (n.role !== "host") return false;
        if (members.some((m) => m.name === n.name)) return true;
        return graph.links.some((link) => {
          const other =
            link.aNode === n.name
              ? link.bNode
              : link.bNode === n.name
                ? link.aNode
                : null;
          if (!other) return false;
          if (memberNames.has(other)) return true;
          const peer = byName[other];
          return peer?.site === key;
        });
      }),
    );

    const mleafDepth = mleafStackDepth(mleaf, graph.links, byName);
    // Width is driven by fabric rows; mleaf/hosts hang under leaf pairs.
    const rowWidths = [
      peerGroupsWidth(borderGroups),
      peerGroupsWidth(spineGroups),
      peerGroupsWidth(leafGroups),
      rowWidth(bb.length),
    ];
    // Hosts fit inside leaf-pair width, so fabric rows drive site width.
    const width = Math.max(...rowWidths, NODE_W) + SITE_PAD * 2;
    const mleafBlockH =
      mleafDepth > 0
        ? MLEAF_DROP +
          mleafDepth * NODE_H +
          Math.max(0, mleafDepth - 1) * MLEAF_STACK_GAP +
          HOST_DROP
        : 0;
    const hostBlockH = host.length
      ? host.length * NODE_H + Math.max(0, host.length - 1) * 28
      : 0;
    const height =
      SITE_PAD * 2 +
      18 +
      (borderGroups.length ? NODE_H + V_GAP : 0) +
      (spineGroups.length ? NODE_H + V_GAP : 0) +
      (leafGroups.length ? NODE_H + V_GAP : 0) +
      mleafBlockH +
      hostBlockH;
    return {
      key,
      borderGroups,
      spineGroups,
      leafGroups,
      mleaf,
      host,
      width,
      height,
    };
  });

  const siteHeight = Math.max(...plans.map((p) => p.height), NODE_H + SITE_PAD * 2);
  const bbRowH = bb.length ? NODE_H + V_GAP : 0;
  const totalSitesW =
    plans.reduce((s, p) => s + p.width, 0) + Math.max(0, plans.length - 1) * SITE_GAP;

  let width =
    MARGIN * 2 + Math.max(totalSitesW, peerGroupsWidth(bbGroups));
  let height = MARGIN * 2 + 28 + bbRowH + siteHeight;

  // Place backbone centered above sites (peer-gap when MLAG'd).
  if (bbGroups.length) {
    placePeerGroups(bbGroups, MARGIN + 28, 0, width, positions);
  }

  const siteTop = MARGIN + 28 + bbRowH;
  let siteLeft = MARGIN + Math.max(0, (totalSitesW > 0 ? (width - MARGIN * 2 - totalSitesW) / 2 : 0));

  const domains: LaidDomain[] = [];
  const mlagPairs: Array<[TopologyNode, TopologyNode]> = [];

  for (const plan of plans) {
    if (multi || plan.key !== "fabric") {
      domains.push({
        id: `site-${plan.key}`,
        kind: "site",
        label: plan.key === "fabric" ? "Fabric" : `Site ${plan.key}`,
        x: siteLeft,
        y: siteTop,
        w: plan.width,
        h: siteHeight,
      });
    }

    const placeRow = (nodes: TopologyNode[], y: number) => {
      if (!nodes.length) return;
      const rowW = nodes.length * NODE_W + (nodes.length - 1) * H_GAP;
      let x = siteLeft + (plan.width - rowW) / 2;
      for (const node of nodes) {
        positions.set(node.name, { x, y });
        x += NODE_W + H_GAP;
      }
    };

    let y = siteTop + SITE_PAD + 14;
    placePeerGroups(plan.borderGroups, y, siteLeft, plan.width, positions);
    for (const group of plan.borderGroups) {
      if (group.length === 2) mlagPairs.push([group[0], group[1]]);
    }
    if (plan.borderGroups.length) y += NODE_H + V_GAP;
    placePeerGroups(plan.spineGroups, y, siteLeft, plan.width, positions);
    if (plan.spineGroups.length) y += NODE_H + V_GAP;

    const leafRowY = y;
    placePeerGroups(plan.leafGroups, y, siteLeft, plan.width, positions);
    for (const group of plan.leafGroups) {
      if (group.length === 2) mlagPairs.push([group[0], group[1]]);
    }
    if (plan.leafGroups.length) {
      y = placeMleafStacks(
        plan.mleaf,
        leafRowY,
        siteLeft,
        plan.width,
        positions,
        graph.links,
        byName,
      );
    } else if (plan.mleaf.length) {
      placeRow(plan.mleaf, y);
      y += NODE_H + HOST_DROP;
    }
    y = placeHostsUnderParents(
      plan.host,
      y,
      siteLeft,
      plan.width,
      positions,
      graph.links,
      byName,
    );

    siteLeft += plan.width + SITE_GAP;
  }

  // Outboard mleaf-rail hosts can sit left of siteLeft — shift so everything
  // stays inside the canvas margin (before ports/links are laid).
  {
    let minX = Infinity;
    let maxX = -Infinity;
    let maxBottom = 0;
    for (const [name, pos] of positions) {
      const node = byName[name];
      if (!node) continue;
      const w = deviceW(node.role);
      minX = Math.min(minX, pos.x);
      maxX = Math.max(maxX, pos.x + w);
      maxBottom = Math.max(maxBottom, pos.y + NODE_H);
    }
    if (Number.isFinite(minX) && minX < MARGIN) {
      const dx = MARGIN - minX;
      for (const pos of positions.values()) pos.x += dx;
      for (const d of domains) d.x += dx;
      maxX += dx;
    }
    if (Number.isFinite(maxX)) {
      width = Math.max(width, maxX + MARGIN);
    }
    height = Math.max(height, maxBottom + MARGIN);
  }

  // MLAG domain boxes around peer leaf pairs (after positions known).
  for (const [left, right] of mlagPairs) {
    if (!showMlagDomain(mode, left, right)) continue;
    const peerLinks = graph.links.filter(
      (l) =>
        (l.aNode === left.name && l.bNode === right.name) ||
        (l.aNode === right.name && l.bNode === left.name),
    );
    if (!peerLinks.length) continue;
    const lp = positions.get(left.name)!;
    const rp = positions.get(right.name)!;
    const rightMost = rp.x >= lp.x ? right : left;
    const x = Math.min(lp.x, rp.x) - MLAG_PAD;
    const y = Math.min(lp.y, rp.y) - MLAG_PAD;
    const w =
      Math.abs(rp.x - lp.x) + deviceW(rightMost.role) + MLAG_PAD * 2;
    const h = NODE_H + MLAG_PAD * 2;
    domains.push({
      id: `mlag-${left.name}-${right.name}`,
      kind: "mlag",
      label: "MLAG",
      x,
      y,
      w,
      h,
    });
  }

  // Assign port sides from neighbor geometry, then place port blocks.
  const portsByNode = new Map<string, LaidPort[]>();
  const ensurePorts = (name: string) => {
    let list = portsByNode.get(name);
    if (!list) {
      list = [];
      portsByNode.set(name, list);
    }
    return list;
  };

  /**
   * Pick a Y for a side port that does not collide with ports already on that
   * face (e.g. mleaf uplink elbow + host rail both wanting mid-height).
   */
  const freePortY = (
    name: string,
    side: Side,
    nodeY: number,
    preferredY: number,
  ): number => {
    const minGap = PORT_H + 4;
    const lo = nodeY + 2;
    const hi = nodeY + NODE_H - PORT_H - 2;
    const preferred = Math.min(hi, Math.max(lo, preferredY));
    const taken = (portsByNode.get(name) ?? [])
      .filter((p) => p.side === side)
      .map((p) => p.y);
    const blocked = (y: number) =>
      taken.some((ty) => Math.abs(ty - y) < minGap);
    if (!blocked(preferred)) return preferred;
    for (let step = minGap; step <= NODE_H; step += minGap) {
      for (const cand of [preferred + step, preferred - step]) {
        const y = Math.min(hi, Math.max(lo, cand));
        if (!blocked(y)) return y;
      }
    }
    return preferred;
  };

  const sideSlots = new Map<string, Record<Side, number>>();
  const nextSlot = (name: string, side: Side) => {
    let slots = sideSlots.get(name);
    if (!slots) {
      slots = { top: 0, bottom: 0, left: 0, right: 0 };
      sideSlots.set(name, slots);
    }
    const i = slots[side];
    slots[side] = i + 1;
    return i;
  };

  function chooseSide(
    from: Pos,
    to: Pos,
    fromNode: TopologyNode,
    toNode: TopologyNode,
  ): Side {
    const dx =
      to.x +
      deviceW(toNode.role) / 2 -
      (from.x + deviceW(fromNode.role) / 2);
    const dy = to.y + NODE_H / 2 - (from.y + NODE_H / 2);
    // Same-tier peers (MLAG) attach on left/right; cross-tier on top/bottom.
    if (isPeerPair(fromNode, toNode)) {
      return dx >= 0 ? "right" : "left";
    }
    if (roleRank(fromNode.role) !== roleRank(toNode.role)) {
      return dy >= 0 ? "bottom" : "top";
    }
    if (Math.abs(dx) > Math.abs(dy)) return dx >= 0 ? "right" : "left";
    return dy >= 0 ? "bottom" : "top";
  }

  function portAnchor(
    pos: Pos,
    side: Side,
    slot: number,
    totalHint: number,
    boxW: number = NODE_W,
    pw: number = PORT_W,
    ph: number = PORT_H,
  ): { x: number; y: number } {
    const spread = Math.max(1, totalHint);
    const t = (slot + 1) / (spread + 1);
    if (side === "top") {
      return { x: pos.x + boxW * t - pw / 2, y: pos.y - ph };
    }
    if (side === "bottom") {
      return { x: pos.x + boxW * t - pw / 2, y: pos.y + NODE_H };
    }
    if (side === "left") {
      return { x: pos.x - pw, y: pos.y + NODE_H * t - ph / 2 };
    }
    return { x: pos.x + boxW, y: pos.y + NODE_H * t - ph / 2 };
  }

  /** Midpoint of the port face away from the device (where the link attaches). */
  function outerAttach(
    anchor: LaidPoint,
    side: Side,
    pw: number = PORT_W,
    ph: number = PORT_H,
  ): LaidPoint {
    const cx = anchor.x + pw / 2;
    const cy = anchor.y + ph / 2;
    if (side === "top") return { x: cx, y: anchor.y };
    if (side === "bottom") return { x: cx, y: anchor.y + ph };
    if (side === "left") return { x: anchor.x, y: cy };
    return { x: anchor.x + pw, y: cy };
  }

  function stubFrom(attach: LaidPoint, side: Side): LaidPoint {
    if (side === "top") return { x: attach.x, y: attach.y - PORT_STUB };
    if (side === "bottom") return { x: attach.x, y: attach.y + PORT_STUB };
    if (side === "left") return { x: attach.x - PORT_STUB, y: attach.y };
    return { x: attach.x + PORT_STUB, y: attach.y };
  }

  /**
   * Bottom port: slot 0 = innermost (toward peer), then outward.
   * Pitch keeps interface blocks from overlapping (PORT_W + gap).
   */
  function bottomPortFromInner(
    pos: Pos,
    slotFromInner: number,
    total: number,
    innerIsRight: boolean,
    boxW: number = NODE_W,
    pw: number = PORT_W,
  ): LaidPoint {
    const n = Math.max(1, total);
    const pitch = pw + 4;
    const edgePad = 4;
    const usable = Math.max(0, boxW - edgePad * 2 - pw);
    const naturalSpan = n <= 1 ? 0 : (n - 1) * pitch;
    const span = n <= 1 ? 0 : Math.min(naturalSpan, usable);
    const step = n <= 1 ? 0 : span / (n - 1);
    const fromInner = edgePad + slotFromInner * step;
    const x = innerIsRight
      ? pos.x + boxW - pw - fromInner
      : pos.x + fromInner;
    return { x, y: pos.y + NODE_H };
  }

  // First pass: decide sides and count slots per side (skip leaf↔mleaf).
  type Pending = {
    link: GraphLink;
    aSide: Side;
    bSide: Side;
  };
  const pending: Pending[] = [];
  const mleafLinks: GraphLink[] = [];
  const hostLinks: GraphLink[] = [];
  for (const link of graph.links) {
    const a = byName[link.aNode];
    const b = byName[link.bNode];
    const ap = positions.get(link.aNode);
    const bp = positions.get(link.bNode);
    if (!a || !b || !ap || !bp) continue;
    if (isLeafMleafLink(a, b)) {
      mleafLinks.push(link);
      continue;
    }
    if (isHostRole(a.role) || isHostRole(b.role)) {
      hostLinks.push(link);
      continue;
    }
    const aSide = chooseSide(ap, bp, a, b);
    const bSide = chooseSide(bp, ap, b, a);
    pending.push({ link, aSide, bSide });
    nextSlot(link.aNode, aSide);
    nextSlot(link.bNode, bSide);
  }

  // Reset counters for placement using totals.
  const totals = new Map(sideSlots);
  sideSlots.clear();

  const linkEndpoints = new Map<string, LaidPoint[]>();

  const placedIds = new Set<string>();

  // Peer bundles first: stack ports with matching Y so links stay horizontal.
  const peerGroups = new Map<string, Pending[]>();
  for (const item of pending) {
    const a = byName[item.link.aNode]!;
    const b = byName[item.link.bNode]!;
    if (!isPeerPair(a, b)) continue;
    const key = pairKey(item.link.aNode, item.link.bNode);
    (peerGroups.get(key) ?? peerGroups.set(key, []).get(key)!).push(item);
  }

  for (const group of peerGroups.values()) {
    group.sort(
      (left, right) =>
        left.link.aPort - right.link.aPort ||
        left.link.bPort - right.link.bPort,
    );
    const sample = group[0];
    const leftName =
      positions.get(sample.link.aNode)!.x <= positions.get(sample.link.bNode)!.x
        ? sample.link.aNode
        : sample.link.bNode;
    const rightName =
      leftName === sample.link.aNode ? sample.link.bNode : sample.link.aNode;
    const leftPos = positions.get(leftName)!;
    const rightPos = positions.get(rightName)!;
    const leftRole = byName[leftName]!.role;
    const rightRole = byName[rightName]!.role;
    const leftBox = deviceW(leftRole);
    const { w: lpw, h: lph } = portSize(leftRole);
    const { w: rpw, h: rph } = portSize(rightRole);
    const n = group.length;
    const pitch = Math.min(lph, rph) + 4;
    const span = Math.min(
      NODE_H - Math.min(lph, rph),
      Math.max(Math.min(lph, rph), (n - 1) * pitch + Math.min(lph, rph)),
    );
    const startY = leftPos.y + (NODE_H - span) / 2;

    for (let i = 0; i < group.length; i += 1) {
      const { link } = group[i];
      const t = n === 1 ? 0.5 : i / (n - 1);
      const y = startY + t * (span - Math.min(lph, rph));
      const leftPort = link.aNode === leftName ? link.aPort : link.bPort;
      const rightPort = link.aNode === rightName ? link.aPort : link.bPort;
      const leftAnchor = { x: leftPos.x + leftBox, y };
      const rightAnchor = { x: rightPos.x - rpw, y };

      ensurePorts(leftName).push({
        port: leftPort,
        side: "right",
        x: leftAnchor.x,
        y: leftAnchor.y,
        w: lpw,
        h: lph,
        peerName: rightName,
        kind: "peer",
      });
      ensurePorts(rightName).push({
        port: rightPort,
        side: "left",
        x: rightAnchor.x,
        y: rightAnchor.y,
        w: rpw,
        h: rph,
        peerName: leftName,
        kind: "peer",
      });

      const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
      placedIds.add(id);
      const leftFace = outerAttach(leftAnchor, "right", lpw, lph);
      const rightFace = outerAttach(rightAnchor, "left", rpw, rph);
      linkEndpoints.set(id, [leftFace, rightFace]);
    }
  }

  // Member-leaf uplinks: first mleaf gets centered verticals into top ports;
  // deeper stack members keep the side-elbow path. Dual-homed mleafs collect
  // a horizontal Po around the long vertical stubs under the narrow mleaf.
  const dualMleafPo: Array<{
    mleaf: string;
    stubs: Array<{ x: number; y0: number; y1: number }>;
  }> = [];
  {
    type MleafStack = {
      mleafs: string[];
      leftLeaf: string;
      rightLeaf: string;
    };
    const stacks = new Map<string, MleafStack>();
    for (const link of mleafLinks) {
      const a = byName[link.aNode]!;
      const b = byName[link.bNode]!;
      const mleafName = a.role === "mleaf" ? a.name : b.name;
      const parents = mleafParentNames(mleafName, graph.links, byName);
      if (parents.length < 1) continue;
      const parentPos = parents
        .map((name) => ({ name, pos: positions.get(name) }))
        .filter((p): p is { name: string; pos: Pos } => p.pos != null)
        .sort((l, r) => l.pos.x - r.pos.x);
      if (!parentPos.length) continue;
      const leftLeaf = parentPos[0].name;
      const rightLeaf = parentPos[parentPos.length - 1].name;
      const key = `${leftLeaf}|${rightLeaf}`;
      let stack = stacks.get(key);
      if (!stack) {
        stack = { mleafs: [], leftLeaf, rightLeaf };
        stacks.set(key, stack);
      }
      if (!stack.mleafs.includes(mleafName)) stack.mleafs.push(mleafName);
    }

    for (const stack of stacks.values()) {
      stack.mleafs.sort((a, b) => {
        const ay = positions.get(a)?.y ?? 0;
        const by = positions.get(b)?.y ?? 0;
        if (ay !== by) return ay - by;
        return nodeIndex(a) - nodeIndex(b);
      });
      const depth = stack.mleafs.length;
      const leftPos = positions.get(stack.leftLeaf)!;
      const rightPos = positions.get(stack.rightLeaf)!;

      const findMleafLink = (
        leafName: string,
        mleafName: string,
      ): GraphLink | undefined =>
        mleafLinks.find(
          (l) =>
            (l.aNode === leafName && l.bNode === mleafName) ||
            (l.bNode === leafName && l.aNode === mleafName),
        );

      for (let i = 0; i < depth; i += 1) {
        const mleafName = stack.mleafs[i];
        const mPos = positions.get(mleafName);
        if (!mPos) continue;
        const dualThis =
          Boolean(findMleafLink(stack.leftLeaf, mleafName)) &&
          Boolean(findMleafLink(stack.rightLeaf, mleafName));

        const placeUplink = (
          leafName: string,
          leafPos: Pos,
          innerIsRight: boolean,
        ) => {
          const link = findMleafLink(leafName, mleafName);
          if (!link) return;
          const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
          if (placedIds.has(id)) return;

          const leafPort =
            link.aNode === leafName ? link.aPort : link.bPort;
          const mleafPort =
            link.aNode === mleafName ? link.aPort : link.bPort;

          const leafAnchor = bottomPortFromInner(
            leafPos,
            i,
            depth,
            innerIsRight,
          );

          if (i === 0) {
            // First mleaf: drop from leaf, clamp onto the narrower mleaf top.
            const mleafAnchor = {
              x: Math.min(
                mPos.x + MLEAF_W - PORT_W - 2,
                Math.max(mPos.x + 2, leafAnchor.x),
              ),
              y: mPos.y - PORT_H,
            };
            ensurePorts(leafName).push({
              port: leafPort,
              side: "bottom",
              x: leafAnchor.x,
              y: leafAnchor.y,
              peerName: mleafName,
              kind: "uplink",
            });
            ensurePorts(mleafName).push({
              port: mleafPort,
              side: "top",
              x: mleafAnchor.x,
              y: mleafAnchor.y,
              peerName: leafName,
              kind: "uplink",
            });
            const leafFace = outerAttach(leafAnchor, "bottom");
            const mleafFace = outerAttach(mleafAnchor, "top");
            const path: LaidPoint[] = [leafFace];
            if (dualThis) {
              // Jog under the narrow mleaf first, then a long vertical stub so
              // the Po ellipse wraps a consistent corridor (not the wide leaf
              // bottoms).
              const jogY = leafFace.y + PORT_STUB;
              const stubTop = { x: mleafFace.x, y: jogY };
              const stubBot = {
                x: mleafFace.x,
                y: Math.min(mleafFace.y - 2, jogY + MLEAF_PO_STUB),
              };
              if (Math.abs(leafFace.x - mleafFace.x) >= 2) {
                path.push({ x: leafFace.x, y: jogY });
              }
              path.push(stubTop);
              if (stubBot.y > stubTop.y + 1) path.push(stubBot);
              path.push(mleafFace);
              let po = dualMleafPo.find((p) => p.mleaf === mleafName);
              if (!po) {
                po = { mleaf: mleafName, stubs: [] };
                dualMleafPo.push(po);
              }
              po.stubs.push({
                x: mleafFace.x,
                y0: stubTop.y,
                y1: Math.max(stubBot.y, stubTop.y + MLEAF_PO_STUB),
              });
            } else {
              const leafStub = {
                x: leafFace.x,
                y: leafFace.y + PORT_STUB,
              };
              const joinY = Math.min(
                mleafFace.y - 4,
                Math.max(leafStub.y + 2, leafFace.y + PORT_STUB),
              );
              path.push(leafStub);
              if (Math.abs(leafStub.x - mleafFace.x) >= 2) {
                path.push({ x: leafStub.x, y: joinY });
                path.push({ x: mleafFace.x, y: joinY });
              }
              path.push(mleafFace);
            }
            linkEndpoints.set(id, path);
            placedIds.add(id);
            return;
          }

          // Deeper stack: vertical from leaf, then 90° into mleaf side.
          // Sit near the top of the face so host rails can own mid/lower.
          const side: Side = leafName === stack.leftLeaf ? "left" : "right";
          const uplinkY = freePortY(
            mleafName,
            side,
            mPos.y,
            mPos.y + 4,
          );
          const mleafAnchor =
            side === "left"
              ? { x: mPos.x - PORT_W, y: uplinkY }
              : { x: mPos.x + MLEAF_W, y: uplinkY };

          ensurePorts(leafName).push({
            port: leafPort,
            side: "bottom",
            x: leafAnchor.x,
            y: leafAnchor.y,
            peerName: mleafName,
            kind: "uplink",
          });
          ensurePorts(mleafName).push({
            port: mleafPort,
            side,
            x: mleafAnchor.x,
            y: mleafAnchor.y,
            peerName: leafName,
            kind: "uplink",
          });

          const leafFace = outerAttach(leafAnchor, "bottom");
          // Deeper dual stack: keep a short leaf stub; Po is owned by the
          // first (top-port) mleaf under the narrow box.
          const leafStub = { x: leafFace.x, y: leafFace.y + PORT_STUB };
          const mleafFace = outerAttach(mleafAnchor, side);
          const mleafStub = stubFrom(mleafFace, side);
          const elbowY = Math.max(leafStub.y + 2, mleafStub.y);
          const elbow = { x: leafStub.x, y: elbowY };
          const path: LaidPoint[] = [
            leafFace,
            leafStub,
            elbow,
            { x: mleafStub.x, y: elbowY },
            mleafFace,
          ];
          linkEndpoints.set(id, path);
          placedIds.add(id);
        };

        placeUplink(stack.leftLeaf, leftPos, true);
        placeUplink(stack.rightLeaf, rightPos, false);
      }
    }
  }

  // Host uplinks: mleaf side-rails; leaf single-home vertical; MLAG dual-home Po.
  const leafMates = leafMateMap(graph.links, byName);
  const spineMatesForRoute = roleMateMap("spine", graph.links, byName);
  type HostRoute = {
    link: GraphLink;
    hostNode: TopologyNode;
    parentNode: TopologyNode;
    hostPos: Pos;
    parentPos: Pos;
    rail: "left" | "right" | null;
    dual: [string, string] | null;
  };
  const hostRoutes: HostRoute[] = [];
  for (const link of hostLinks) {
    const a = byName[link.aNode]!;
    const b = byName[link.bNode]!;
    const hostNode = isHostRole(a.role) ? a : b;
    const parentNode = isHostRole(a.role) ? b : a;
    const hostPos = positions.get(hostNode.name);
    const parentPos = positions.get(parentNode.name);
    if (!hostPos || !parentPos) continue;
    const dual = mlagDualHomeLeaves(
      hostNode.name,
      graph.links,
      byName,
      positions,
      leafMates,
    );
    let rail: "left" | "right" | null = null;
    // Spine hosts stay on bottom ports + outer corridor (peers own sides).
    if (!dual && parentNode.role !== "spine") {
      const parentWidth = deviceW(parentNode.role);
      if (hostPos.x + HOST_W <= parentPos.x + 2) rail = "left";
      else if (hostPos.x >= parentPos.x + parentWidth - 2) rail = "right";
    }
    hostRoutes.push({
      link,
      hostNode,
      parentNode,
      hostPos,
      parentPos,
      rail,
      dual,
    });
  }

  const sideHostSlot = new Map<string, number>();
  const sideHostCount = new Map<string, number>();
  for (const item of hostRoutes) {
    if (!item.rail) continue;
    const key = `${item.rail}:${item.parentNode.name}`;
    sideHostCount.set(key, (sideHostCount.get(key) ?? 0) + 1);
  }

  // Dual-home hosts per MLAG pair, top → bottom (first uses inward leaf ports).
  const dualHostsByPair = new Map<string, string[]>();
  for (const item of hostRoutes) {
    if (!item.dual) continue;
    const key = pairKey(item.dual[0], item.dual[1]);
    const list = dualHostsByPair.get(key) ?? [];
    if (!list.includes(item.hostNode.name)) list.push(item.hostNode.name);
    dualHostsByPair.set(key, list);
  }
  for (const list of dualHostsByPair.values()) {
    list.sort(
      (a, b) =>
        (positions.get(a)?.y ?? 0) - (positions.get(b)?.y ?? 0) ||
        a.localeCompare(b),
    );
  }

  // Dual-home: two top ports on the host; leaf bottoms aim inward; Po mark later.
  const dualHomePo: Array<{ host: string; paths: LaidPoint[][] }> = [];

  for (const item of hostRoutes) {
    const { link, hostNode, parentNode, hostPos, parentPos, rail, dual } = item;
    const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
    if (placedIds.has(id)) continue;

    const hostPort =
      link.aNode === hostNode.name ? link.aPort : link.bPort;
    const parentPort =
      link.aNode === parentNode.name ? link.aPort : link.bPort;

    if (dual) {
      const [leftLeaf, rightLeaf] = dual;
      const isLeft = parentNode.name === leftLeaf;
      const pair = pairKey(leftLeaf, rightLeaf);
      const ordered = dualHostsByPair.get(pair) ?? [hostNode.name];
      const dualIndex = Math.max(0, ordered.indexOf(hostNode.name));
      const reserveMleaf = pairHasMleaf(
        leftLeaf,
        rightLeaf,
        positions,
        byName,
      )
        ? 1
        : 0;
      // Left leg → leftish top port; right leg → rightish (no cross).
      const hostAnchor = {
        x: hostPos.x + (isLeft ? HOST_W * 0.2 : HOST_W * 0.8) - PORT_W / 2,
        y: hostPos.y - PORT_H,
      };
      const leafPos = parentPos;
      // Inward from the peer face; slot 0 is reserved for mleaf uplinks when
      // present, so the first dual-home is not parked on the far outer edge.
      const parentAnchor = bottomPortFromInner(
        leafPos,
        dualIndex + reserveMleaf,
        ordered.length + reserveMleaf,
        isLeft,
      );

      ensurePorts(parentNode.name).push({
        port: parentPort,
        side: "bottom",
        x: parentAnchor.x,
        y: parentAnchor.y,
        peerName: hostNode.name,
        kind: "host",
      });
      ensurePorts(hostNode.name).push({
        port: hostPort,
        side: "top",
        x: hostAnchor.x,
        y: hostAnchor.y,
        peerName: parentNode.name,
        kind: "host",
      });

      const parentFace = outerAttach(parentAnchor, "bottom");
      const parentStub = stubFrom(parentFace, "bottom");
      const hostFace = outerAttach(hostAnchor, "top");
      const pairCx =
        ((positions.get(leftLeaf)?.x ?? 0) +
          (positions.get(rightLeaf)?.x ?? 0) +
          NODE_W) /
        2;
      // Gap under the mleaf stack (pairColumnBottom includes mleafs).
      const clearY = Math.min(
        hostFace.y - 8,
        Math.max(
          parentStub.y + 12,
          pairColumnBottom(leftLeaf, rightLeaf, positions, byName) + 10,
        ),
      );
      const mleafLeft = pairCx - MLEAF_W / 2 - 2;
      const mleafRight = pairCx + MLEAF_W / 2 + 2;
      const clearsMleaf = isLeft
        ? parentStub.x < mleafLeft
        : parentStub.x > mleafRight;
      // Inward leaf seats already clear the narrow mleaf — drop straight,
      // then join at the host. No long horizontal at the leaf bottom.
      const path: LaidPoint[] = [parentFace, parentStub];
      if (clearsMleaf) {
        path.push(
          { x: parentStub.x, y: clearY },
          { x: hostFace.x, y: clearY },
          hostFace,
        );
      } else {
        const bypassX = isLeft
          ? Math.min(parentStub.x, mleafLeft)
          : Math.max(parentStub.x, mleafRight);
        if (Math.abs(bypassX - parentStub.x) >= 2) {
          path.push({ x: bypassX, y: parentStub.y });
        }
        path.push(
          { x: bypassX, y: clearY },
          { x: hostFace.x, y: clearY },
          hostFace,
        );
      }
      linkEndpoints.set(id, path);
      let po = dualHomePo.find((p) => p.host === hostNode.name);
      if (!po) {
        po = { host: hostNode.name, paths: [] };
        dualHomePo.push(po);
      }
      po.paths.push(path);
      placedIds.add(id);
      continue;
    }

    if (rail) {
      const laneKey = `${rail}:${parentNode.name}`;
      const slot = sideHostSlot.get(laneKey) ?? 0;
      sideHostSlot.set(laneKey, slot + 1);
      const slots = sideHostCount.get(laneKey) ?? 1;
      const t = (slot + 1) / (slots + 1);
      const parentSide: Side = rail === "left" ? "left" : "right";
      const hostSide: Side = rail === "left" ? "right" : "left";
      const { w: ppw, h: pph } = portSize(parentNode.role);
      const parentY = freePortY(
        parentNode.name,
        parentSide,
        parentPos.y,
        parentPos.y + NODE_H * Math.max(0.55, t) - pph / 2,
      );
      const parentAnchor =
        rail === "left"
          ? { x: parentPos.x - ppw, y: parentY }
          : { x: parentPos.x + deviceW(parentNode.role), y: parentY };
      const hostAnchor =
        rail === "left"
          ? {
              x: hostPos.x + HOST_W,
              y: hostPos.y + NODE_H / 2 - PORT_H / 2,
            }
          : {
              x: hostPos.x - PORT_W,
              y: hostPos.y + NODE_H / 2 - PORT_H / 2,
            };

      ensurePorts(parentNode.name).push({
        port: parentPort,
        side: parentSide,
        x: parentAnchor.x,
        y: parentAnchor.y,
        w: ppw,
        h: pph,
        peerName: hostNode.name,
        kind: "host",
      });
      ensurePorts(hostNode.name).push({
        port: hostPort,
        side: hostSide,
        x: hostAnchor.x,
        y: hostAnchor.y,
        peerName: parentNode.name,
        kind: "host",
      });

      const parentFace = outerAttach(parentAnchor, parentSide, ppw, pph);
      const hostFace = outerAttach(hostAnchor, hostSide);
      // Leave mleaf etN at face center with a short stub, drop, then into the
      // host port — avoid a long unused horizontal off the switchport.
      const laneX =
        rail === "left" ? parentFace.x - 6 : parentFace.x + 6;
      linkEndpoints.set(id, [
        parentFace,
        { x: laneX, y: parentFace.y },
        { x: laneX, y: hostFace.y },
        hostFace,
      ]);
    } else {
      // Single-home under a leaf/spine: bottom port on the parent.
      const { w: ppw, h: pph } = portSize(parentNode.role);
      const parentBox = deviceW(parentNode.role);
      const hostCx = hostPos.x + HOST_W / 2;
      const parentAnchor = {
        x: Math.min(
          parentPos.x + parentBox - ppw - 2,
          Math.max(parentPos.x + 2, hostCx - ppw / 2),
        ),
        y: parentPos.y + NODE_H,
      };
      const hostAnchor = {
        x: hostCx - PORT_W / 2,
        y: hostPos.y - PORT_H,
      };

      ensurePorts(parentNode.name).push({
        port: parentPort,
        side: "bottom",
        x: parentAnchor.x,
        y: parentAnchor.y,
        w: ppw,
        h: pph,
        peerName: hostNode.name,
        kind: "host",
      });
      ensurePorts(hostNode.name).push({
        port: hostPort,
        side: "top",
        x: hostAnchor.x,
        y: hostAnchor.y,
        peerName: parentNode.name,
        kind: "host",
      });

      const parentFace = outerAttach(parentAnchor, "bottom", ppw, pph);
      const parentStub = stubFrom(parentFace, "bottom");
      const hostFace = outerAttach(hostAnchor, "top");

      if (parentNode.role === "spine") {
        // Drop through the spine-pair center corridor (peer gap → host),
        // not around the outside of the leaf fabric.
        const spineMate = spineMatesForRoute.get(parentNode.name);
        const matePos = spineMate ? positions.get(spineMate) : undefined;
        const corridorX = matePos
          ? (Math.min(parentPos.x, matePos.x) +
              Math.max(parentPos.x, matePos.x) +
              SPINE_W) /
            2
          : hostFace.x;
        linkEndpoints.set(id, [
          parentFace,
          parentStub,
          { x: corridorX, y: parentStub.y },
          { x: corridorX, y: hostFace.y },
          hostFace,
        ]);
      } else if (Math.abs(parentStub.x - hostFace.x) < 2) {
        linkEndpoints.set(id, [parentFace, parentStub, hostFace]);
      } else {
        const elbow = { x: hostFace.x, y: parentStub.y };
        linkEndpoints.set(id, [parentFace, parentStub, elbow, hostFace]);
      }
    }
    placedIds.add(id);
  }

  for (const { link, aSide, bSide } of pending) {
    const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
    if (placedIds.has(id)) continue;

    const aNode = byName[link.aNode]!;
    const bNode = byName[link.bNode]!;
    const kind: PortKind =
      aNode.role === "host" || bNode.role === "host"
        ? "host"
        : aNode.role === "mleaf" || bNode.role === "mleaf"
          ? "uplink"
          : "fabric";

    const ap = positions.get(link.aNode)!;
    const bp = positions.get(link.bNode)!;
    const aTotal = totals.get(link.aNode)?.[aSide] ?? 1;
    const bTotal = totals.get(link.bNode)?.[bSide] ?? 1;
    const aSlot = nextSlot(link.aNode, aSide);
    const bSlot = nextSlot(link.bNode, bSide);
    const { w: apw, h: aph } = portSize(aNode.role);
    const { w: bpw, h: bph } = portSize(bNode.role);
    const aAnchor = portAnchor(
      ap,
      aSide,
      aSlot,
      aTotal,
      deviceW(aNode.role),
      apw,
      aph,
    );
    const bAnchor = portAnchor(
      bp,
      bSide,
      bSlot,
      bTotal,
      deviceW(bNode.role),
      bpw,
      bph,
    );

    const aFace = outerAttach(aAnchor, aSide, apw, aph);
    const bFace = outerAttach(bAnchor, bSide, bpw, bph);
    const aStub = stubFrom(aFace, aSide);
    const bStub = stubFrom(bFace, bSide);

    ensurePorts(link.aNode).push({
      port: link.aPort,
      side: aSide,
      x: aAnchor.x,
      y: aAnchor.y,
      w: apw,
      h: aph,
      peerName: link.bNode,
      kind,
    });
    ensurePorts(link.bNode).push({
      port: link.bPort,
      side: bSide,
      x: bAnchor.x,
      y: bAnchor.y,
      w: bpw,
      h: bph,
      peerName: link.aNode,
      kind,
    });

    // Face → stub → stub → face keeps the join in the middle of the port.
    linkEndpoints.set(id, [aFace, aStub, bStub, bFace]);
  }

  const nodes: LaidNode[] = [];
  for (const node of graph.summary.nodes) {
    const pos = positions.get(node.name);
    if (!pos) continue;
    const shortIp = node.ipAddr
      ? multi && node.role !== "bb"
        ? `.${node.ipAddr.split(".").pop()}`
        : node.ipAddr
      : null;
    nodes.push({
      name: node.name,
      role: node.role,
      site: node.site,
      x: pos.x,
      y: pos.y,
      w: deviceW(node.role),
      h: NODE_H,
      title: node.name,
      subtitle:
        node.role === "host"
          ? (() => {
              const via = hostViaLabel(
                node.name,
                graph.links,
                byName,
                positions,
              );
              if (shortIp && via) return `${shortIp} · ${via}`;
              return via ?? shortIp ?? "host";
            })()
          : shortIp,
      ports: portsByNode.get(node.name) ?? [],
    });
  }

  const links: LaidLink[] = [];
  const bundleBuckets = new Map<
    string,
    { a: TopologyNode; b: TopologyNode; paths: LaidPoint[][] }
  >();

  for (const link of graph.links) {
    const a = byName[link.aNode];
    const b = byName[link.bNode];
    if (!a || !b) continue;
    const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
    const points = linkEndpoints.get(id);
    if (!points) continue;
    links.push({
      id,
      points,
      kind: linkKind(a, b),
      aName: link.aNode,
      bName: link.bNode,
      aPort: link.aPort,
      bPort: link.bPort,
    });
    const key = pairKey(link.aNode, link.bNode);
    const bucket = bundleBuckets.get(key) ?? {
      a,
      b,
      paths: [],
    };
    bucket.paths.push(points);
    bundleBuckets.set(key, bucket);
  }

  const bundles: LaidBundle[] = [];
  for (const [key, bucket] of bundleBuckets) {
    if (!showPoForBundle(mode, bucket.a, bucket.b, bucket.paths.length)) continue;
    const mids = bucket.paths.map((pts) => {
      const i = Math.max(0, Math.floor((pts.length - 1) / 2));
      const p = pts[i];
      const q = pts[Math.min(pts.length - 1, i + 1)];
      return { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
    });
    const cx = mids.reduce((s, p) => s + p.x, 0) / mids.length;
    const cy = mids.reduce((s, p) => s + p.y, 0) / mids.length;
    // Always taller than wide (CV Po mark between horizontal peer lines).
    bundles.push({
      id: `po-${key}`,
      cx,
      cy,
      rx: 8,
      ry: 14,
      vertical: true,
    });
  }

  // Dual-homed host ↔ MLAG leaf pair: horizontal Po around the vertical stubs.
  for (const po of dualHomePo) {
    if (po.paths.length < 2) continue;
    const stubs = po.paths.map((pts) => {
      const hostPt = pts[pts.length - 1];
      const above = pts[pts.length - 2] ?? hostPt;
      return {
        x: hostPt.x,
        y0: Math.min(above.y, hostPt.y),
        y1: Math.max(above.y, hostPt.y),
      };
    });
    const minX = Math.min(...stubs.map((s) => s.x));
    const maxX = Math.max(...stubs.map((s) => s.x));
    const minY = Math.min(...stubs.map((s) => s.y0));
    const maxY = Math.max(...stubs.map((s) => s.y1));
    const stubSpanX = Math.max(PORT_W, maxX - minX);
    const stubSpanY = Math.max(10, maxY - minY);
    // Long axis horizontal — wrap both vertical stubs, centered on their length.
    bundles.push({
      id: `po-host-${po.host}`,
      cx: (minX + maxX) / 2,
      cy: (minY + maxY) / 2,
      rx: stubSpanX / 2 + 12,
      ry: Math.max(6, Math.min(stubSpanY / 2 + 2, stubSpanX / 3)),
      vertical: false,
    });
  }

  // Dual-homed leaf ↔ mleaf: horizontal Po around the long stubs under the
  // narrow mleaf (same corridor for every dual-attached member leaf).
  for (const po of dualMleafPo) {
    if (po.stubs.length < 2) continue;
    const minX = Math.min(...po.stubs.map((s) => s.x));
    const maxX = Math.max(...po.stubs.map((s) => s.x));
    const minY = Math.min(...po.stubs.map((s) => s.y0));
    const maxY = Math.max(...po.stubs.map((s) => s.y1));
    const stubSpanX = Math.max(PORT_W, maxX - minX);
    const stubSpanY = Math.max(MLEAF_PO_STUB, maxY - minY);
    bundles.push({
      id: `po-mleaf-${po.mleaf}`,
      cx: (minX + maxX) / 2,
      cy: (minY + maxY) / 2 + 3,
      // 2px tighter each side vs prior (+10 → +8); drop 3px so it sits on the stubs.
      rx: stubSpanX / 2 + 8,
      // 3px shorter overall (−1.5 on each vertical radius).
      ry: Math.max(5, Math.min(stubSpanY / 2 + 2, stubSpanX / 2.5) - 1.5),
      vertical: false,
    });
  }

  return { width, height, title, nodes, links, bundles, domains };
}

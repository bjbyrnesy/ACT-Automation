/** Deterministic CV-style layout for ACT fabric topologies. */

import {
  fabricModeOf,
  roleRank,
  type GraphLink,
  type TopologyGraph,
} from "./graph";
import type { NodeRole, TopologyNode } from "./summary";

export type Side = "top" | "bottom" | "left" | "right";

export type LaidPort = {
  port: number;
  side: Side;
  x: number;
  y: number;
  peerName: string;
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
/** Narrower than fabric switches so several hosts fit beside mleaf stacks. */
const HOST_W = 72;
const PORT_W = 22;
const PORT_H = 14;
/** Default horizontal gap between non-peer devices. */
const H_GAP = 52;
/** Gap inside an MLAG/peer pair (leaf and border pairs). */
const PEER_GAP = 80;
/** Gap between adjacent MLAG domains on the leaf row. */
const PAIR_GAP = 40;
const V_GAP = 96;
/** Leaf row → first member leaf (tighter than fabric V_GAP). */
const MLEAF_DROP = 40;
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

type PairKey = string;

function pairKey(a: string, b: string): PairKey {
  return a < b ? `${a}::${b}` : `${b}::${a}`;
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

/** Row width with wide peer gaps inside pairs and PAIR_GAP between domains. */
function peerGroupsWidth(groups: TopologyNode[][]): number {
  if (!groups.length) return 0;
  let width = 0;
  for (let i = 0; i < groups.length; i += 1) {
    const group = groups[i];
    if (group.length === 2) {
      width += NODE_W + PEER_GAP + NODE_W;
    } else {
      width += group.length * NODE_W + Math.max(0, group.length - 1) * H_GAP;
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
    for (let ni = 0; ni < group.length; ni += 1) {
      positions.set(group[ni].name, { x, y });
      if (ni < group.length - 1) {
        x += NODE_W + (group.length === 2 ? PEER_GAP : H_GAP);
      } else {
        x += NODE_W;
      }
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
        x: stack.cx - NODE_W / 2,
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

/** Parent switch for a host (prefer mleaf, else leaf). */
function hostParentName(
  hostName: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
): string | null {
  for (const link of links) {
    const other =
      link.aNode === hostName
        ? link.bNode
        : link.bNode === hostName
          ? link.aNode
          : null;
    if (!other) continue;
    const node = byName[other];
    if (node?.role === "mleaf" || node?.role === "leaf") return other;
  }
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

/** Short peer label for host subtitles (``blz-MSP-mleaf2`` → ``mleaf2``). */
function shortParentLabel(name: string): string {
  const m = /-((?:m)?leaf\d+)$/i.exec(name);
  return m ? m[1].toLowerCase() : name;
}

/** Bounding box of the leaf pair (or single leaf) that feeds an mleaf column. */
function leafPairBoundsForColumn(
  mleafParent: string,
  links: GraphLink[],
  byName: Record<string, TopologyNode>,
  positions: Map<string, Pos>,
): { left: number; right: number } | null {
  const leaves = mleafParentNames(mleafParent, links, byName);
  const xs = leaves
    .map((name) => positions.get(name))
    .filter((p): p is Pos => p != null);
  // Fall back to the attach parent itself when it is already a leaf.
  if (!xs.length) {
    const self = positions.get(mleafParent);
    const node = byName[mleafParent];
    if (self && node?.role === "leaf") {
      return { left: self.x, right: self.x + NODE_W };
    }
    return null;
  }
  return {
    left: Math.min(...xs.map((p) => p.x)),
    right: Math.max(...xs.map((p) => p.x + NODE_W)),
  };
}

/**
 * Hang hosts under / beside their parent column — never level with mleafs.
 *
 * Deep stacks or multiple hosts: park in vertical lists on both sides of the
 * column (below the lowest switch). Odd switch ports → left rail, even → right.
 * Side rails stay inside the parent leaf-pair width.
 * Single host under a leaf with nothing below: center under the parent.
 * Returns the lowest Y extent used (for site height).
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

  type ColHost = {
    host: TopologyNode;
    parent: string;
    parentY: number;
    parentPort: number;
  };
  type ColGroup = {
    colX: number;
    cx: number;
    bottom: number;
    items: ColHost[];
  };
  const byColumn = new Map<number, ColGroup>();
  const loose: TopologyNode[] = [];

  for (const host of sortNodes(hosts)) {
    const parent = hostParentName(host.name, links, byName);
    const parentPos = parent ? positions.get(parent) : undefined;
    if (!parent || !parentPos) {
      loose.push(host);
      continue;
    }
    const parentPort = hostParentPort(host.name, parent, links) ?? 1;
    const key = Math.round(parentPos.x);
    let col = byColumn.get(key);
    if (!col) {
      col = {
        colX: parentPos.x,
        cx: parentPos.x + NODE_W / 2,
        bottom: columnFabricBottom(parentPos, positions, byName),
        items: [],
      };
      byColumn.set(key, col);
    } else {
      col.bottom = Math.max(
        col.bottom,
        columnFabricBottom(parentPos, positions, byName),
      );
    }
    col.items.push({ host, parent, parentY: parentPos.y, parentPort });
  }

  const HOST_H_GAP = 20;
  let maxBottom = hostRowY;

  const sortColHosts = (items: ColHost[]) => {
    items.sort((a, b) => {
      if (a.parentY !== b.parentY) return a.parentY - b.parentY;
      if (a.parentPort !== b.parentPort) return a.parentPort - b.parentPort;
      if (a.parent !== b.parent) return a.parent.localeCompare(b.parent);
      return a.host.name.localeCompare(b.host.name);
    });
  };

  const stackSide = (items: ColHost[], x: number, startY: number): number => {
    let y = startY;
    for (const item of items) {
      positions.set(item.host.name, { x, y });
      y += NODE_H + HOST_H_GAP;
    }
    return items.length ? y - HOST_H_GAP : startY;
  };

  for (const col of byColumn.values()) {
    sortColHosts(col.items);

    const deepOrMany =
      col.items.length > 1 ||
      col.items.some((item) => {
        const p = positions.get(item.parent)!;
        return col.bottom > p.y + NODE_H + 1;
      });

    if (deepOrMany) {
      const left = col.items.filter((item) => item.parentPort % 2 === 1);
      const right = col.items.filter((item) => item.parentPort % 2 === 0);
      const startY = col.bottom + HOST_DROP;
      // Keep host rails inside the leaf-pair footprint that owns this stack.
      const bounds = leafPairBoundsForColumn(
        col.items[0].parent,
        links,
        byName,
        positions,
      );
      const pairLeft = bounds?.left ?? col.colX - HOST_W;
      const pairRight = bounds?.right ?? col.colX + NODE_W + HOST_W;
      const leftX = pairLeft;
      const rightX = pairRight - HOST_W;
      maxBottom = Math.max(
        maxBottom,
        stackSide(left, leftX, startY),
        stackSide(right, rightX, startY),
      );
    } else {
      const y = col.items[0]
        ? positions.get(col.items[0].parent)!.y + NODE_H + HOST_DROP
        : hostRowY;
      const rowW =
        col.items.length * HOST_W + (col.items.length - 1) * HOST_H_GAP;
      let x = col.cx - rowW / 2;
      for (const item of col.items) {
        positions.set(item.host.name, { x, y });
        x += HOST_W + HOST_H_GAP;
      }
      maxBottom = Math.max(maxBottom, y + NODE_H);
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

  const width =
    MARGIN * 2 + Math.max(totalSitesW, peerGroupsWidth(bbGroups));
  const height = MARGIN * 2 + 28 + bbRowH + siteHeight;

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
    const x = Math.min(lp.x, rp.x) - MLAG_PAD;
    const y = Math.min(lp.y, rp.y) - MLAG_PAD;
    const w = Math.abs(rp.x - lp.x) + NODE_W + MLAG_PAD * 2;
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
    const dx = to.x + NODE_W / 2 - (from.x + NODE_W / 2);
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
  ): { x: number; y: number } {
    const spread = Math.max(1, totalHint);
    const t = (slot + 1) / (spread + 1);
    if (side === "top") {
      return { x: pos.x + NODE_W * t - PORT_W / 2, y: pos.y - PORT_H };
    }
    if (side === "bottom") {
      return { x: pos.x + NODE_W * t - PORT_W / 2, y: pos.y + NODE_H };
    }
    if (side === "left") {
      return { x: pos.x - PORT_W, y: pos.y + NODE_H * t - PORT_H / 2 };
    }
    return { x: pos.x + NODE_W, y: pos.y + NODE_H * t - PORT_H / 2 };
  }

  /** Midpoint of the port face away from the device (where the link attaches). */
  function outerAttach(anchor: LaidPoint, side: Side): LaidPoint {
    const cx = anchor.x + PORT_W / 2;
    const cy = anchor.y + PORT_H / 2;
    if (side === "top") return { x: cx, y: anchor.y };
    if (side === "bottom") return { x: cx, y: anchor.y + PORT_H };
    if (side === "left") return { x: anchor.x, y: cy };
    return { x: anchor.x + PORT_W, y: cy };
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
  ): LaidPoint {
    const n = Math.max(1, total);
    const pitch = PORT_W + 4;
    const edgePad = 4;
    const usable = Math.max(0, NODE_W - edgePad * 2 - PORT_W);
    const naturalSpan = n <= 1 ? 0 : (n - 1) * pitch;
    const span = n <= 1 ? 0 : Math.min(naturalSpan, usable);
    const step = n <= 1 ? 0 : span / (n - 1);
    const fromInner = edgePad + slotFromInner * step;
    const x = innerIsRight
      ? pos.x + NODE_W - PORT_W - fromInner
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
    const n = group.length;
    const span = Math.min(NODE_H - PORT_H, Math.max(PORT_H, (n - 1) * 18 + PORT_H));
    const startY = leftPos.y + (NODE_H - span) / 2;

    for (let i = 0; i < group.length; i += 1) {
      const { link } = group[i];
      const t = n === 1 ? 0.5 : i / (n - 1);
      const y = startY + t * (span - PORT_H);
      const leftPort = link.aNode === leftName ? link.aPort : link.bPort;
      const rightPort = link.aNode === rightName ? link.aPort : link.bPort;
      const leftAnchor = { x: leftPos.x + NODE_W, y };
      const rightAnchor = { x: rightPos.x - PORT_W, y };

      ensurePorts(leftName).push({
        port: leftPort,
        side: "right",
        x: leftAnchor.x,
        y: leftAnchor.y,
        peerName: rightName,
      });
      ensurePorts(rightName).push({
        port: rightPort,
        side: "left",
        x: rightAnchor.x,
        y: rightAnchor.y,
        peerName: leftName,
      });

      const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
      placedIds.add(id);
      const leftFace = outerAttach(leftAnchor, "right");
      const rightFace = outerAttach(rightAnchor, "left");
      linkEndpoints.set(id, [leftFace, rightFace]);
    }
  }

  // Member-leaf uplinks: first mleaf gets centered verticals into top ports;
  // deeper stack members keep the side-elbow path.
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

      for (let i = 0; i < depth; i += 1) {
        const mleafName = stack.mleafs[i];
        const mPos = positions.get(mleafName);
        if (!mPos) continue;

        const findLink = (leafName: string): GraphLink | undefined =>
          mleafLinks.find(
            (l) =>
              (l.aNode === leafName && l.bNode === mleafName) ||
              (l.bNode === leafName && l.aNode === mleafName),
          );

        const placeUplink = (
          leafName: string,
          leafPos: Pos,
          innerIsRight: boolean,
        ) => {
          const link = findLink(leafName);
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
            // First mleaf: straight vertical into top port, centered on both
            // interface blocks — no horizontal elbow/stub.
            const mleafAnchor = {
              x: leafAnchor.x,
              y: mPos.y - PORT_H,
            };
            ensurePorts(leafName).push({
              port: leafPort,
              side: "bottom",
              x: leafAnchor.x,
              y: leafAnchor.y,
              peerName: mleafName,
            });
            ensurePorts(mleafName).push({
              port: mleafPort,
              side: "top",
              x: mleafAnchor.x,
              y: mleafAnchor.y,
              peerName: leafName,
            });
            const leafFace = outerAttach(leafAnchor, "bottom");
            const mleafFace = outerAttach(mleafAnchor, "top");
            linkEndpoints.set(id, [leafFace, mleafFace]);
            placedIds.add(id);
            return;
          }

          // Deeper stack: vertical from leaf, then 90° into mleaf side.
          const side: Side = leafName === stack.leftLeaf ? "left" : "right";
          const mleafAnchor =
            side === "left"
              ? {
                  x: mPos.x - PORT_W,
                  y: mPos.y + NODE_H / 2 - PORT_H / 2,
                }
              : {
                  x: mPos.x + NODE_W,
                  y: mPos.y + NODE_H / 2 - PORT_H / 2,
                };

          ensurePorts(leafName).push({
            port: leafPort,
            side: "bottom",
            x: leafAnchor.x,
            y: leafAnchor.y,
            peerName: mleafName,
          });
          ensurePorts(mleafName).push({
            port: mleafPort,
            side,
            x: mleafAnchor.x,
            y: mleafAnchor.y,
            peerName: leafName,
          });

          const leafFace = outerAttach(leafAnchor, "bottom");
          const leafStub = stubFrom(leafFace, "bottom");
          const mleafFace = outerAttach(mleafAnchor, side);
          const mleafStub = stubFrom(mleafFace, side);
          const elbow = { x: leafStub.x, y: mleafStub.y };
          linkEndpoints.set(id, [
            leafFace,
            leafStub,
            elbow,
            mleafStub,
            mleafFace,
          ]);
          placedIds.add(id);
        };

        placeUplink(stack.leftLeaf, leftPos, true);
        placeUplink(stack.rightLeaf, rightPos, false);
      }
    }
  }

  // Host uplinks: left/right side-rail hosts get dedicated lanes; under-parent
  // hosts stay vertical into top ports.
  type HostRoute = {
    link: GraphLink;
    hostNode: TopologyNode;
    parentNode: TopologyNode;
    hostPos: Pos;
    parentPos: Pos;
    rail: "left" | "right" | null;
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
    let rail: "left" | "right" | null = null;
    if (hostPos.x + HOST_W <= parentPos.x + 2) rail = "left";
    else if (hostPos.x >= parentPos.x + NODE_W - 2) rail = "right";
    hostRoutes.push({ link, hostNode, parentNode, hostPos, parentPos, rail });
  }

  // Lane index per parent on each side (stable by parent Y).
  const parentLane = new Map<string, number>();
  for (const side of ["left", "right"] as const) {
    const parents = [
      ...new Set(
        hostRoutes
          .filter((h) => h.rail === side)
          .map((h) => h.parentNode.name),
      ),
    ].sort((a, b) => {
      const ay = positions.get(a)?.y ?? 0;
      const by = positions.get(b)?.y ?? 0;
      return ay !== by ? ay - by : a.localeCompare(b);
    });
    parents.forEach((name, i) => parentLane.set(`${side}:${name}`, i));
  }

  const sideHostSlot = new Map<string, number>();
  const sideHostCount = new Map<string, number>();
  for (const item of hostRoutes) {
    if (!item.rail) continue;
    const key = `${item.rail}:${item.parentNode.name}`;
    sideHostCount.set(key, (sideHostCount.get(key) ?? 0) + 1);
  }

  for (const item of hostRoutes) {
    const { link, hostNode, parentNode, hostPos, parentPos, rail } = item;
    const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
    if (placedIds.has(id)) continue;

    const hostPort =
      link.aNode === hostNode.name ? link.aPort : link.bPort;
    const parentPort =
      link.aNode === parentNode.name ? link.aPort : link.bPort;

    if (rail) {
      const laneKey = `${rail}:${parentNode.name}`;
      const lane = parentLane.get(laneKey) ?? 0;
      const slot = sideHostSlot.get(laneKey) ?? 0;
      sideHostSlot.set(laneKey, slot + 1);
      const slots = sideHostCount.get(laneKey) ?? 1;
      const t = (slot + 1) / (slots + 1);
      const parentSide: Side = rail === "left" ? "left" : "right";
      const hostSide: Side = rail === "left" ? "right" : "left";
      // Place lanes in the gap between host face and mleaf face.
      const gapOuter =
        rail === "left" ? hostPos.x + HOST_W : parentPos.x + NODE_W;
      const gapInner = rail === "left" ? parentPos.x : hostPos.x;
      const gap = Math.max(0, gapInner - gapOuter);
      const laneCount = Math.max(
        1,
        [...parentLane.keys()].filter((k) => k.startsWith(`${rail}:`)).length,
      );
      const laneX =
        gapOuter + (gap * (lane + 1)) / (laneCount + 1);
      const parentAnchor =
        rail === "left"
          ? {
              x: parentPos.x - PORT_W,
              y: parentPos.y + NODE_H * t - PORT_H / 2,
            }
          : {
              x: parentPos.x + NODE_W,
              y: parentPos.y + NODE_H * t - PORT_H / 2,
            };
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
        peerName: hostNode.name,
      });
      ensurePorts(hostNode.name).push({
        port: hostPort,
        side: hostSide,
        x: hostAnchor.x,
        y: hostAnchor.y,
        peerName: parentNode.name,
      });

      const parentFace = outerAttach(parentAnchor, parentSide);
      const parentStub = stubFrom(parentFace, parentSide);
      const hostFace = outerAttach(hostAnchor, hostSide);
      const hostStub = stubFrom(hostFace, hostSide);
      const midTop = { x: laneX, y: parentStub.y };
      const midBot = { x: laneX, y: hostStub.y };
      linkEndpoints.set(id, [
        parentFace,
        parentStub,
        midTop,
        midBot,
        hostStub,
        hostFace,
      ]);
    } else {
      const hostCx = hostPos.x + HOST_W / 2;
      const parentAnchor = {
        x: Math.min(
          parentPos.x + NODE_W - PORT_W - 2,
          Math.max(parentPos.x + 2, hostCx - PORT_W / 2),
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
        peerName: hostNode.name,
      });
      ensurePorts(hostNode.name).push({
        port: hostPort,
        side: "top",
        x: hostAnchor.x,
        y: hostAnchor.y,
        peerName: parentNode.name,
      });

      const parentFace = outerAttach(parentAnchor, "bottom");
      const parentStub = stubFrom(parentFace, "bottom");
      const hostFace = outerAttach(hostAnchor, "top");
      const hostStub = stubFrom(hostFace, "top");
      if (Math.abs(parentStub.x - hostStub.x) < 2) {
        linkEndpoints.set(id, [parentFace, parentStub, hostStub, hostFace]);
      } else {
        const elbow = { x: parentStub.x, y: hostStub.y };
        linkEndpoints.set(id, [
          parentFace,
          parentStub,
          elbow,
          hostStub,
          hostFace,
        ]);
      }
    }
    placedIds.add(id);
  }

  for (const { link, aSide, bSide } of pending) {
    const id = `${link.aNode}:${link.aPort}-${link.bNode}:${link.bPort}`;
    if (placedIds.has(id)) continue;

    const ap = positions.get(link.aNode)!;
    const bp = positions.get(link.bNode)!;
    const aTotal = totals.get(link.aNode)?.[aSide] ?? 1;
    const bTotal = totals.get(link.bNode)?.[bSide] ?? 1;
    const aSlot = nextSlot(link.aNode, aSide);
    const bSlot = nextSlot(link.bNode, bSide);
    const aAnchor = portAnchor(ap, aSide, aSlot, aTotal);
    const bAnchor = portAnchor(bp, bSide, bSlot, bTotal);

    const aFace = outerAttach(aAnchor, aSide);
    const bFace = outerAttach(bAnchor, bSide);
    const aStub = stubFrom(aFace, aSide);
    const bStub = stubFrom(bFace, bSide);

    ensurePorts(link.aNode).push({
      port: link.aPort,
      side: aSide,
      x: aAnchor.x,
      y: aAnchor.y,
      peerName: link.bNode,
    });
    ensurePorts(link.bNode).push({
      port: link.bPort,
      side: bSide,
      x: bAnchor.x,
      y: bAnchor.y,
      peerName: link.aNode,
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
      w: node.role === "host" ? HOST_W : NODE_W,
      h: NODE_H,
      title: node.name,
      subtitle:
        node.role === "host"
          ? (() => {
              const parent = hostParentName(node.name, graph.links, byName);
              const via = parent ? shortParentLabel(parent) : null;
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

  return { width, height, title, nodes, links, bundles, domains };
}

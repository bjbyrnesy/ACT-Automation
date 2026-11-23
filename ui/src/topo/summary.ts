/** Client-side inventory parsed from ACT topology YAML. */

export type NodeRole = "bb" | "border" | "spine" | "leaf" | "mleaf" | "other";

export type TopologyNode = {
  name: string;
  role: NodeRole;
  site: string | null;
  ipAddr: string | null;
};

export type TopologySummary = {
  fabricMode: string | null;
  useCase: string | null;
  title: string | null;
  nodeCount: number;
  linkCount: number;
  sites: string[];
  nodes: TopologyNode[];
  bySite: Record<string, TopologyNode[]>;
  byRole: Record<NodeRole, number>;
};

const ROLE_ORDER: NodeRole[] = ["bb", "border", "spine", "leaf", "mleaf", "other"];

const NODE_KEY_RE = /^ {2}- ([A-Za-z0-9][\w.-]*):\s*$/;
const MODE_RE = /^# capacity:.*\bfabric_mode=(\S+)/m;
const USE_CASE_RE = /^# capacity:.*\buse_case=(\S+)/m;
const MULTI_RE =
  /-(?<site>[A-Za-z0-9][A-Za-z0-9_-]*)-(?<role>border|spine|leaf|mleaf)(?<index>[1-9]\d*)$/;
const BB_RE = /-bb(?<index>[1-9]\d*)$/;
const SINGLE_RE = /-(?<role>border|spine|leaf|mleaf)(?<index>[1-9]\d*)$/;
const LINK_RE = /^ {2}- connection:/;

function classify(name: string): { role: NodeRole; site: string | null } {
  const multi = MULTI_RE.exec(name);
  if (multi?.groups) {
    return {
      role: multi.groups.role as NodeRole,
      site: multi.groups.site,
    };
  }
  if (BB_RE.test(name)) {
    return { role: "bb", site: null };
  }
  const single = SINGLE_RE.exec(name);
  if (single?.groups) {
    return { role: single.groups.role as NodeRole, site: null };
  }
  return { role: "other", site: null };
}

function emptyRoleCounts(): Record<NodeRole, number> {
  return { bb: 0, border: 0, spine: 0, leaf: 0, mleaf: 0, other: 0 };
}

/** Parse ACT YAML into a compact inventory for the workspace pane. */
export function parseTopologySummary(yamlText: string): TopologySummary | null {
  const text = yamlText.trim();
  if (!text) return null;

  const fabricMode = MODE_RE.exec(text)?.[1] ?? null;
  const useCase = USE_CASE_RE.exec(text)?.[1] ?? null;

  const nodes: TopologyNode[] = [];
  let inNodes = false;
  let pending: TopologyNode | null = null;

  for (const line of text.split("\n")) {
    if (!inNodes) {
      if (line.trim() === "nodes:" && !line.startsWith(" ")) {
        inNodes = true;
      }
      continue;
    }
    if (line && !line.startsWith(" ") && !line.startsWith("#")) {
      if (pending) nodes.push(pending);
      pending = null;
      break;
    }
    const key = NODE_KEY_RE.exec(line);
    if (key) {
      if (pending) nodes.push(pending);
      const name = key[1];
      const { role, site } = classify(name);
      pending = { name, role, site, ipAddr: null };
      continue;
    }
    if (pending) {
      const ip = /^\s+ip_addr:\s*(\S+)/.exec(line);
      if (ip) pending.ipAddr = ip[1];
    }
  }
  if (pending) nodes.push(pending);

  let linkCount = 0;
  let inLinks = false;
  for (const line of text.split("\n")) {
    if (!inLinks) {
      if (line.trim() === "links:" && !line.startsWith(" ")) {
        inLinks = true;
      }
      continue;
    }
    if (line && !line.startsWith(" ") && !line.startsWith("#")) break;
    if (LINK_RE.test(line)) linkCount += 1;
  }

  const byRole = emptyRoleCounts();
  const bySite: Record<string, TopologyNode[]> = {};
  const siteSet = new Set<string>();

  for (const node of nodes) {
    byRole[node.role] += 1;
    const bucket = node.site ?? (node.role === "bb" ? "core" : "fabric");
    siteSet.add(bucket);
    (bySite[bucket] ??= []).push(node);
  }

  const sites = [...siteSet].sort((a, b) => {
    if (a === "core") return -1;
    if (b === "core") return 1;
    return a.localeCompare(b);
  });

  for (const site of sites) {
    bySite[site].sort((a, b) => {
      const ri = ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role);
      return ri !== 0 ? ri : a.name.localeCompare(b.name);
    });
  }

  // Prefer fabric prefix: strip `-{site}-{role}{n}` or bare `-{role}{n}` / `-bb{n}`.
  let title: string | null = null;
  if (nodes[0]) {
    const multiTitle = MULTI_RE.exec(nodes[0].name);
    if (multiTitle) {
      title = nodes[0].name.slice(0, multiTitle.index);
    } else {
      title =
        nodes[0].name.replace(/-(?:bb|border|spine|leaf|mleaf)\d+$/, "") || null;
      if (title === nodes[0].name) title = null;
    }
  }

  return {
    fabricMode,
    useCase,
    title,
    nodeCount: nodes.length,
    linkCount,
    sites,
    nodes,
    bySite,
    byRole,
  };
}

export function roleLabel(role: NodeRole): string {
  switch (role) {
    case "bb":
      return "backbone";
    case "mleaf":
      return "member leaf";
    default:
      return role;
  }
}

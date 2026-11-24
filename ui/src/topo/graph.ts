/** Parse ACT topology YAML into a graph for the CV-style diagram. */

import {
  applyMgmtIps,
  assignHostSites,
  parseTopologySummary,
  rebuildSiteIndex,
  type NodeRole,
  type TopologyNode,
  type TopologySummary,
} from "./summary";

export type GraphLink = {
  aNode: string;
  aPort: number;
  bNode: string;
  bPort: number;
};

export type TopologyGraph = {
  summary: TopologySummary;
  links: GraphLink[];
  byName: Record<string, TopologyNode>;
};

const CONN_RE =
  /connection:\s*\[([^:]+):Ethernet(\d+),\s*([^:]+):Ethernet(\d+)\]/g;

export type ParseTopologyOptions = {
  /** Prefer clab/live management IPs over ACT ``ip_addr`` placeholders. */
  mgmtIps?: Record<string, string> | null;
};

/** Full topology graph (nodes from summary + Ethernet connections). */
export function parseTopologyGraph(
  yamlText: string,
  options: ParseTopologyOptions = {},
): TopologyGraph | null {
  const summary = parseTopologySummary(yamlText);
  if (!summary || summary.nodeCount === 0) return null;

  applyMgmtIps(summary.nodes, options.mgmtIps);

  const links: GraphLink[] = [];
  for (const match of yamlText.matchAll(CONN_RE)) {
    links.push({
      aNode: match[1].trim(),
      aPort: Number(match[2]),
      bNode: match[3].trim(),
      bPort: Number(match[4]),
    });
  }

  assignHostSites(summary.nodes, links);
  rebuildSiteIndex(summary);

  const byName: Record<string, TopologyNode> = {};
  for (const node of summary.nodes) {
    byName[node.name] = node;
  }

  return { summary, links, byName };
}

export function fabricModeOf(graph: TopologyGraph): "l3ls" | "l2ls" {
  const mode = graph.summary.fabricMode?.toLowerCase();
  if (mode === "l2ls" || mode === "l3ls") return mode;
  return graph.summary.byRole.border > 0 ? "l3ls" : "l2ls";
}

export function roleRank(role: NodeRole): number {
  switch (role) {
    case "bb":
      return 0;
    case "border":
      return 1;
    case "spine":
      return 2;
    case "leaf":
      return 3;
    case "mleaf":
      return 4;
    default:
      return 5;
  }
}

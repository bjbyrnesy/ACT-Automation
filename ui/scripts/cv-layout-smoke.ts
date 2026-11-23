/**
 * Smoke checks for CV layout (run: npx tsx scripts/cv-layout-smoke.ts).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseTopologyGraph } from "../src/topo/graph.ts";
import { layoutCvDiagram } from "../src/topo/cvLayout.ts";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const here = fileURLToPath(new URL(".", import.meta.url));
const yamlPath = resolve(here, "../../topology-blz3-2026-11-21.yml");
const yaml = readFileSync(yamlPath, "utf8");
const graph = parseTopologyGraph(yaml);
assert(graph, "parseTopologyGraph failed");
const lay = layoutCvDiagram(graph);

const leaf1 = lay.nodes.find((n) => n.name.endsWith("B-leaf1"));
const leaf2 = lay.nodes.find((n) => n.name.endsWith("B-leaf2"));
assert(leaf1 && leaf2, "missing B leaf pair");
const peerGap = leaf2.x - (leaf1.x + leaf1.w);
assert(peerGap === 80, `expected PEER_GAP 80, got ${peerGap}`);

const mleaf = lay.nodes.find((n) => n.name.includes("B-mleaf1"));
assert(mleaf, "missing B-mleaf1");
const pairMid = (leaf1.x + leaf2.x + leaf2.w) / 2;
const mMid = mleaf.x + mleaf.w / 2;
assert(Math.abs(pairMid - mMid) < 0.5, `mleaf not centered (${pairMid} vs ${mMid})`);
assert(
  mleaf.y - (leaf1.y + leaf1.h) === 40,
  `expected MLEAF_DROP 40, got ${mleaf.y - (leaf1.y + leaf1.h)}`,
);

const host = lay.nodes.find((n) => n.name === "bar");
assert(host, "missing host bar");
assert(
  Math.abs(host.x - mleaf.x) < 0.5,
  `host not under mleaf (${host.x} vs ${mleaf.x})`,
);

const mlag = lay.domains.filter((d) => d.kind === "mlag");
assert(mlag.length >= 1, "expected MLAG domains");

const peer = lay.links.find(
  (l) => l.kind === "peer" && l.aName.includes("leaf") && l.bName.includes("leaf"),
);
assert(peer, "missing leaf peer link");
assert(
  peer.points.every((p, i, arr) => i === 0 || Math.abs(p.y - arr[0].y) < 0.01),
  "peer link not horizontal",
);

console.log("cvLayout smoke ok", {
  nodes: lay.nodes.length,
  links: lay.links.length,
  bundles: lay.bundles.length,
  mlag: mlag.length,
});

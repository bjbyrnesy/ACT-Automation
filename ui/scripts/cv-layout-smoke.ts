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
assert(
  mleaf.w < leaf1.w,
  `mleaf should be narrower than leaf (${mleaf.w} vs ${leaf1.w})`,
);
const pairMid = (leaf1.x + leaf2.x + leaf2.w) / 2;
const mMid = mleaf.x + mleaf.w / 2;
assert(Math.abs(pairMid - mMid) < 0.5, `mleaf not centered (${pairMid} vs ${mMid})`);
assert(
  mleaf.y - (leaf1.y + leaf1.h) === 40,
  `expected MLEAF_DROP 40, got ${mleaf.y - (leaf1.y + leaf1.h)}`,
);

const host = lay.nodes.find((n) => n.name === "bar");
assert(host, "missing host bar");
// bar → B-mleaf1:et9 (odd) → left rail of the leaf-pair footprint.
assert(host.w === 88, `expected host width 88, got ${host.w}`);
assert(
  Math.abs(host.x - leaf1.x) < 0.5,
  `mleaf host should sit on left rail (odd et), got x=${host.x} pairLeft=${leaf1.x}`,
);
assert(
  host.subtitle != null && /:et\d+$/.test(host.subtitle),
  `expected host subtitle with switchport (mleafN:etN), got ${host.subtitle}`,
);
assert(host.y >= mleaf.y + mleaf.h, "host must sit below mleaf stack");

// foo is dual-homed to A-leaf1+leaf2 → MLAG centerline + Po mark.
const foo = lay.nodes.find((n) => n.name === "foo");
assert(foo, "missing host foo");
const aLeaf1 = lay.nodes.find((n) => n.name.endsWith("A-leaf1"));
const aLeaf2 = lay.nodes.find((n) => n.name.endsWith("A-leaf2"));
assert(aLeaf1 && aLeaf2, "missing A leaf pair");
const aMid = (aLeaf1.x + aLeaf2.x + aLeaf2.w) / 2;
assert(
  Math.abs(foo.x + foo.w / 2 - aMid) < 0.5,
  `dual-home foo should sit on MLAG centerline (${foo.x + foo.w / 2} vs ${aMid})`,
);
assert(
  foo.subtitle != null && foo.subtitle.includes("·"),
  `dual-home subtitle should list both leaves, got ${foo.subtitle}`,
);
const fooPo = lay.bundles.find((b) => b.id === "po-host-foo");
assert(fooPo, "expected Po bundle for dual-homed foo");
assert(
  fooPo.rx > fooPo.ry,
  `dual-home Po should be horizontal (rx>ry), got rx=${fooPo.rx} ry=${fooPo.ry}`,
);

// With an mleaf + mleaf-rail host (foobar), dual-home foo sits below the rail.
const foobar = lay.nodes.find((n) => n.name === "foobar");
assert(foobar, "missing host foobar");
assert(
  foo.y >= foobar.y + foobar.h,
  `dual-home foo should sit below single-attached foobar (${foo.y} vs ${foobar.y}+${foobar.h})`,
);

// Dual-home legs must not cut through the mleaf box (segment sample).
const aMleaf = lay.nodes.find((n) => n.name.includes("A-mleaf1"));
assert(aMleaf, "missing A-mleaf1");
assert(
  aMleaf.w < aLeaf1.w,
  `A-mleaf should be narrower than leaf (${aMleaf.w} vs ${aLeaf1.w})`,
);
const fooLinks = lay.links.filter(
  (l) => l.aName === "foo" || l.bName === "foo",
);
assert(fooLinks.length === 2, "foo should have two access links");
for (const link of fooLinks) {
  for (let i = 1; i < link.points.length; i += 1) {
    const a = link.points[i - 1];
    const b = link.points[i];
    for (const t of [0.25, 0.5, 0.75]) {
      const x = a.x + (b.x - a.x) * t;
      const y = a.y + (b.y - a.y) * t;
      const inside =
        x >= aMleaf.x &&
        x <= aMleaf.x + aMleaf.w &&
        y >= aMleaf.y &&
        y <= aMleaf.y + aMleaf.h;
      assert(
        !inside,
        `foo link segment crosses A-mleaf1 at (${x.toFixed(1)},${y.toFixed(1)})`,
      );
    }
  }
}

// First dual-home must not sit on the far outer bottom corners of the leaves.
for (const leaf of [aLeaf1, aLeaf2]) {
  const hostPorts = leaf.ports.filter((p) => p.side === "bottom" && p.kind === "host");
  assert(hostPorts.length >= 1, `${leaf.name} missing dual-home bottom port`);
  for (const port of hostPorts) {
    const onFarOuter =
      Math.abs(port.x - leaf.x) <= 6 ||
      Math.abs(port.x + 22 - (leaf.x + leaf.w)) <= 6;
    assert(
      !onFarOuter,
      `${leaf.name} dual-home port still on far outer edge (x=${port.x}, leaf=${leaf.x}..${leaf.x + leaf.w})`,
    );
  }
}

// foobar ↔ mleaf: leave port face center with a short stub (≤8px), not a long
// unused horizontal at the switchport.
const foobarLink = lay.links.find(
  (l) =>
    (l.aName === "foobar" && l.bName.includes("A-mleaf1")) ||
    (l.bName === "foobar" && l.aName.includes("A-mleaf1")),
);
assert(foobarLink, "missing foobar↔A-mleaf1 link");
{
  const mleafPort = aMleaf.ports.find((p) => p.kind === "host" && p.side === "left");
  assert(mleafPort, "A-mleaf1 missing left host port");
  const faceY = mleafPort.y + 14 / 2;
  const faceX = mleafPort.x; // left face
  const start = foobarLink.points[0];
  const nearMleaf =
    Math.abs(start.x - faceX) < Math.abs(foobarLink.points[foobarLink.points.length - 1].x - faceX)
      ? start
      : foobarLink.points[foobarLink.points.length - 1];
  assert(
    Math.abs(nearMleaf.y - faceY) <= 1,
    `foobar link should hit mleaf et center (y=${nearMleaf.y} vs face ${faceY})`,
  );
  const second = foobarLink.points[1];
  const stubLen = Math.hypot(second.x - nearMleaf.x, second.y - nearMleaf.y);
  assert(stubLen <= 8, `mleaf host stub too long (${stubLen})`);
}

// Dual-home: no long horizontal jog at the leaf-bottom stub row.
for (const link of fooLinks) {
  const leafEnd = link.points[0];
  const next = link.points[1];
  const third = link.points[2];
  assert(next, "foo link too short");
  // First step is a short vertical stub.
  assert(
    Math.abs(next.x - leafEnd.x) <= 1 && next.y > leafEnd.y,
    "foo dual-home should stub vertically off the leaf port",
  );
  if (third) {
    assert(
      Math.abs(third.x - next.x) <= 1 || third.y > next.y + 4,
      "foo dual-home should not take a long horizontal at the leaf bottom",
    );
  }
}

// Host rails must not cover leaf↔mleaf uplink elbows on the same face.
for (const node of lay.nodes) {
  for (const side of ["left", "right"] as const) {
    const hosts = node.ports.filter((p) => p.side === side && p.kind === "host");
    const uplinks = node.ports.filter(
      (p) => p.side === side && p.kind === "uplink",
    );
    for (const hostPort of hosts) {
      for (const up of uplinks) {
        const dy = Math.abs(hostPort.y - up.y);
        assert(
          dy >= 14,
          `${node.name} ${side}: host et${hostPort.port} covers uplink et${up.port} (dy=${dy})`,
        );
      }
    }
  }
}

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

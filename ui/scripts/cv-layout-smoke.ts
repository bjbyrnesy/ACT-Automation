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
  mleaf.y - (leaf1.y + leaf1.h) === 52,
  `expected MLEAF_DROP 52, got ${mleaf.y - (leaf1.y + leaf1.h)}`,
);

const host = lay.nodes.find((n) => n.name === "bar");
assert(host, "missing host bar");
// bar → B-mleaf1:et9 (odd) → host-band column under the B leaf pair.
assert(host.w === 88, `expected host width 88, got ${host.w}`);
assert(
  host.x + host.w / 2 >= leaf1.x - 2 &&
    host.x + host.w / 2 <= leaf2.x + leaf2.w + 2,
  `mleaf host should sit under the leaf-pair span (x=${host.x})`,
);
assert(
  host.subtitle != null && /:et\d+$/.test(host.subtitle),
  `expected host subtitle with switchport (mleafN:etN), got ${host.subtitle}`,
);
assert(
  host.y >= mleaf.y + mleaf.h,
  `mleaf host must sit in host band below mleaf (host.y=${host.y} mleaf bottom=${mleaf.y + mleaf.h})`,
);

// foo is dual-homed to A-leaf1+leaf2 → MLAG centerline + Po mark.
const foo = lay.nodes.find((n) => n.name === "foo");
assert(foo, "missing host foo");
const aLeaf1 = lay.nodes.find((n) => n.name.endsWith("A-leaf1"));
const aLeaf2 = lay.nodes.find((n) => n.name.endsWith("A-leaf2"));
assert(aLeaf1 && aLeaf2, "missing A leaf pair");
const aPairLeft = Math.min(aLeaf1.x, aLeaf2.x);
const aPairRight = Math.max(aLeaf1.x + aLeaf1.w, aLeaf2.x + aLeaf2.w);
assert(
  foo.x + foo.w / 2 >= aPairLeft - 2 &&
    foo.x + foo.w / 2 <= aPairRight + 2,
  `dual-home foo should sit under the A leaf-pair span (${foo.x + foo.w / 2} in ${aPairLeft}..${aPairRight})`,
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

// Dual-attached member leaves: horizontal Po around long stubs under the
// narrow mleaf (not spanning the wide leaf bottoms).
for (const site of ["A", "B", "C"]) {
  const siteLeaf = lay.nodes.find((n) => n.name.endsWith(`${site}-leaf1`));
  const ml = lay.nodes.find((n) => n.name.includes(`${site}-mleaf1`));
  assert(siteLeaf && ml, `missing ${site} leaf/mleaf`);
  const po = lay.bundles.find((b) => b.id === `po-mleaf-${ml.name}`);
  assert(po, `expected Po bundle for dual-homed ${ml.name}`);
  assert(
    po.rx > po.ry,
    `${ml.name} Po should be horizontal (rx>ry), got rx=${po.rx} ry=${po.ry}`,
  );
  assert(
    po.cy > siteLeaf.y + siteLeaf.h && po.cy < ml.y,
    `${ml.name} Po should sit in the leaf→mleaf stub gap (cy=${po.cy})`,
  );
  assert(
    po.cx >= ml.x - 2 && po.cx <= ml.x + ml.w + 2,
    `${ml.name} Po should center under the narrow mleaf (cx=${po.cx} mleaf=${ml.x}..${ml.x + ml.w})`,
  );
  assert(
    po.rx * 2 <= ml.w + 24,
    `${ml.name} Po should fit the narrow mleaf corridor (rx=${po.rx} mleaf.w=${ml.w})`,
  );
  const uplinkLinks = lay.links.filter(
    (l) =>
      l.kind !== "host" &&
      (l.aName === ml.name || l.bName === ml.name) &&
      (l.aName.includes("leaf") || l.bName.includes("leaf")),
  );
  assert(uplinkLinks.length >= 2, `${ml.name} should have dual uplinks`);
  for (const link of uplinkLinks) {
    // Long vertical stub sits under the mleaf after the inward jog.
    let longStub = 0;
    let longStubX = 0;
    for (let i = 1; i < link.points.length; i += 1) {
      const a = link.points[i - 1];
      const b = link.points[i];
      if (Math.abs(a.x - b.x) <= 1 && b.y > a.y) {
        const len = b.y - a.y;
        if (len > longStub) {
          longStub = len;
          longStubX = a.x;
        }
      }
    }
    assert(
      longStub >= 16,
      `${ml.name} dual uplink stub too short for Po (${longStub})`,
    );
    assert(
      longStubX >= ml.x - 2 && longStubX <= ml.x + ml.w + 2,
      `${ml.name} long stub must run under mleaf (x=${longStubX})`,
    );
  }
}

// Dual-home legs must not cut through the mleaf box (segment sample).
const aMleaf = lay.nodes.find((n) => n.name.includes("A-mleaf1"));
assert(aMleaf, "missing A-mleaf1");
assert(
  aMleaf.w < aLeaf1.w,
  `A-mleaf should be narrower than leaf (${aMleaf.w} vs ${aLeaf1.w})`,
);

// foobar (mleaf rail) and foo (dual) share the host band under site A —
// distinct columns, no box overlap (checked globally below).
const foobar = lay.nodes.find((n) => n.name === "foobar");
assert(foobar, "missing host foobar");
assert(
  foobar.y >= aMleaf.y + aMleaf.h,
  "foobar must sit in host band below A-mleaf1",
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

// Leaf-single and mleaf-rail hosts under the same pair must not overlap.
{
  const hosts = lay.nodes.filter((n) => n.role === "host");
  const overlaps = (a: (typeof hosts)[0], b: (typeof hosts)[0]) =>
    a.x < b.x + b.w &&
    a.x + a.w > b.x &&
    a.y < b.y + b.h &&
    a.y + a.h > b.y;
  for (let i = 0; i < hosts.length; i += 1) {
    for (let j = i + 1; j < hosts.length; j += 1) {
      assert(
        !overlaps(hosts[i], hosts[j]),
        `host boxes overlap: ${hosts[i].name} vs ${hosts[j].name}`,
      );
    }
  }
}

// Live campus fixture: leaf-single + mleaf-rail in host band, no overlap.
for (const campusPath of ["/tmp/campus-live.yml", "/tmp/campus-2026-11-23-2.yml"]) {
  let campusYaml: string;
  try {
    campusYaml = readFileSync(campusPath, "utf8");
  } catch {
    continue;
  }
  if (!campusYaml.includes("boo:")) continue;
  const campusGraph = parseTopologyGraph(campusYaml);
  assert(campusGraph, `parse failed for ${campusPath}`);
  const campus = layoutCvDiagram(campusGraph);
  const boo = campus.nodes.find((n) => n.name === "boo");
  const fooH = campus.nodes.find((n) => n.name === "foo");
  const cLeaf = campus.nodes.find((n) => n.name.endsWith("leaf1"));
  const cMleaf = campus.nodes.find((n) => n.name.includes("mleaf1"));
  assert(boo && fooH && cLeaf && cMleaf, "campus boo/foo/leaf/mleaf missing");
  assert(
    boo.y >= cMleaf.y + cMleaf.h && fooH.y >= cMleaf.y + cMleaf.h,
    "campus hosts must sit in host band below mleaf",
  );
  const overlap =
    boo.x < fooH.x + fooH.w &&
    boo.x + boo.w > fooH.x &&
    boo.y < fooH.y + fooH.h &&
    boo.y + boo.h > fooH.y;
  assert(!overlap, "boo (leaf1) overlaps foo (mleaf1 rail)");
  break;
}

// Spine hosts: host-band under spine X, bottom ports, outer-corridor path.
{
  const spineYaml = `
veos:
  version: 4.37.0F
nodes:
  - t-spine1:
      node_type: veos
  - t-spine2:
      node_type: veos
  - t-leaf1:
      node_type: veos
  - t-leaf2:
      node_type: veos
  - h1:
      node_type: generic
  - h2:
      node_type: generic
links:
  - connection: [t-spine1:Ethernet1, t-leaf1:Ethernet1]
  - connection: [t-spine1:Ethernet2, t-leaf2:Ethernet1]
  - connection: [t-spine2:Ethernet1, t-leaf1:Ethernet2]
  - connection: [t-spine2:Ethernet2, t-leaf2:Ethernet2]
  - connection: [t-spine1:Ethernet9, t-spine2:Ethernet9]
  - connection: [h1:Ethernet1, t-spine1:Ethernet10]
  - connection: [h2:Ethernet1, t-spine2:Ethernet10]
`;
  const spineGraph = parseTopologyGraph(spineYaml);
  assert(spineGraph, "spine fixture parse failed");
  const spineLay = layoutCvDiagram(spineGraph);
  const s1 = spineLay.nodes.find((n) => n.name === "t-spine1");
  const s2 = spineLay.nodes.find((n) => n.name === "t-spine2");
  const l1 = spineLay.nodes.find((n) => n.name === "t-leaf1");
  const h1 = spineLay.nodes.find((n) => n.name === "h1");
  const h2 = spineLay.nodes.find((n) => n.name === "h2");
  assert(s1 && s2 && l1 && h1 && h2, "spine fixture nodes missing");
  assert(s1.w === 160 && s2.w === 160, "spines should be wide");
  const spinePeerGap = s2.x - (s1.x + s1.w);
  assert(
    spinePeerGap === 140,
    `expected SPINE_PEER_GAP 140, got ${spinePeerGap}`,
  );
  assert(
    h1.y >= l1.y + l1.h && h2.y >= l1.y + l1.h,
    "spine hosts must sit in host band below leaves",
  );
  const spineMid = (s1.x + s2.x + s2.w) / 2;
  // Both spine singles share the pair centerline column (stacked).
  assert(
    Math.abs(h1.x + h1.w / 2 - spineMid) < 1,
    `h1 should sit on spine-pair centerline (${h1.x + h1.w / 2} vs ${spineMid})`,
  );
  assert(
    Math.abs(h2.x + h2.w / 2 - spineMid) < 1,
    `h2 should sit on spine-pair centerline (${h2.x + h2.w / 2} vs ${spineMid})`,
  );
  assert(h2.y > h1.y, "spine hosts should stack on the center column");
  const s1Host = s1.ports.find((p) => p.kind === "host");
  assert(s1Host?.side === "bottom", "spine1 host port on bottom");
  assert((s1Host?.w ?? 22) <= 16, "spine host port should be compact");
  assert(
    s1.ports.filter((p) => p.kind === "peer").every((p) => p.side === "right"),
    "spine1 peers must stay on inner right face",
  );
  const h1Link = spineLay.links.find(
    (l) => l.aName === "h1" || l.bName === "h1",
  );
  assert(h1Link, "missing h1 spine link");
  // Center corridor: vertical run near spine mid, no leaf-box crossings.
  const verticalXs = [];
  for (let i = 1; i < h1Link.points.length; i += 1) {
    const a = h1Link.points[i - 1];
    const b = h1Link.points[i];
    if (Math.abs(a.x - b.x) <= 1 && b.y > a.y) verticalXs.push(a.x);
  }
  assert(verticalXs.length >= 1, "h1 spine link missing vertical drop");
  assert(
    verticalXs.every((x) => Math.abs(x - spineMid) < 160),
    `h1 vertical should stay near spine mid (got ${verticalXs.join(",")})`,
  );
  for (const leaf of spineLay.nodes.filter((n) => n.role === "leaf")) {
    for (let i = 1; i < h1Link.points.length; i += 1) {
      const a = h1Link.points[i - 1];
      const b = h1Link.points[i];
      for (const t of [0.25, 0.5, 0.75]) {
        const x = a.x + (b.x - a.x) * t;
        const y = a.y + (b.y - a.y) * t;
        const inside =
          x >= leaf.x &&
          x <= leaf.x + leaf.w &&
          y >= leaf.y &&
          y <= leaf.y + leaf.h;
        assert(!inside, `h1 spine link crosses ${leaf.name}`);
      }
    }
  }
}

// Multi-host packing under one pair: leaf singles + mleaf rails + duals.
{
  const packYaml = `
veos:
  version: 4.37.0F
nodes:
  - p-spine1:
      node_type: veos
  - p-leaf1:
      node_type: veos
  - p-leaf2:
      node_type: veos
  - p-mleaf1:
      node_type: veos
  - dual1:
      node_type: generic
  - dual2:
      node_type: generic
  - l1a:
      node_type: generic
  - l1b:
      node_type: generic
  - ml:
      node_type: generic
  - mr:
      node_type: generic
links:
  - connection: [p-spine1:Ethernet1, p-leaf1:Ethernet1]
  - connection: [p-spine1:Ethernet2, p-leaf2:Ethernet1]
  - connection: [p-leaf1:Ethernet3, p-leaf2:Ethernet3]
  - connection: [p-mleaf1:Ethernet1, p-leaf1:Ethernet5]
  - connection: [p-mleaf1:Ethernet2, p-leaf2:Ethernet5]
  - connection: [dual1:Ethernet1, p-leaf1:Ethernet9]
  - connection: [dual1:Ethernet2, p-leaf2:Ethernet9]
  - connection: [dual2:Ethernet1, p-leaf1:Ethernet10]
  - connection: [dual2:Ethernet2, p-leaf2:Ethernet10]
  - connection: [l1a:Ethernet1, p-leaf1:Ethernet7]
  - connection: [l1b:Ethernet1, p-leaf1:Ethernet8]
  - connection: [ml:Ethernet1, p-mleaf1:Ethernet7]
  - connection: [mr:Ethernet1, p-mleaf1:Ethernet8]
`;
  const packGraph = parseTopologyGraph(packYaml);
  assert(packGraph, "pack fixture parse failed");
  const pack = layoutCvDiagram(packGraph);
  const hosts = ["dual1", "dual2", "l1a", "l1b", "ml", "mr"].map((name) => {
    const n = pack.nodes.find((x) => x.name === name);
    assert(n, `missing pack host ${name}`);
    return n;
  });
  const mleaf = pack.nodes.find((n) => n.name === "p-mleaf1");
  assert(mleaf, "missing p-mleaf1");
  for (const h of hosts) {
    assert(
      h.y >= mleaf.y + mleaf.h,
      `${h.name} must sit below mleaf in host band`,
    );
  }
  // Leaf1 singles stack in one column (same x).
  assert(
    Math.abs(hosts[2].x - hosts[3].x) < 1,
    "l1a/l1b should share a column",
  );
  assert(hosts[3].y > hosts[2].y, "l1b should stack below l1a");
  // Duals stack on centerline column.
  assert(
    Math.abs(hosts[0].x - hosts[1].x) < 1,
    "dual1/dual2 should share a column",
  );
  assert(hosts[1].y > hosts[0].y, "dual2 should stack below dual1");
  // Distinct columns: leaf1 | mleaf-L | dual | mleaf-R (leaf2 empty).
  const mids = [hosts[2], hosts[4], hosts[0], hosts[5]].map(
    (h) => h.x + h.w / 2,
  );
  for (let i = 1; i < mids.length; i += 1) {
    assert(
      mids[i] > mids[i - 1] + 8,
      `pack columns not left→right ordered (${mids.join(",")})`,
    );
  }
}

console.log("cvLayout smoke ok", {
  nodes: lay.nodes.length,
  links: lay.links.length,
  bundles: lay.bundles.length,
  mlag: mlag.length,
});

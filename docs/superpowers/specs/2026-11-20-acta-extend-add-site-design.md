# Extend `--add site` + named sites + backbone redundancy

**Date:** 2026-11-20  
**Status:** approved for planning (not implemented)  
**Branch intent:** `feat/extend-add-site` (implementation follows a separate plan)

## Summary

Operators can grow multi-site labs after create via
`acta act extend TOPOLOGY --add site`. That includes promoting a single-site
topology to multi-DC (new dated file only), naming sites with airport-style
labels (not only A–D), wiring new sites to the shared backbone hub in a
fabric-mode-aware way, and choosing backbone/border redundancy
(`mlag-peer` default vs `evpn-aa`).

Clos / mesh WAN beyond the dual (or N-node) hub is explicitly out of scope for
implementation in this cycle; the data model leaves a seam for it.

## Goals

- Add a site to an existing multi-DC lab without destroying prior site wiring.
- Promote single-site → multi-DC without in-place mutation of the input file.
- Named sites (alphanumeric) with safe hostname length rules.
- Backbone attach: L3LS borders↔bb; L2/L2LS spines↔bb.
- Redundancy: default classic MLAG peer links; optional EVPN AA multi-homing
  sets (≥2 nodes, no peer link in the topology).
- Honest RAM guidance (baseline → EVPN range) so labs stay runnable.
- Clear ACT vs clab next-step messaging (fresh deploy / re-onboard).

## Non-goals (this cycle)

- Implementing Clos / per-site WAN mesh (`backbone_mode=clos` etc.).
- EVPN AA for leaf MLAG pairs (borders + bb only here).
- In-place rewrite of a running ACT or clab lab.
- Enabling GitHub Issues via API (repo currently has issues disabled; track
  follow-ups once Settings → Features → Issues is on).

## Decisions (locked)

| Topic | Choice |
| --- | --- |
| Scope shape | Near-term site-add + backbone sketch; Clos later |
| Promote single-site | Yes, always write a **new dated** topology |
| Site sizing | Interactive prompts + optional flags (lean defaults) |
| Site names | Charset `[A-Za-z0-9][A-Za-z0-9_-]*`; soft-cap **32**; full hostname **≤64** |
| Max sites | **8**; fail when bb/border ports exhausted |
| CLI | `act extend --add site` (same surface as other extend ops) |
| Module | Dedicated `acta/site_extend.py` (or `acta/sites.py`); extend CLI wires it |
| CVP identity on promote | Keep `serial_number` / `system_mac_address` by default; `--rekey-identity` to rewrite |
| Bb/border redundancy | Default `mlag-peer`; optional `evpn-aa` (N≥2, no peer links) |
| RAM UX | Print baseline→EVPN range; confirm if projected cEOS >~24 (or `--force`) |

## Architecture

```text
acta act extend --add site
        │
        ▼
┌───────────────────┐
│  site_extend.py   │
│ ensure_multi_dc() │  single-site → named first site + bb hub (or no-op)
│ add_site()        │  append site + mode-aware bb attach
└─────────┬─────────┘
          │ new dated *.yml
          ▼
   stdout: path, RAM range, ACT/clab next steps
```

Shared dependencies: `PortPlan`, capacity header, `node_block` / link emitters
from create (refactored for reuse as needed), existing extend validation
patterns.

### `ensure_multi_dc(text) → text`

- If backbone already present → return text unchanged (aside from any normalize
  needed for named-site parsing).
- If single-site → rewrite fabric node keys/links to
  `{prefix}-{first_site}-{role}{n}`, inject `bb1`… per redundancy mode, add
  mode-correct site↔bb links and (if `mlag-peer`) bb peer + border MLAG peers.
- Never writes the input path; caller always persists a new file.

### `add_site(text, site_name, fabric_spec, …) → text`

- Reject duplicate site name, count >8, or insufficient bb/border ports.
- Emit lean site fabric (prompts/flags); wire to existing bb set.
- New nodes get new serials/MACs; promoted nodes keep old ones unless
  `--rekey-identity`.

## Naming & identity

- Hostname pattern: `{prefix}-{site}-{role}{n}`; backbone `{prefix}-bb{n}`.
- Legacy letter sites `A`–`D` remain valid site tokens.
- Soft-cap site token length 32 for readability; hard-fail if assembled
  hostname length >64.
- **CVP:** identity is serial (then system MAC, then hostname). Preserving
  serial/MAC on promote keeps inventory continuity when the same serials come
  back after a fresh ACT deploy. `--rekey-identity` is an intentional clean
  break (expect new CVP devices; decommission old rows).
- **ACT reality:** upload + deploy is a new lab → re-onboard either way;
  messaging must say so. Serial preservation still reduces CVP ghost clutter.

## CLI & UX

```text
acta act extend TOPOLOGY.yml --add site
acta act extend TOPOLOGY.yml --add site --name dfw --spines 2 --leaves 2 \
  [--bb-redundancy mlag-peer|evpn-aa] [--bb-count N] \
  [--border-redundancy mlag-peer|evpn-aa] [--border-count N] \
  [--rekey-identity] [--force]
```

- Missing flags → interactive prompts; lean defaults (2 spines / 2 leaves).
- New site name uses `--name` (do not overload existing `--site`, which scopes
  leaf/spine/mleaf extend on an existing site).
- Promote prompts for **existing** site name and **new** site name.
- Always emit a new dated topology; leave input untouched.
- After write, print:
  1. Output path
  2. Projected cEOS count + baseline→EVPN RAM range
  3. Next steps: ACT `act upload` (new lab / re-onboard); clab
     `generate` / `redeploy` from the new file (no in-place rename of running
     containers)
  4. Promote warning about hostname renames / identity flags

### Create alignment

`act create` site collection moves from “number of letters A–D” to named sites
(still max 8) so new labs match extend. Default redundancy remains `mlag-peer`.

## Backbone & redundancy

### Attach

| Fabric mode | Site edge toward bb |
| --- | --- |
| `l3ls` | Border leaves |
| `l2ls` / `l2` | Spines |

### Modes

| Mode | Set size | Peer link in YAML |
| --- | --- | --- |
| `mlag-peer` (default) | 2 | Yes (bb peer; border MLAG peer on L3LS) |
| `evpn-aa` | N≥2 (default 2) | No peer links inside the AA set |

Users on `mlag-peer` may still shut peer links later and configure ESI/AA MH in
EOS/CVP without re-emitting the topology; `evpn-aa` exists when the wire model
should match that practice from the start.

Leaf MLAG pairs stay as today (AA for leaf pairs = later issue).

### Port plan

- Site ordinal = sorted site-name order (stable), not fixed A=0…D=3.
- Reserve ports for max 8 sites and chosen bb/border set sizes so later adds do
  not renumber existing endpoints.
- Fail clearly when Ethernet16 cannot fit another site or a larger AA set.
- Capacity header records `bb_redundancy`, `border_redundancy`, set sizes, and
  an implied `backbone_mode=hub` seam for future Clos work.

## RAM guidance

Live measurement on `blz2` (`ceos:4.37.0F`, quiet lab):

- ~**1.53 GiB** RSS per cEOS; hosts ~negligible; ~15% VM overhead above sum.
- Rule of thumb (baseline): machine GiB ≈ **1.8 × cEOS count**.
- Full L2LS/EVPN will raise RSS; UX shows a **range** (baseline → +50–75%), not
  a single number.
- Comfortable configured scale on 64 GiB VM ≈ **20–24 cEOS**; 64 all-cEOS nodes
  is not realistic once EVPN is configured.

Site-add defaults stay lean. Confirm (or `--force`) when projected cEOS >~24.

## Error handling

**Hard-fail:** invalid site name; hostname >64; site soft-cap violated; >8
sites; port exhaustion; `evpn-aa` with N<2; missing/corrupt capacity header.

**Warn / confirm:** RAM thresholds; promote rename + ACT/clab next steps;
`--rekey-identity` implications for CVP.

## Testing (representative)

- Promote single→multi: naming, links, serial/MAC preserved vs `--rekey-identity`.
- Add site on multi-DC: L3LS borders↔bb; L2 spines↔bb.
- `evpn-aa`: no peer links; set size 3.
- Caps: 8th site OK; 9th fails; port-exhaustion message.
- CLI flags + interactive defaults; always new dated output.
- Create named-site prompt alignment (smoke).

## Follow-ups (tracked in-repo; GH Issues currently disabled)

See [`docs/backlog/`](../../backlog/README.md) until the repo owner enables
GitHub Issues:

1. **Clos / mesh WAN backbone** — `docs/backlog/002-clos-wan-backbone.md`
2. **Leaf-pair EVPN AA** — `docs/backlog/003-leaf-pair-evpn-aa.md`
3. Optional **live RAM probe** — `docs/backlog/004-live-ram-probe.md`

Related (mgmt discovery, deferred earlier):
`docs/backlog/001-probe-mgmt-network.md`.

## Implementation note

Do not start coding until an implementation plan exists
(`docs/superpowers/plans/…`) derived from this spec.

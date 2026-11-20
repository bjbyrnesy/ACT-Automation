# ACTA Python CLI — Design Spec

**Date:** 2026-11-19  
**Branch:** `feature/topology-spare-width-extend`  
**Status:** Draft for review

## Goal

Replace the bash entrypoints (`generate.sh`, `act_topology.sh`, `onboard.sh`, `_common.sh`) and the standalone `clab.py` with one user-facing Python CLI: `acta.py`.

Ship two coupled fabric features in the same effort:

1. **Spare width at create time** — reserve spine/leaf/member-leaf port budgets so growth does not renumber existing links.
2. **Extend** — grow an existing ACT topology by wiring new switches onto unused ports only (IRL-like). Existing `node:EthernetN` endpoints on prior connections never change.

No shell shims. Delete `.sh` files and top-level `clab.py` only after parity, tests, and README cutover.

**Out of scope (this branch):** port shuffle / renorm / CVP-accept flows for moving existing endpoints. Reason about them as a future mode; do not build them now.

## User-facing CLI

### Top-level help (shape)

```text
usage: acta.py [-h] <command> ...

ACT Automation — create, extend, upload, and onboard fabric labs
(ACT + containerlab). Capacity reserved at create time; extend only
uses unused ports (existing endpoints stay fixed).

options:
  -h, --help  show this help message and exit

commands:
  create          Interactive ACT topology create (pinned serials/MACs,
                  spare spine/leaf/mleaf capacity)
  extend          Grow an existing topology on unused ports
  upload          Upload topology YAML to ACT; optional lab create/deploy
  onboard         Onboard a Running ACT lab to CVaaS (TerminAttr over SSH)
  clab            Containerlab: generate, deploy, onboard cEOS labs

Use "acta.py <command> -h" for command help.
```

### `extend` help (shape)

```text
usage: acta.py extend [-h] [--add {spine,leaf,pair,mleaf}]
                      [--site SITE] [--pair N] [--count N]
                      [--out PATH | --new] topology

Grow an existing generate/create topology using unused ports only.
Existing node:Ethernet endpoints never change. Prefers planned
capacity; may grow past soft max with a warning up to 16 ports per
switch. L2 fabrics hard-cap at 2 spines.

positional arguments:
  topology              ACT topology YAML (default: overwrite in place)

options:
  -h, --help            show this help message and exit
  --add {spine,leaf,pair,mleaf}
                        What to add (prompt if omitted)
  --site SITE           Site letter when DC_COUNT > 1 (else prompt)
  --pair N              Leaf pair index for --add mleaf (required then)
  --count N             How many leaves/mleafs to add (default: 1)
  --out PATH            Write result to PATH; leave input unchanged
  --new                 Write a new dated topology-*.yml beside input
```

### `clab` nesting

```text
usage: acta.py clab [-h] {generate,deploy,onboard} ...
```

Behavior matches today’s `clab.py` subcommands after the move.

### Extend semantics (where devices attach)

| Add | Attachment rule |
|-----|-----------------|
| `leaf` | Next leaf index; full-mesh uplinks to every **current** spine (no per-spine flag). |
| `pair` | Next two leaves as an MLAG pair; mesh both to all current spines; add peer links. |
| `mleaf` | Requires `--pair N` (or prompt). Dual-home under that leaf pair on next free downlinks. |
| `spine` | Next spine index; mesh to every **current** leaf. |

Multi-site: if `DC_COUNT > 1`, prompt for site unless `--site` is set.

Output: overwrite the given path by default; `--out PATH` or `--new` writes a copy. Refuse `--out` if the target file already exists. `--new` chooses a unique dated `topology-*.yml` name (do not clobber).

## Capacity model

### Create prompts

Keep today’s size questions (spines, leaves, MLAG, member leaves, fabric mode, EOS version, etc.). After current size, also ask:

- **max_spines** — planned spine layer width. L3LS: default and planned ceiling **4** (demo: add 3rd/4th spine). L2: spines **hard-capped at 2** (design rule; do not offer growth past 2).
- **max_leaves** — planned spine↔leaf port budget; must be ≥ current leaf count.
- **max_mleafs_per_pair** — planned member-leaf downlinks per pair; must be ≥ current.

Show a concise banner explaining **why** (growth on free ports without renumbering) and **how** (`acta.py extend …` examples).

### Soft max vs hard cap

- Planned `max_*` values define the **reserved contiguous** port layout so MLAG / mleaf / border / backbone service ports sit after the reserved spine/leaf blocks and do not slide when extending inside the plan.
- Only active devices get links; reserved ports stay unused (no dummy links).
- Extending **inside** planned capacity: prefer free ports in the reserved block (no warning).
- Extending **past** planned soft max: allowed (virtual devices). Emit a clear warning; allocate the next free Ethernet on each involved switch by scanning ports 1–16 and skipping any Ethernet already used in a link on that node. New links may be non-contiguous relative to the original plan. Do not renorm existing endpoints.
- **Hard stop:** **16 ports per any one switch**. Fail if an extend would require Ethernet17+. Stay well below typical cEOS-lab interface limits.

L2 spine count remains a crisp design limit of 2 (not a soft max).

### Capacity header (in topology YAML comments)

Machine- and human-readable header, for example:

```text
# capacity: fabric_mode=l3ls max_spines=4 max_leaves=8 max_mleafs_per_pair=2
# capacity: spines=2 leaves=4
```

`extend` requires a parseable capacity header. Missing or invalid → hard fail with guidance to recreate via `acta.py create` (no guessing).

## Create / extend data flow

### Create

1. Load `.config` → interactive prompts (size + capacity + fabric mode).
2. Build `FabricSpec` (counts, max_*, MLAG, sites, EOS, serial/MAC seeds).
3. `PortPlan.from_spec(spec)` → fixed reserved offsets.
4. Emit ACT YAML (capacity header + nodes + active links only) + optional PNG via graphviz.
5. Save config cache. Print next steps (`upload`, `extend -h`).

### Extend

1. Parse topology YAML + `# capacity:` header.
2. Resolve site (`--site` or prompt if multi-DC).
3. Resolve `--add` (or prompt).
4. Validate against PortPlan + live inventory (next index, free ports, L2/L3LS rules, hard 16).
5. Append new nodes and new links only; update current counts in the header; keep `max_*` unless product later defines a bump flag (v1: leave max_* as authored at create; soft-overrun uses next-free ≤16).
6. Write in place or `--out` / `--new`; refresh PNG if graphviz is present.
7. Print what was added and remaining free slots (planned + until hard 16).

### Failures (no partial write)

- No / invalid capacity header.
- L2 `--add spine` when spines already 2.
- `--add mleaf` without usable `--pair` / pair missing / no free downlink and hard 16 reached.
- Multi-DC with no site chosen.
- `--count` would exceed hard 16 mid-batch.
- `--out` path already exists.

### Success criteria (fabric)

- Diff of links after extend: **only additions**; zero changed endpoints on pre-existing connections.
- Tests cover PortPlan offsets, each add type, L2/L3LS spine rules, soft-max warn path, hard-16 fail.

## Package layout

```text
acta.py                 # user entry (argparse → subcommands)
acta/
  __init__.py
  cli.py                # parsers / help text
  config.py             # .config load/save (from _common.sh)
  prompt.py             # interactive prompts
  capacity.py           # header parse/emit + soft max + hard 16
  portplan.py           # reserved offsets + next-free allocator
  topology.py           # parse/emit ACT YAML model
  create.py             # former generate.sh
  extend.py             # new
  act_api.py            # login/poll/upload/lab
  upload.py             # former act_topology.sh
  onboard_act.py        # former onboard.sh
  diagram.py            # graphviz PNG
  clab/                 # former clab.py
    generate.py
    deploy.py
    onboard.py
    layout.py
tests/
pyproject.toml
uv.lock
```

Shared helpers: config, prompts, ACT API client, capacity/port planner used by create and extend.

## Tooling

- **Python:** latest stable CPython **3.15** (`requires-python >=3.15`).
- **uv:** owns virtualenv and dependencies (`uv sync`, `uv run acta.py …`, `uv run pytest`).
- **Format/lint:** black + ruff; type hints on new code.
- **YAML:** PyYAML.
- **HTTP:** httpx for ACT API (replace curl/jq-centric upload/onboard paths).
- **Diagrams:** optional host `graphviz` binary (unchanged expectation).

## Migration order

Same branch; delete shells only at the end.

1. Skeleton `acta.py` + config/prompt + PortPlan/capacity tests + uv/pyproject.
2. `create` parity with `generate.sh` + capacity header + why/how banner.
3. `extend` + endpoint-freeze / soft-max / hard-16 tests.
4. `upload` + ACT `onboard` parity.
5. Move `clab.py` under `acta clab` (behavior unchanged).
6. README cutover to `uv run acta.py …` only.
7. Remove `generate.sh`, `onboard.sh`, `act_topology.sh`, `_common.sh`, top-level `clab.py`. No shims.

Prefer demoable create/extend (steps 1–3) before ACT/clab moves if sequencing for review, but the branch goal includes the full cutover.

## Testing

- pytest via `uv run pytest`.
- PortPlan: reserved offsets; next-free; soft-max warning path; hard fail at Eth17.
- Extend: spine / leaf / pair / mleaf; L2 spine cap 2; multi-site `--site` / prompt.
- Endpoint freeze: pre-existing connections unchanged after extend.
- Create header round-trip; extend without header fails.
- Adapt existing `tests/test_clab.py` to `acta clab`.
- No real network in unit tests; mock ACT HTTP.

**Done when:**

- `uv run acta.py --help` matches the agreed shape.
- Create + extend work without `.sh`.
- Upload / onboard / clab parity verified; README points only at `acta.py`.
- Shells and top-level `clab.py` removed.
- `uv run ruff`, `uv run black --check`, `uv run pytest` green.

## Future (not this branch)

- Explicit renorm / shuffle mode that changes existing endpoints, with loud user acceptance for CVP/topology drift.
- Raising planned `max_*` in-place without recreate (optional bump flag).
- Confirm exact cEOS-lab interface ceiling empirically; keep hard cap at 16 unless evidence supports a documented higher safe default.

## Decisions log

| Topic | Decision |
|-------|----------|
| Endpoint stability | Preserve existing link endpoints on extend (IRL unused ports). |
| Spare width UX | Current size + max_leaves + max_mleafs_per_pair + max_spines. |
| Spine growth | L3LS planned up to 4; L2 hard max 2 spines. |
| Past soft max | Allowed with warning; next free port ≤16. |
| Hard port cap | 16 Ethernet ports per switch. |
| CLI surface | `extend` as first-class command with flags; interactive when flags omitted. |
| Multi-site | Prompt if DC>1; `--site` skips prompt. |
| Capacity persistence | YAML `# capacity:` header comments. |
| Output | Overwrite default; `--out` / `--new` for copies. |
| Implementation | Full Python refactor; one `acta.py`; delete `.sh` after parity. |
| Tooling | Python 3.15 + uv + black/ruff/pytest. |

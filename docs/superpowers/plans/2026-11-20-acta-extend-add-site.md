# Extend `--add site` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `acta act extend --add site` (promote single-site → multi-DC,
add named sites, mode-aware backbone attach, `mlag-peer` / `evpn-aa` redundancy)
per the approved spec, with clear ACT/clab next-step and RAM-range messaging.

**Architecture:** New module `acta/site_extend.py` owns `ensure_multi_dc` and
`add_site`. CLI wires `--add site` through existing extend entrypoints. Reuse
`PortPlan`, capacity header, and create emitters (refactor shared helpers out of
`create.py` only as needed). Always write a **new dated** topology file.

**Tech Stack:** Python ≥3.15, uv, PyYAML, pytest, black, ruff.

**Spec:** `docs/superpowers/specs/2026-11-20-acta-extend-add-site-design.md`

## Global constraints

- Existing link endpoints never move except intentional promote renames of
  **node names** (serial/MAC preserved unless `--rekey-identity`).
- Max **8** sites; site soft-cap **32** chars; full hostname **≤64**.
- Default redundancy **`mlag-peer`**; optional **`evpn-aa`** (N≥2, no peer links).
- L3LS: borders↔bb; L2/L2LS: spines↔bb.
- Lean defaults (2 spines / 2 leaves); RAM range baseline→EVPN; confirm >~24 cEOS.
- Format black; lint ruff; secrets never in code.
- Work on branch `feat/extend-add-site` from current `main`.

## File map

| File | Responsibility |
|------|----------------|
| `acta/site_extend.py` | `ensure_multi_dc`, `add_site`, naming validators, RAM message helpers |
| `acta/site_names.py` (optional split) | Site token / hostname length validation |
| `acta/portplan.py` | Extend for named-site ordinals + AA set sizes + max 8 |
| `acta/capacity.py` | Persist `bb_redundancy`, `border_redundancy`, set sizes, `backbone_mode=hub` |
| `acta/create.py` | Named sites at create (max 8); share emitters with site_extend |
| `acta/extend.py` | Dispatch `add=="site"` to site_extend; keep leaf/spine/mleaf |
| `acta/cli.py` | Flags: `--name`, redundancy, counts, `--rekey-identity`, `--force` |
| `tests/test_site_extend.py` | Promote, add site, AA, caps, identity |
| `tests/test_extend.py` | Ensure existing extend still green |
| `README.md` | Document `--add site` + clab/ACT next steps |

---

### Task 1: Site naming validators + capacity header fields

**Files:**
- Create: `acta/site_names.py` (or functions at top of `site_extend.py` if tiny)
- Modify: `acta/capacity.py`
- Create: `tests/test_site_names.py`

- [ ] **Step 1: Failing tests** for charset, soft-cap 32, hostname ≤64, legacy A–D OK.
- [ ] **Step 2: Implement validators.**
- [ ] **Step 3: Extend capacity parse/emit** for `bb_redundancy`, `border_redundancy`,
      `bb_count`, `border_count`, `backbone_mode` (default `hub` / `mlag-peer` / 2).
- [ ] **Step 4: `uv run pytest tests/test_site_names.py tests/test_capacity.py -q`**

---

### Task 2: PortPlan for named sites + AA sets

**Files:**
- Modify: `acta/portplan.py`
- Modify: `tests/test_portplan.py`

- [ ] **Step 1: Failing tests** — site ordinal by sorted name; bb ports for 8 sites;
      `evpn-aa` set size 3; peer port reserved so adds don’t renumber; exhaustion errors.
- [ ] **Step 2: Implement** without breaking single-letter A–D layouts (same formulas
      with ordinal index).
- [ ] **Step 3: `uv run pytest tests/test_portplan.py -q`**

---

### Task 3: `ensure_multi_dc` (promote)

**Files:**
- Create: `acta/site_extend.py`
- Create: `tests/test_site_extend.py`

- [ ] **Step 1: Failing test** — single-site topo → named first site + bb hub;
      links rewritten; serial/MAC preserved; `--rekey-identity` rewrites them;
      `mlag-peer` has peer link; `evpn-aa` does not.
- [ ] **Step 2: Implement `ensure_multi_dc(...)`** (pure text/YAML transform; no file I/O).
- [ ] **Step 3: Multi-DC input is no-op** (aside from parseability).
- [ ] **Step 4: `uv run pytest tests/test_site_extend.py -k promote -q`**

---

### Task 4: `add_site`

**Files:**
- Modify: `acta/site_extend.py`
- Modify: `tests/test_site_extend.py`

- [ ] **Step 1: Failing tests** — add site on multi-DC L3LS (borders↔bb) and L2
      (spines↔bb); lean fabric; 8th OK / 9th fails; duplicate name fails;
      port exhaustion message.
- [ ] **Step 2: Implement `add_site(...)`** reusing create node/link helpers.
- [ ] **Step 3: `uv run pytest tests/test_site_extend.py -q`**

---

### Task 5: CLI + always-new file + messaging

**Files:**
- Modify: `acta/cli.py`, `acta/extend.py`
- Modify: `tests/test_cli_help.py`, `tests/test_extend.py` as needed

- [ ] **Step 1: Extend `--add` choices with `site`**; add `--name`, redundancy flags,
      `--rekey-identity`, `--force`; interactive prompts when flags omitted.
- [ ] **Step 2: Wire handler** — read input → ensure_multi_dc → add_site → write
      **new dated** path (never overwrite input); print RAM range + ACT/clab next steps.
- [ ] **Step 3: Confirm prompt** when projected cEOS >24 unless `--force`.
- [ ] **Step 4: Help tests** list `--add site` and new flags.
- [ ] **Step 5: `uv run pytest tests/test_cli_help.py tests/test_extend.py tests/test_site_extend.py -q`**

---

### Task 6: Create alignment (named sites, max 8)

**Files:**
- Modify: `acta/create.py`
- Modify: `tests/test_create.py`

- [ ] **Step 1: Replace letter-only DC count** with named-site collection (max 8),
      default redundancy `mlag-peer`, optional AA prompts.
- [ ] **Step 2: Keep ACT/clab `--for` behavior**; ensure emitted YAML matches extend
      expectations (named sites, capacity fields).
- [ ] **Step 3: `uv run pytest tests/test_create.py -q`**

---

### Task 7: README + full suite + PR

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document** `extend --add site`, promote, redundancy, RAM messaging.
- [ ] **Step 2: `uv run black … && uv run ruff check … && uv run pytest -q`**
- [ ] **Step 3: Open PR** against `main` with test plan from the spec.

## Out of scope (track as issues when GH Issues enabled)

1. Clos / mesh WAN backbone
2. Leaf-pair EVPN AA
3. Live RAM probe from lab host

## Execution handoff

After this plan is reviewed, implement on `feat/extend-add-site` using
subagent-driven-development or executing-plans, one task at a time.

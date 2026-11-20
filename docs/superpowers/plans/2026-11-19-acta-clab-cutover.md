# ACTA Clab Move + Shell Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nest former `clab.py` under `acta.py clab`, rewrite README to `uv run acta.py …` only, then delete `generate.sh`, `act_topology.sh`, `onboard.sh`, `_common.sh`, and top-level `clab.py` with no shims.

**Architecture:** Move containerlab modules into `acta/clab/` package; CLI `clab generate|deploy|onboard` calls the same functions. Adapt `tests/test_clab.py` imports. Final commit removes shells and updates docs.

**Tech Stack:** Existing clab Python code + Plan 1/2 CLI.

**Depends on:** Plan 1 and Plan 2 complete (`create`, `extend`, `upload`, `onboard` usable).

**Spec:** `docs/superpowers/specs/2026-11-19-acta-python-cli-design.md`

## Global Constraints

- Same Global Constraints as design spec / Plan 1.
- Behavior of clab generate/deploy/onboard must stay test-equivalent.
- Delete shells only after README + tests green.
- No `.sh` shims.

## File map

| File | Responsibility |
|------|----------------|
| `acta/clab/*.py` | Former `clab.py` split by concern |
| `acta/cli.py` | Wire clab subcommands to real handlers |
| `tests/test_clab.py` | Import from `acta.clab` |
| `README.md` | Full cutover docs |
| Delete | `clab.py`, `generate.sh`, `act_topology.sh`, `onboard.sh`, `_common.sh` |

---

### Task 1: Move clab.py into acta.clab package

**Files:**
- Create: `acta/clab/__init__.py`
- Create: `acta/clab/generate.py`, `deploy.py`, `onboard.py`, `layout.py`, `support.py` (split along existing `clab.py` function groups; keep public function names used by tests)
- Modify: `tests/test_clab.py` imports
- Keep `clab.py` as thin re-export **only until Task 3** (temporary — delete in Task 3; do not document as supported)

**Interfaces:**
- Preserve: `generate(args)`, `deploy(args)`, `onboard(args)`, `topology_layout(...)`, etc.
- Tests currently `import clab` — change to `from acta import clab` or `import acta.clab as clab` with attribute parity.

- [ ] **Step 1: Write/adjust one failing import test if needed; otherwise move code and fix imports**
- [ ] **Step 2: `uv run pytest tests/test_clab.py -v` — PASS**
- [ ] **Step 3: Wire `acta.py clab generate|deploy|onboard` to same handlers**
- [ ] **Step 4: Commit `refactor(acta): move clab.py under acta.clab`**

---

### Task 2: README cutover

**Files:**
- Modify: `README.md`

Replace all `./generate.sh`, `./act_topology.sh`, `./onboard.sh`, `./clab.py` examples with:

```bash
uv sync --extra dev
uv run python acta.py create
uv run python acta.py extend topology-….yml --add leaf
uv run python acta.py upload topology-….yml
uv run python acta.py onboard
uv run python acta.py clab generate …
uv run python acta.py clab deploy …
uv run python acta.py clab onboard …
```

Document Python 3.15 + uv requirement. Document capacity prompts and extend rules (soft max, hard 16, L2 spines=2).

- [ ] **Step 1: Edit README**
- [ ] **Step 2: Grep README for `.sh` / `clab.py` — expect no user-facing old entrypoints**
- [ ] **Step 3: Commit `docs: cut README over to acta.py and uv`**

---

### Task 3: Delete shells and top-level clab.py

**Files:**
- Delete: `generate.sh`, `act_topology.sh`, `onboard.sh`, `_common.sh`, `clab.py`
- Modify: any remaining imports/docs/plans references only if needed
- Modify: `tests/` to ensure nothing imports deleted `clab.py`

- [ ] **Step 1: Remove temporary `clab.py` re-export if present**
- [ ] **Step 2: Delete shell scripts**
- [ ] **Step 3: `uv run ruff check acta tests && uv run black --check acta tests && uv run pytest -v`**
- [ ] **Step 4: Commit `chore: remove bash entrypoints and standalone clab.py`**

---

### Task 4: Final acceptance checklist

- [ ] `uv run python acta.py --help` matches design mockup commands
- [ ] `uv run python acta.py extend -h` shows add/site/pair/out/new
- [ ] Create → extend leaf → existing endpoints unchanged (manual or test)
- [ ] Upload/onboard/clab smoke on trogdor when credentials available (manual; not required for unit green)
- [ ] Commit any leftover fixups `test: finalize acta cutover acceptance`

---

## Self-review

- Spec cutover + clab nesting covered.
- Shell deletion gated on tests/README.
- Plan 1/2 features assumed present.

# ACTA Upload + ACT Onboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `act_topology.sh` and `onboard.sh` with `acta.py upload` and `acta.py onboard` using shared config and an httpx ACT API client.

**Architecture:** `acta/act_api.py` owns login, operation polling, topology upload, lab create/deploy, and listing running labs. `upload.py` and `onboard_act.py` implement CLI flows. Reuse `acta/config.py` and `acta/prompt.py` from Plan 1.

**Tech Stack:** Python ≥3.15, uv, httpx, PyYAML, pytest (httpx mocked).

**Depends on:** Plan 1 (`2026-11-19-acta-create-extend.md`) complete enough that `acta/config.py`, `acta/prompt.py`, and `acta/cli.py` exist.

**Spec:** `docs/superpowers/specs/2026-11-19-acta-python-cli-design.md`

## Global Constraints

- Same Global Constraints as Plan 1 / design spec.
- Do not delete `.sh` files in this plan.
- No real ACT calls in unit tests; mock httpx transport.
- Keep `.config` key names compatible with existing caches (`ACT_TENANT`, `ACT_API_KEY`, `CVAAS_TOKEN`, …).

## File map

| File | Responsibility |
|------|----------------|
| `acta/act_api.py` | ACT REST client |
| `acta/upload.py` | Upload topology + optional lab deploy |
| `acta/onboard_act.py` | List running labs; SSH TerminAttr onboard |
| `tests/test_act_api.py` | Client unit tests |
| `tests/test_upload.py` | Upload flow with mocks |
| `tests/test_onboard_act.py` | Lab pick + command build tests |

---

### Task 1: ACT API client (login + poll)

**Files:**
- Create: `acta/act_api.py`
- Create: `tests/test_act_api.py`

**Interfaces:**
- Consumes: httpx
- Produces:
  - `class ActClient`
  - `ActClient(base_url: str, api_key: str, transport: httpx.BaseTransport | None = None)`
  - `login() -> str` bearer token
  - `poll_operation(operation: dict, label: str, max_iterations: int = 60, interval: float = 10.0) -> dict`

Port behavior from `act_topology.sh` `act_login` / `act_poll`.

- [ ] **Step 1: Write failing test with httpx MockTransport**
- [ ] **Step 2: Run `uv run pytest tests/test_act_api.py -v` — expect FAIL**
- [ ] **Step 3: Implement login + poll**
- [ ] **Step 4: pytest PASS**
- [ ] **Step 5: Commit `feat(acta): add ACT API login and poll client`**

---

### Task 2: Upload topology + optional lab create/deploy

**Files:**
- Create: `acta/upload.py`
- Modify: `acta/cli.py` (wire `upload`)
- Create: `tests/test_upload.py`

**Interfaces:**
- `run_upload(topology: Path, *, deploy: bool | None = None, tenant: str | None = None) -> None`
- Convert YAML→JSON via PyYAML (no yq dependency).
- Attach PNG if sibling `.png` exists (best-effort; match `act_topology.sh` notes on failure).
- Prompt create/deploy when `deploy is None`.

Reference: `act_topology.sh` main upload path.

- [ ] **Step 1: Failing test — client receives topology JSON body**
- [ ] **Step 2: Implement upload flow**
- [ ] **Step 3: pytest PASS**
- [ ] **Step 4: Commit `feat(acta): upload topologies to ACT`**

---

### Task 3: ACT onboard (TerminAttr over SSH)

**Files:**
- Create: `acta/onboard_act.py`
- Modify: `acta/cli.py`
- Create: `tests/test_onboard_act.py`

**Interfaces:**
- `run_onboard_act(...)` — list running labs, pick one, resolve EOS password from topology `veos:` block (same rules as `onboard.sh`), SSH paste TerminAttr.
- Keep password resolution unit-tested without SSH.
- SSH execution behind a narrow `run_ssh(host, commands) -> None` injectable dependency for tests.

Reference: `onboard.sh` password resolution + onboarding snippet construction.

- [ ] **Step 1: Failing tests for password resolution + snippet**
- [ ] **Step 2: Implement onboard_act with injectable SSH**
- [ ] **Step 3: pytest PASS**
- [ ] **Step 4: Commit `feat(acta): onboard ACT labs to CVaaS`**

---

### Task 4: CLI help + config keys parity

**Files:**
- Modify: `acta/cli.py`, `acta/config.py`, `tests/test_cli_help.py`

- [ ] **Step 1: Extend help test — `upload`/`onboard` subhelp mention topology/lab**
- [ ] **Step 2: Ensure `save_config` still writes union of ACT + create + clab keys**
- [ ] **Step 3: `uv run ruff check acta tests && uv run black acta tests && uv run pytest -v`**
- [ ] **Step 4: Commit `feat(acta): wire upload and onboard CLI help`**

---

## Self-review

- Spec `upload` / `onboard` commands covered.
- Shell deletion not in this plan.
- No TBD steps; implementers read `act_topology.sh` / `onboard.sh` for endpoint paths and copy strings verbatim into Python.

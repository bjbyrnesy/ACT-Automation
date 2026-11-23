# ACTA local Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `acta serve` — a localhost FastAPI + React SPA ops console with
Graphviz preview, Create→Write, Labs/Show, Extend, Attach, Clab/ACT jobs, and
Settings, backed by in-process `acta` library calls (no CLI subprocess).

**Architecture:** Thin façade modules under `acta/web/` expose promptless
functions. FastAPI mounts `/api/*` and serves built SPA assets from
`acta/web/static/` (copied from `ui/dist` at build time). SPA shell: left nav,
top contextual controls, content = YAML + PNG. Clab host is local or remote via
existing config. Jobs are in-process background tasks with pollable status.

**Tech Stack:** Python ≥3.15, uv, FastAPI, uvicorn, httpx, PyYAML, React 18 +
Vite + TypeScript, Graphviz `dot`, pytest, black, ruff.

**Spec:** `docs/superpowers/specs/2026-11-21-acta-webui-design.md`

## Global constraints

- Bind **127.0.0.1** only by default; port **8765**; `--no-open` supported.
- In-process library calls only — **never** shell out to `acta` for preview/ops.
- No SSH UI; no interactive canvas in v1 (leave a code comment seam only).
- Draft Create stays in memory until Write; Deploy/Upload/Onboard/Destroy require
  a written Active topology path.
- Secrets in `.config` / env; masked on GET; never commit `.config` / `.env`.
- Format black; lint ruff; SPA: `npm run lint` / `npm run build` green.
- Work on branch `feat/acta-webui` from current `main` (merge docs PR first if needed).

## Open points resolved

| Item | Choice |
|------|--------|
| SPA | **React + Vite + TypeScript** |
| Static assets | Build `ui/` → copy into `acta/web/static/`; **do not** commit minified churn long-term; CI/build script produces static; `acta serve` serves package resources; if static missing in dev, print clear “run `npm run build` in ui/” |
| Jobs | **Poll** `GET /api/jobs/{id}` (no SSE in v1) |

## File map

| File / dir | Responsibility |
|------------|----------------|
| `acta/web/__init__.py` | Package marker |
| `acta/web/errors.py` | `WebError` / field errors → HTTP mapping helpers |
| `acta/web/preview.py` | `preview_from_spec`, `png_from_yaml` |
| `acta/web/labs.py` | List/read/write topologies under labs root |
| `acta/web/settings_api.py` | Load/patch settings; mask secrets |
| `acta/web/jobs.py` | In-memory job registry + runner |
| `acta/web/ops.py` | Extend/attach/clab/act wrappers taking paths + DTOs |
| `acta/web/app.py` | FastAPI app factory, routes, static mount |
| `acta/web/serve.py` | `run_serve(host, port, root, open_browser)` |
| `acta/web/static/` | Built SPA (generated) |
| `acta/cli.py` | Add `serve` / `ui` subcommand |
| `acta/create.py` | Ensure `FabricSpec` + `emit_act_yaml` remain the create engine (no stdin in façade path) |
| `ui/` | Vite React SPA source |
| `tests/test_web_preview.py` | Façade preview/png |
| `tests/test_web_labs.py` | Labs list/write |
| `tests/test_web_api.py` | FastAPI TestClient routes |
| `tests/test_web_jobs.py` | Job lifecycle |
| `tests/test_cli_help.py` | `serve` appears in help |
| `pyproject.toml` | `[project.optional-dependencies] ui`, hatch static include |
| `README.md` | `uv sync --extra ui` + `acta serve` |
| `scripts/build-ui.sh` | `npm ci && npm run build` + copy to `acta/web/static` |

---

### Task 1: Packaging extras + `WebError` + health stub

**Files:**
- Create: `acta/web/__init__.py`, `acta/web/errors.py`, `acta/web/app.py` (minimal)
- Create: `tests/test_web_api.py`
- Modify: `pyproject.toml`
- Create: `acta/web/static/.gitkeep` (placeholder until UI build)

**Interfaces:**
- Produces: `class WebError(Exception): status_code: int; detail: str; fields: dict[str, str] | None`
- Produces: `def create_app(*, labs_root: Path) -> FastAPI`
- Produces: optional-deps `ui = ["fastapi>=0.115", "uvicorn[standard]>=0.32"]`

- [ ] **Step 1: Add failing API health test**

```python
from pathlib import Path
from fastapi.testclient import TestClient
from acta.web.app import create_app

def test_health_ok(tmp_path: Path):
    client = TestClient(create_app(labs_root=tmp_path))
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "dot" in body
    assert body["bind_hint"] == "127.0.0.1"
```

- [ ] **Step 2: Run test — expect fail** (`create_app` missing)

Run: `uv sync --extra ui --extra dev && uv run pytest tests/test_web_api.py::test_health_ok -v`  
Expected: FAIL import / not found

- [ ] **Step 3: Implement `WebError`, `create_app` with `GET /api/health`**

Health payload:

```python
{
  "ok": True,
  "dot": shutil.which("dot") is not None,
  "labs_root": str(labs_root.resolve()),
  "bind_hint": "127.0.0.1",
}
```

Register exception handler: `WebError` → JSON `{"detail", "fields"}` with `status_code`.

- [ ] **Step 4: Update `pyproject.toml`** — optional-deps `ui`; ensure hatch packages `acta`.

- [ ] **Step 5: Re-run test — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml acta/web tests/test_web_api.py
git commit -m "feat(web): FastAPI app stub, WebError, and ui extra"
```

---

### Task 2: Preview façade (`FabricSpec` → YAML + PNG)

**Files:**
- Create: `acta/web/preview.py`
- Create: `tests/test_web_preview.py`
- Modify: `acta/web/app.py` — `POST /api/preview`
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `acta.create.FabricSpec`, `emit_act_yaml`, `acta.diagram.topology_to_dot`, `write_png`
- Produces:

```python
@dataclass(frozen=True)
class PreviewResult:
    yaml_text: str
    png_base64: str | None  # None if dot missing
    summary: dict[str, Any]  # node_count, fabric_mode, sites, title

def preview_from_spec(spec: FabricSpec) -> PreviewResult: ...
def png_bytes_from_yaml(yaml_text: str) -> bytes | None: ...
```

- [ ] **Step 1: Failing unit tests**

```python
from acta.capacity import Capacity
from acta.create import FabricSpec
from acta.web.preview import preview_from_spec

def test_preview_emits_yaml_and_optional_png():
    spec = FabricSpec(
        hostname_prefix="demo",
        serial_prefix="DEMO",
        eos_version="4.35.4M",
        capacity=Capacity("l3ls", 2, 4, 0, 1, 0),
        mlag_pairs=True,
        spine_mlag=False,
        member_leaf_pairs=[],
        member_leaves_per_pair=0,
    )
    result = preview_from_spec(spec)
    assert "demo-spine1" in result.yaml_text
    assert result.summary["node_count"] >= 1
    # png_base64 may be None in CI without graphviz — assert type only
    assert result.png_base64 is None or result.png_base64.startswith("iVBOR")
```

Invalid spec must raise `WebError` or `ValueError` that API maps to 422:

```python
def test_preview_rejects_bad_spine_mlag_on_l3ls():
    ...
```

- [ ] **Step 2: Implement `preview_from_spec` / `png_bytes_from_yaml`**
  - Call `_validate_spec` indirectly via `emit_act_yaml`
  - Write temp PNG via `write_png` or fail soft → `png_base64=None`
  - Summary: count `nodes:` keys; parse fabric mode from capacity header comment if present

- [ ] **Step 3: `POST /api/preview`** accepts JSON body matching FabricSpec fields
  (flat or nested `capacity`); returns PreviewResult as JSON.

- [ ] **Step 4: `uv run pytest tests/test_web_preview.py tests/test_web_api.py -q`**

- [ ] **Step 5: Commit** `feat(web): preview_from_spec and POST /api/preview`

---

### Task 3: Labs list / read / write dated topology

**Files:**
- Create: `acta/web/labs.py`
- Create: `tests/test_web_labs.py`
- Modify: `acta/web/app.py` — `GET/POST /api/topologies`, `GET /api/topologies/{name}`
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Produces:

```python
def list_topologies(root: Path) -> list[dict]:  # name, path, mtime, has_clab_sibling
def read_topology(root: Path, name: str) -> dict:  # yaml_text, png_base64?, path
def write_topology(root: Path, yaml_text: str, *, stem: str | None = None) -> Path:
    # dated filename like create CLI: {stem}-{YYYY-MM-DD}.yml or unique suffix
```

- [ ] **Step 1: Failing tests** — write under `tmp_path`, list finds file, read round-trips;
      reject path traversal (`../etc/passwd`).

- [ ] **Step 2: Implement labs helpers** — only `*.yml` / `*.yaml` that look like ACT
      topologies (contain `nodes:`); ignore `.clab.yml` in primary list (show as sibling flag).

- [ ] **Step 3: Wire routes**; Write from preview body `{yaml_text, stem?}`.

- [ ] **Step 4: pytest green**

- [ ] **Step 5: Commit** `feat(web): labs list/read/write under labs_root`

---

### Task 4: `acta serve` launcher

**Files:**
- Create: `acta/web/serve.py`
- Modify: `acta/cli.py` — top-level `serve` (and alias `ui`)
- Modify: `tests/test_cli_help.py`

**Interfaces:**
- Produces: `def run_serve(*, host: str = "127.0.0.1", port: int = 8765, labs_root: Path, open_browser: bool = True) -> None`
- CLI: `acta serve [--port 8765] [--root PATH] [--no-open] [--host 127.0.0.1]`
  - Reject host other than `127.0.0.1` / `localhost` unless `--allow-remote-bind` (not documented in README v1; or simply hard-refuse non-loopback)

- [ ] **Step 1: Failing help test** — `serve` in `acta --help` / subparser help.

- [ ] **Step 2: Implement `run_serve`**
  - `uvicorn.run(create_app(labs_root=...), host=host, port=port)`
  - If `open_browser`: `webbrowser.open(f"http://{host}:{port}/")` after short delay or uvicorn callback
  - Print one line: URL + Ctrl-C

- [ ] **Step 3: Wire CLI**; do not break existing commands.

- [ ] **Step 4: Manual smoke** — `uv run acta serve --no-open` then curl health (kill after).

- [ ] **Step 5: Commit** `feat(cli): acta serve launches local Web UI`

---

### Task 5: SPA shell (React + Vite) — layout chrome

**Files:**
- Create: `ui/package.json`, `ui/vite.config.ts`, `ui/tsconfig.json`, `ui/index.html`
- Create: `ui/src/main.tsx`, `ui/src/App.tsx`, `ui/src/layout/AppShell.tsx`
- Create: `ui/src/layout/LeftNav.tsx`, `ui/src/layout/TopBar.tsx`
- Create: `ui/src/pages/{Labs,Create,Show,Settings}Page.tsx` (stubs OK)
- Create: `scripts/build-ui.sh`
- Modify: `acta/web/app.py` — mount static + SPA fallback to `index.html`
- Modify: `README.md` — brief UI section

**Interfaces:**
- Vite proxy `/api` → `http://127.0.0.1:8765` in dev
- Production: assets under `acta/web/static/`; FastAPI `StaticFiles` + catch-all for client routes
- Left nav items: Labs, Create, Extend, Clab, ACT, Attach, Show, Settings
- Top bar: active topo label, clab host badge, slot for page actions

- [ ] **Step 1: Scaffold Vite React-TS in `ui/`** (`npm create vite@latest` pattern).

- [ ] **Step 2: Implement AppShell CSS layout** (CSS variables; no purple-gradient AI slop;
      match “ops console” denser than marketing). Vertical nav ~220px; top bar ~48px;
      content split YAML (monospace) + PNG.

- [ ] **Step 3: `scripts/build-ui.sh`** copies `ui/dist/*` → `acta/web/static/`.

- [ ] **Step 4: FastAPI serves `index.html` for `/` and unknown non-API paths.**

- [ ] **Step 5: `npm run build` + curl `/` returns HTML; `/api/health` still JSON.**

- [ ] **Step 6: Commit** `feat(web): React SPA shell with left nav and top bar`

---

### Task 6: Create page — form, Preview, Write

**Files:**
- Create: `ui/src/api/client.ts`, `ui/src/api/types.ts`
- Create: `ui/src/pages/CreatePage.tsx`, `ui/src/components/TopologyPane.tsx`
- Modify: `ui/src/state/activeTopology.ts` (React context or zustand — pick one; prefer
  lightweight context for v1)
- Modify: `tests/test_web_api.py` — preview + write integration

**Interfaces:**
- `POST /api/preview` body fields aligned with `FabricSpec` + nested capacity
- `POST /api/topologies` `{ yaml_text, stem }` → `{ path, name }`
- Active topology context: `{ path?, name?, yamlText, pngBase64?, isDraft }`

- [ ] **Step 1: API client** with typed `preview(spec)`, `writeTopology(...)`.

- [ ] **Step 2: Create form** — fabric mode, spines, leaves, pairs, max_*, sites
      (comma list), redundancy, prefixes, eos version, create_for act|clab|both.

- [ ] **Step 3: Preview button + optional debounce (400ms) when Settings flag true**
      (hardcode auto-preview default **off** until Settings task; manual always on).

- [ ] **Step 4: TopologyPane** shows YAML + `<img src={data:image/png;base64,...}>`
      or placeholder if no PNG.

- [ ] **Step 5: Write** calls API, sets Active topology, navigates to Show/Labs.

- [ ] **Step 6: pytest API + manual Create→Preview→Write smoke**

- [ ] **Step 7: Commit** `feat(web): Create form with Graphviz preview and Write`

---

### Task 7: Labs + Show pages

**Files:**
- Modify: `ui/src/pages/LabsPage.tsx`, `ShowPage.tsx`
- Modify: `acta/web/labs.py` / app if need `GET .../png` raw endpoint
- Optional: `GET /api/topologies/{name}/png` returns `image/png`

- [ ] **Step 1: Labs table** — name, mtime, open → set Active + load YAML/PNG.

- [ ] **Step 2: Show page** — summary from preview summary endpoint or client-side
      parse; PNG refresh button; **no** SSH reachability probes.

- [ ] **Step 3: Tests** for get-by-name 404; png route if added.

- [ ] **Step 4: Commit** `feat(web): Labs picker and Show pane for active topology`

---

### Task 8: Settings API (masked secrets) + Settings page

**Files:**
- Create: `acta/web/settings_api.py`
- Modify: `acta/web/app.py` — `GET/PATCH /api/settings`
- Modify: `ui/src/pages/SettingsPage.tsx`
- Create: `tests/test_web_settings.py`
- Uses: `acta.config.load_config` / `save_config` at `labs_root / ".config"`
  **or** project `.config` — match CLI: prefer same resolution as upload/clab
  (document: Settings writes project `.config` next to labs_root / cwd used by serve)

**Interfaces:**
- GET returns `{ CLAB_HOST, CLAB_IMAGE, ..., ACT_API_KEY: "••••" | null, preview_auto: bool, preview_debounce_ms: int }`
- PATCH accepts partial updates; empty string clears host → local
- Never echo full secrets back after save (return masked)

- [ ] **Step 1: Failing tests** — mask on get; patch host; reject writing outside allowlist keys.

- [ ] **Step 2: Implement settings_api + routes**

- [ ] **Step 3: Settings page form** + host badge fed from GET

- [ ] **Step 4: Commit** `feat(web): Settings API with masked secrets`

---

### Task 9: Jobs runner + Clab/ACT ops façade

**Files:**
- Create: `acta/web/jobs.py`, `acta/web/ops.py`
- Modify: `acta/web/app.py` — job + ops routes
- Create: `tests/test_web_jobs.py`
- Modify: `tests/test_web_api.py`

**Interfaces:**

```python
@dataclass
class Job:
    id: str
    kind: str  # clab.deploy | act.upload | ...
    status: Literal["queued","running","succeeded","failed"]
    log: str
    created_at: float
    finished_at: float | None

def submit_job(kind: str, fn: Callable[[], None]) -> Job: ...
def get_job(job_id: str) -> Job: ...

# ops.py
def require_written_path(path: Path | None) -> Path: ...  # raises WebError 400 if missing
def op_clab_generate(act_path: Path, **kwargs) -> Path: ...
def op_clab_deploy(clab_path: Path, *, host: str | None, ...) -> None: ...
def op_clab_destroy(...) -> None: ...
def op_clab_redeploy(...) -> None: ...
def op_clab_onboard(...) -> None: ...
def op_act_upload(path: Path, *, deploy: bool, ...) -> None: ...
def op_act_onboard(...) -> None: ...
```

Wrap existing `acta.clab.*` / `acta.upload.run_upload` / onboard functions.
Capture stdout/log via context or returned messages into job.log.
**Gate:** ops routes return 400 if no `path` query/body for active written topo.

- [ ] **Step 1: Job unit tests** — submit fake fn, poll until succeeded/failed.

- [ ] **Step 2: Implement jobs + ops wrappers** (local unit tests mock subprocess-heavy
      deploy where needed; at least generate path can run pure).

- [ ] **Step 3: Routes**
  - `POST /api/jobs/clab/{generate,deploy,destroy,redeploy,onboard}`
  - `POST /api/jobs/act/{upload,onboard}`
  - `GET /api/jobs`, `GET /api/jobs/{id}`

- [ ] **Step 4: Commit** `feat(web): background jobs for clab and ACT operations`

---

### Task 10: Clab / ACT / Extend / Attach SPA pages

**Files:**
- Create/Modify: `ui/src/pages/{Clab,Act,Extend,Attach}Page.tsx`
- Create: `ui/src/components/JobsDrawer.tsx`
- Wire top-bar actions per page

- [ ] **Step 1: Clab page** — Generate/Deploy/Destroy/Redeploy/Onboard buttons;
      disabled when no Active written path; poll job; show log in drawer.

- [ ] **Step 2: ACT page** — Upload (+ deploy checkbox), Onboard; honor fail-closed
      errors in toast.

- [ ] **Step 3: Extend page** — forms for `--add` leaf|spine|pair|mleaf|site + site
      fields; `POST /api/extend` writing new dated file via ops; offer set Active.

- [ ] **Step 4: Attach page** — host, switch, optional et; `POST /api/attach`; refresh PNG.

- [ ] **Step 5: Implement `POST /api/extend` and `POST /api/attach`** in app/ops if not
      done in Task 9 (call `acta.extend` / `acta.attach` / `site_extend`).

- [ ] **Step 6: Manual smoke** against a small local topo (no live trogdor required for
      generate; deploy optional).

- [ ] **Step 7: Commit** `feat(web): Clab, ACT, Extend, and Attach UI flows`

---

### Task 11: Docs polish + README happy path + help tests

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-11-21-acta-webui-design.md` — Status: approved/implemented-in-progress
- Modify: `tests/test_cli_help.py` — serve flags

- [ ] **Step 1: README section**

```markdown
## Web UI (local)

uv sync --extra ui
# first time / after ui changes:
./scripts/build-ui.sh
acta serve
```

Document: browser opens to `http://127.0.0.1:8765/`; clab host in Settings;
Graphviz required for PNG; no SSH in UI.

- [ ] **Step 2: Full `uv run pytest -q`** green.

- [ ] **Step 3: Commit** `docs: acta serve Web UI usage`

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| FastAPI + SPA Approach A | 1, 5 |
| `acta serve` + open browser + 127.0.0.1:8765 | 4 |
| Graphviz preview button/debounce | 2, 6, 8 |
| Create → Write dated file | 3, 6 |
| Labs / Show / Active topo | 3, 7 |
| Left nav + top controls + content YAML/PNG | 5–7 |
| Extend / Attach | 10 |
| Clab generate/deploy/destroy/redeploy/onboard + jobs | 9–10 |
| ACT upload/onboard + fail-closed | 9–10 |
| Settings + masked secrets + local/remote host | 8 |
| No SSH / no canvas v1 | enforced by omission |
| `uv sync --extra ui` | 1, 11 |
| Poll jobs not SSE | 9 |

## Out of plan (explicit)

- Interactive topology canvas (phase 2)
- SSE job streams
- Non-loopback bind as supported mode
- Playwright e2e (optional follow-up)
- Deferred backlog features (Clos, leaf EVPN-AA, live RAM)

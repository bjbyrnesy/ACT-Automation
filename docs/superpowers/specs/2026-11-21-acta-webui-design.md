# ACTA local Web UI — Design Spec

**Date:** 2026-11-21  
**Branch intent:** `feat/acta-webui` (implementation follows a separate plan)  
**Status:** implemented on `feat/acta-webui` (review/PR)  
**Approach:** Library-backed FastAPI + SPA (Approach A)

## Summary

Ship a **localhost Web UI** on the operator’s Mac that exposes essentially the full
`acta` ops surface (create, extend, show/preview, attach, clab generate/deploy/
destroy/redeploy/onboard, ACT upload/onboard) with a **Graphviz PNG preview** of
the active or in-progress topology. Launch via **`acta serve`**, which starts the
server and opens the browser.

The UI calls **`acta` Python APIs in-process** (not CLI subprocess scraping).
Containerlab may target **local or remote** hosts (same model as `CLAB_HOST` /
`--host`). Interactive TTY prompts become forms. SSH into nodes is out of scope.

## Goals

- Configure a fabric in the browser and preview topology **before** writing files.
- Support **button** preview and optional **debounced** auto-refresh after form edits.
- Cover day-1 and day-2 ops that make sense in a UI (see [Ported vs demoted](#ported-vs-demoted)).
- One **active topology** mental model: Labs picker + draft-until-Write for Create.
- Zero-friction launch: `acta serve` → browser → app on `127.0.0.1`.
- Preserve CLI as the source of truth for topology math, port plans, and remotes.

## Non-goals (v1)

- SSH into lab nodes (`acta ssh`).
- Interactive canvas / draw nodes and links (phase-2 seam only).
- Binding `0.0.0.0`, reverse proxy, or multi-user auth.
- Fake full-screen TTY for deploy logs (jobs + log tail instead).
- Default Show path that SSH-probes every node (optional later; can hang on remote).
- Implementing deferred backlog features (Clos WAN, leaf EVPN-AA, live RAM probe)
  inside the UI.
- Windows as the primary design target (best-effort only).
- Subprocess-wrapping every `acta` CLI invocation as the integration strategy.

## Decisions (locked)

| Topic | Choice |
| --- | --- |
| Product shape | Full ops console (not designer-only); no SSH |
| UI host | Mac localhost; clab **local or remote** |
| Preview v1 | Graphviz PNG (same engine as `acta` diagram/show) |
| Preview later | Interactive canvas for nodes/links (serialize via same YAML model) |
| Stack | FastAPI JSON API + small SPA (modern/responsive) |
| Integration | In-process library façade over `acta.*` (Approach A) |
| Chrome | Left vertical nav; top horizontal contextual controls; content = topo + diagram |
| Launcher | `acta serve` (optional alias `acta ui`): bind 127.0.0.1, open browser |
| Draft rule | Create/edit draft in memory; Write persists; deploy/upload need written path |
| Secrets | `.config` / env; masked on read; never commit |

## Ported vs demoted

| CLI surface | UI v1 |
| --- | --- |
| `act create` / `clab create` | Forms → preview → Write |
| `act extend` / site-add | Structured forms → new dated file |
| `show` / diagram | Content pane PNG + summary |
| `attach` | Form against Active topo |
| `clab generate\|deploy\|destroy\|redeploy\|onboard` | Top-bar actions + jobs |
| `act upload\|onboard` | Forms + jobs; fail-closed on stale “already exists” |
| `ssh` | **Out** |
| Interactive TTY prompts | **Replaced by forms** |
| Clab SSH reachability probes | **Demoted** (optional later) |
| Streaming deploy TTY | **Demoted** → job status + log tail |

## Architecture

```text
  Browser (SPA)
       │  REST/JSON (+ optional SSE for jobs)
       ▼
┌──────────────────┐     ┌─────────────────────────────┐
│  acta serve      │────▶│  FastAPI (127.0.0.1:8765)   │
│  open browser    │     │  /api/*  + static ui/dist   │
└──────────────────┘     └──────────────┬──────────────┘
                                        │ in-process
                                        ▼
                         ┌──────────────────────────────┐
                         │  acta library façade         │
                         │  create/extend/diagram/      │
                         │  clab/upload/attach/config   │
                         └──────────┬───────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              local files     local podman     remote CLAB_HOST
              (*.yml)         / docker         (SSH as today)
```

### Library façade

CLI today is argparse-centric. The Web UI requires a thin, testable façade
(functions/dataclasses) that:

- Accept structured create/extend/attach/upload parameters (no stdin prompts).
- Return YAML text, file paths, summary DTOs, and PNG bytes (or paths).
- Raise typed errors the API maps to HTTP 4xx/5xx + JSON `{detail, fields?}`.

Prefer extracting shared entrypoints used by both CLI and API over duplicating
logic. Subprocess to `acta` CLI is explicitly rejected for preview and core ops.

### SPA shell

```text
┌─────────┬──────────────────────────────────────────┐
│ Vertical│  Horizontal sub-nav / controls           │
│  nav    ├──────────────────────────────────────────┤
│         │  Content: current topology + Graphviz    │
│ Labs    │  diagram (preview / show)                │
│ Create  │                                          │
│ Extend  │                                          │
│ Clab    │                                          │
│ ACT     │                                          │
│ Attach  │                                          │
│ Show    │                                          │
│ Settings│                                          │
└─────────┴──────────────────────────────────────────┘
```

Top bar always shows **active topology name** (or “Draft”) and **clab host badge**
(`local` | configured hostname).

## Launcher & runtime

**Command:** `acta serve` (alias `acta ui` allowed).

| Flag / behavior | Default |
| --- | --- |
| Bind | `127.0.0.1` |
| Port | `8765` (`--port` / env override) |
| Open browser | yes (`--no-open` to skip) |
| Labs root | cwd or `--root` |
| Stop | Ctrl-C (v1); no `serve --stop` required |

Happy path for users:

```text
uv sync --extra ui
acta serve
```

Dev may run Vite against the API; production assets live under a served `ui/dist`
(or equivalent). Document whether first-run builds UI or CI ships prebuilt assets;
choose one in the implementation plan and keep `acta serve` free of mandatory
manual `npm` for the happy path.

## Create + preview data flow

```text
SPA form (capacity, sites, redundancy, platform…)
        │  Preview (button) or debounced auto-refresh
        ▼
POST /api/preview  →  acta emit (in-process)  →  YAML + Graphviz PNG
        │
        │  Write
        ▼
POST /api/topologies  →  dated *.yml on disk  →  Active topology
```

- **Create form** mirrors interactive create: fabric mode, spines/leaves/pairs,
  max capacity, named sites, bb/border redundancy, hostname prefix, EOS version,
  target **act / clab / both**.
- **Draft** stays in memory until Write; content pane shows draft YAML + PNG.
- Auto-preview debounce ~300–500ms when Settings enable it; manual Preview always
  available. On validation failure, keep last-good PNG and show field errors.
- **Labs / Show:** selecting a file sets Active topology; same content pane.
- **Extend:** starts from written Active topo; always proposes a **new dated**
  output file (CLI parity); offer “set Active” after success.

**Phase-2 seam:** interactive canvas edits must serialize into the same ACT YAML
model before preview/write; no parallel topology truth.

## Clab / ACT / Attach + jobs

**Gate:** Deploy, Destroy, Redeploy, Upload, Onboard require a **written** Active
topology path. Drafts are preview/Write only.

**Clab actions** (contextual top bar): Generate, Deploy, Redeploy, Destroy,
Onboard. Host from Settings (empty = local). Compact form for mgmt overrides
when needed. Long work runs as a **job** (`id`, `status`, `log` tail); UI polls
or uses light SSE — not a fake terminal.

**ACT:** Upload (respect fail-closed when topology already exists), Onboard
TerminAttr to running devices.

**Attach:** host name, switch, optional Ethernet, credentials defaults from
Settings; refresh PNG after successful write/sync.

**Jobs UI:** drawer or bottom panel — last N jobs, expandable logs. Cancel only
where the underlying operation supports it; v1 may be wait + dismiss.

**Errors:** map domain errors to toasts + job log; no raw tracebacks in the main
content pane.

## Settings & security

**Settings fields:** labs root; clab host (local vs remote) + existing image/
runtime defaults; ACT tenant / API key / CVaaS token; Attach credential defaults;
preview auto-refresh toggle + debounce.

**Security (v1):**

- Bind loopback only by default.
- Single-operator; no login system.
- Secrets masked on GET; update via POST/PATCH.
- Do not return full secret material in list/detail payloads.

## Packaging

- Optional extra: `uv sync --extra ui` (fastapi, uvicorn, and UI build deps as needed).
- SPA source under `ui/`; `acta serve` serves the production build.
- Graphviz `dot` required for PNG — Settings/health endpoint reports missing `dot`.
- Reuse existing `.config` conventions; never commit secrets.

## API sketch (illustrative)

Exact routes land in the implementation plan; shape:

| Area | Examples |
| --- | --- |
| Health | `GET /api/health` (dot, clab host reachability soft-check) |
| Labs | `GET/POST /api/topologies`, `GET /api/topologies/{id}` |
| Preview | `POST /api/preview` → `{ yaml, png_base64\|url, summary }` |
| Extend / Attach | `POST /api/extend`, `POST /api/attach` |
| Clab / ACT | `POST /api/clab/{generate,deploy,…}`, `POST /api/act/{upload,onboard}` |
| Jobs | `GET /api/jobs`, `GET /api/jobs/{id}` |
| Settings | `GET/PATCH /api/settings` |

Static SPA: `GET /` and assets from `ui/dist`.

## Testing

- Unit tests for the library façade (create/preview/extend parameter paths).
- API tests: preview validation errors, Write creates dated file, upload
  fail-closed, job status transitions.
- Existing `acta` pytest suite remains the topology-correctness gate.
- Optional later: Playwright smoke for `acta serve` + Create → Preview → Write.

## Implementation notes (for planning)

1. Extract façade / promptless create before large SPA investment.
2. Vertical slice: `acta serve` + Labs + Create preview/Write + Show PNG.
3. Then Extend, Attach, Clab jobs, ACT jobs, Settings polish.
4. Keep CLI behavior unchanged except adding `serve` subcommand.

## Open points (resolve in implementation plan, not blockers)

- SPA framework pick inside “small SPA” (React vs Vue vs Svelte) — prefer whatever
  keeps the repo light and meets responsive UX; default recommendation **React + Vite**
  unless plan justifies otherwise.
- Prebuilt `ui/dist` in git vs build step in packaging — prefer **build in CI /
  package**, not committing minified churn, unless distribution constraints force it.
- SSE vs poll for jobs — poll is enough for v1.

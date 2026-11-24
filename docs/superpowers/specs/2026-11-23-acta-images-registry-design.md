# ACTA Web UI — Images page + registry (local load first)

**Date:** 2026-11-23  
**Status:** approved design (awaiting implementation plan)  
**Approach:** A — Images page with upload→load primary; registry push/pull secondary

## Summary

Add a dedicated **Images** nav page so operators can get cEOS and host/jumphost
images onto the lab host without leaving the Web UI. The default path is
**upload an image archive → `docker`/`podman load` on the lab host**. A registry
(URL + credentials in Settings) is optional for **push** / **pull** when other
hosts (e.g. acta-docker) need the same images.

Beginners never need a registry. Advanced users set `hub.freeblizz.com` (or
similar), push once, and pull on each lab host.

## Goals

- Upload a cEOS/host image archive and **load** it onto the configured lab host.
- List images already present on that host (same runtime as clab deploy).
- Optionally tag after load when the archive name/tag is wrong or empty.
- Optionally **push** a local image to a configured registry and **pull** from it.
- Store registry URL + username + token in Settings (token masked like
  `ACT_API_KEY`).
- Let the user set `CLAB_IMAGE` / `CLAB_HOST_IMAGE` from a listed image so Deploy
  uses what they just loaded.
- Run long operations as **background jobs** with the existing Jobs drawer
  (colored logs).

## Non-goals (v1)

- Running a registry inside Acta.
- `docker`/`podman import` (filesystem tarballs). Only **load** of image
  archives (`.tar`, `.tar.gz`, `.tgz`, `.xz`).
- Auto-pull during Deploy when an image is missing.
- Multi-host fan-out (push once → pull on N hosts in one click).
- Building the host multitool image from the UI (`scripts/build-host-image.sh`
  remains CLI/host-side).
- Editing or deleting remote registry catalogs beyond push/pull of named tags.

## Decisions (locked)

| Topic | Choice |
| --- | --- |
| UX home | Dedicated **Images** page (left nav); Settings holds registry/creds only |
| Beginner path | Upload → load on lab host; no registry required |
| Advanced path | Settings registry + Images push/pull |
| Auth | Settings: `CLAB_REGISTRY`, `CLAB_REGISTRY_USER`, `CLAB_REGISTRY_TOKEN` |
| Runtime | Same resolution as clab (`CLAB_RUNTIME` / env / auto-detect) |
| Lab host | Same as clab (`CLAB_HOST` empty = local) |
| Upload cap | **10 GB** per archive |
| Job UX | Background jobs + Jobs drawer logs |
| Deploy | Unchanged; uses `CLAB_IMAGE` / `CLAB_HOST_IMAGE` only (no auto-pull) |
| Load vs import | **load** only |

## Settings fields

| Key | Purpose |
| --- | --- |
| `CLAB_REGISTRY` | Registry host and optional path prefix (e.g. `hub.freeblizz.com` or `hub.freeblizz.com/acta`) |
| `CLAB_REGISTRY_USER` | Username for `login` |
| `CLAB_REGISTRY_TOKEN` | Password/token; masked on read; never echoed in job logs |

Empty `CLAB_REGISTRY` → Images page hides or disables Push/Pull; Upload & load
remains available.

Existing `CLAB_IMAGE`, `CLAB_RUNTIME`, and `CLAB_HOST` stay as today. Expose
`CLAB_HOST_IMAGE` in Settings (it already exists in `.config` / generate) so
host/jumphost refs are editable without hand-editing files. Images page
“Use as …” actions patch the same keys.

## Images page

### List

- Query lab host for images via the selected runtime.
- Columns: repository, tag, ID (short), size, created.
- Refresh control.

### Upload & load (primary)

1. File picker accepts `.tar`, `.tar.gz`, `.tgz`, `.xz`.
2. Reject uploads over **10 GB** with a clear client + server error.
3. Submit starts job `images.load`:
   - Stream multipart body to a temp file on the lab host (or local temp then
     copy when `CLAB_HOST` is set — implementation may choose the safer path
     for large files).
   - Run `docker load` or `podman load` (runtime-aware).
   - Delete the temp archive on success or failure.
   - Log resulting image references from load output.
4. Optional **name** / **tag** fields: after load, `docker|podman tag` to the
   requested reference when provided.
5. UI copy: local-only by default; use Push when other hosts need the image.

### Registry actions (secondary)

Visible only when `CLAB_REGISTRY` is non-empty.

- **Push** — body `{ "image": "ceos:4.37.0F" }` (local name). Job:
  login → tag under registry prefix → push → log digest/name.
- **Pull** — body `{ "image": "ceos:4.37.0F" }` or fully-qualified ref. Job:
  login → pull onto lab host (prefix with registry when the ref is short).

Login uses the runtime CLI with password on stdin (or equivalent); token must
not appear in captured stdout/stderr (redact if the CLI echoes it).

### Wire to Deploy settings

- Actions on a list row (or form): “Use as CLAB_IMAGE” / “Use as CLAB_HOST_IMAGE”
  patch Settings so the next generate/deploy picks that ref.

## API

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/images` | List images on lab host |
| `POST` | `/api/jobs/images/load` | Multipart upload → load job |
| `POST` | `/api/jobs/images/push` | JSON `{ image }` → push job |
| `POST` | `/api/jobs/images/pull` | JSON `{ image }` → pull job |

Settings GET/PATCH gain the three `CLAB_REGISTRY*` keys (token masked).

Job payloads follow the existing jobs registry (`queued` / `running` /
`succeeded` / `failed` + `log`).

## Lab host execution

Reuse the clab host-run pattern (`host_run` / SSH when `CLAB_HOST` is set):

- Resolve runtime exactly as deploy does (preferred → probe → fallback).
- Prefer non-interactive flags; fail with actionable errors (daemon down,
  auth failed, disk full, cap exceeded).

## Security

- Secrets only in labs `.config` (owner-only) or env; never commit.
- Token masked in Settings API responses (`••••` / null when empty).
- Redact token strings from job logs.
- Path confinement for any host-side temp files under a dedicated directory.
- No registry credential in browser localStorage.

## Testing

- Unit: registry prefix joining; short vs fully-qualified pull refs; redact
  helpers; upload size rejection.
- API: settings round-trip for registry keys; load/push/pull job submission
  with mocked host_run.
- UI smoke: Images route renders; push/pull controls gated on registry.

## Rollout

1. Settings + config keys.
2. `GET /api/images` + Images page list.
3. Load job + upload UI.
4. Push/pull jobs + gated UI.
5. “Use as CLAB_IMAGE / CLAB_HOST_IMAGE” affordances.
6. Docs: README note that cEOS is load-from-Arista-archive, not Docker Hub.

## Open implementation notes (not design blockers)

- Prefer streaming upload to avoid double disk use on the WebUI host when the
  lab host is remote.
- Exact `podman`/`docker login` flags may differ; wrap behind one helper.
- Whether list parsing uses `{{json}}` format templates vs table parse — prefer
  structured JSON from the runtime CLI.

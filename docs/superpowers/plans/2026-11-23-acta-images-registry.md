# ACTA Images page + registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Web UI Images page that loads image archives onto the lab host (primary) and optionally pushes/pulls via a Settings-configured registry.

**Architecture:** New `acta/web/images.py` façade runs `docker`/`podman` on the lab host through existing `host_run` + `resolve_clab_runtime`. FastAPI routes under `/api/images` and `/api/jobs/images/*` submit background jobs. SPA gets `/images` with list/upload/push/pull; Settings stores registry URL/user/token (token masked).

**Tech Stack:** Python ≥3.15, FastAPI, pytest, React + Vite + TypeScript, existing Jobs drawer.

**Spec:** `docs/superpowers/specs/2026-11-23-acta-images-registry-design.md`

## Global Constraints

- Upload cap **10 GB** (`10 * 1024**3` bytes); reject over limit with HTTP 400.
- **load** only (never `import`); accept `.tar`, `.tar.gz`, `.tgz`, `.xz`.
- Registry optional: empty `CLAB_REGISTRY` → no push/pull UI/actions.
- Token in `.config` mode 600; mask as `••••` on GET; never print token in job logs.
- Same runtime/host resolution as clab deploy (`CLAB_RUNTIME` / env / auto-detect; `CLAB_HOST`).
- No auto-pull during Deploy in v1.
- Format black; lint ruff; `npm run build` green for UI.
- Work on branch `feat/acta-images-registry` (create from current tip if needed).

## File map

| File | Responsibility |
|------|----------------|
| `acta/config.py` | Add `CLAB_REGISTRY`, `CLAB_REGISTRY_USER`, `CLAB_REGISTRY_TOKEN` to `CONFIG_KEYS` |
| `acta/web/settings_api.py` | Allowlist + mask registry token; expose `CLAB_HOST_IMAGE` |
| `acta/web/images.py` | List/load/push/pull helpers; registry ref join; redact; size const |
| `acta/web/routes_images.py` | `GET /api/images`, job routes for load/push/pull |
| `acta/web/app.py` | Mount images router |
| `ui/src/pages/ImagesPage.tsx` | Images UI |
| `ui/src/pages/ImagesPage.css` | Page styles |
| `ui/src/pages/SettingsPage.tsx` | Registry + `CLAB_HOST_IMAGE` fields |
| `ui/src/layout/LeftNav.tsx` | Nav link to `/images` |
| `ui/src/App.tsx` | Route `/images` |
| `ui/src/api/client.ts` | API helpers |
| `tests/test_web_images.py` | Unit + API tests for images façade/routes |
| `tests/test_web_settings.py` | Registry settings round-trip |
| `README.md` | Short note: cEOS via load, not Docker Hub |

---

### Task 1: Config keys + Settings API (registry + CLAB_HOST_IMAGE)

**Files:**
- Modify: `acta/config.py`
- Modify: `acta/web/settings_api.py`
- Modify: `tests/test_web_settings.py`
- Modify: `ui/src/pages/SettingsPage.tsx` (fields only; can wait until Task 6 if preferred — do backend first here, UI fields in Task 6)

**Interfaces:**
- Produces: config keys `CLAB_REGISTRY`, `CLAB_REGISTRY_USER`, `CLAB_REGISTRY_TOKEN`, and Settings exposure of `CLAB_HOST_IMAGE`
- Produces: `CLAB_REGISTRY_TOKEN` in `_SECRET_KEYS`; masked on GET

- [ ] **Step 1: Write failing settings tests**

```python
def test_patch_registry_settings_masks_token(tmp_path: Path):
    from acta.web.settings_api import get_settings, patch_settings, MASK

    patched = patch_settings(
        tmp_path,
        {
            "CLAB_REGISTRY": "hub.freeblizz.com/acta",
            "CLAB_REGISTRY_USER": "acta",
            "CLAB_REGISTRY_TOKEN": "s3cret",
            "CLAB_HOST_IMAGE": "localhost/acta-host-multitool:v0.10.0-mcast0.2.3",
        },
    )
    assert patched["CLAB_REGISTRY"] == "hub.freeblizz.com/acta"
    assert patched["CLAB_REGISTRY_USER"] == "acta"
    assert patched["CLAB_REGISTRY_TOKEN"] == MASK
    assert patched["CLAB_HOST_IMAGE"].startswith("localhost/acta-host")
    again = get_settings(tmp_path)
    assert again["CLAB_REGISTRY_TOKEN"] == MASK


def test_patch_registry_token_mask_preserves_secret(tmp_path: Path):
    from acta.config import load_config
    from acta.web.settings_api import MASK, config_path, patch_settings

    patch_settings(tmp_path, {"CLAB_REGISTRY_TOKEN": "s3cret"})
    patch_settings(tmp_path, {"CLAB_REGISTRY_TOKEN": MASK})
    assert load_config(config_path(tmp_path))["CLAB_REGISTRY_TOKEN"] == "s3cret"
```

- [ ] **Step 2: Run tests — expect fail**

Run: `.venv/bin/python -m pytest tests/test_web_settings.py::test_patch_registry_settings_masks_token tests/test_web_settings.py::test_patch_registry_token_mask_preserves_secret -v`  
Expected: FAIL (keys not allowlisted / missing)

- [ ] **Step 3: Implement**

In `acta/config.py` add to `CONFIG_KEYS` (near other `CLAB_*`):

```python
"CLAB_HOST_IMAGE",  # already present — verify
"CLAB_REGISTRY",
"CLAB_REGISTRY_USER",
"CLAB_REGISTRY_TOKEN",
```

In `acta/web/settings_api.py`:

```python
_SECRET_KEYS = frozenset({
    "ACT_API_KEY",
    "CVAAS_TOKEN",
    "GENERIC_PASSWORD",
    "CLAB_REGISTRY_TOKEN",
})
_EXACT_KEYS = frozenset({
    "CLAB_HOST",
    "CLAB_IMAGE",
    "CLAB_HOST_IMAGE",
    "CLAB_NAME",
    "CLAB_RUNTIME",
    "CLAB_REGISTRY",
    "CLAB_REGISTRY_USER",
    "CLAB_REGISTRY_TOKEN",
    "preview_auto",
    "preview_debounce_ms",
})
```

In `get_settings`, include `CLAB_HOST_IMAGE` and the three registry keys in the initial `out` dict (token via `_mask_value`). Keep prefix loop coherent so duplicates are not double-added.

- [ ] **Step 4: Run tests — expect pass**

Run: `.venv/bin/python -m pytest tests/test_web_settings.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/config.py acta/web/settings_api.py tests/test_web_settings.py
git commit -m "$(cat <<'EOF'
feat(web): settings for registry creds and CLAB_HOST_IMAGE

EOF
)"
```

---

### Task 2: Image helpers (refs, redact, list parse)

**Files:**
- Create: `acta/web/images.py`
- Create: `tests/test_web_images.py`

**Interfaces:**
- Produces:
  - `UPLOAD_MAX_BYTES = 10 * 1024**3`
  - `ALLOWED_ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".xz")`
  - `def registry_image_ref(registry: str, image: str) -> str`
  - `def redact_secrets(text: str, secrets: list[str]) -> str`
  - `def parse_images_json(raw: str) -> list[dict[str, str]]`
  - `def assert_archive_name(filename: str) -> None`  # raises WebError 400

- [ ] **Step 1: Write failing unit tests**

```python
from acta.web.images import (
    ALLOWED_ARCHIVE_SUFFIXES,
    UPLOAD_MAX_BYTES,
    assert_archive_name,
    parse_images_json,
    redact_secrets,
    registry_image_ref,
)
from acta.web.errors import WebError
import pytest

def test_upload_max_is_10gib():
    assert UPLOAD_MAX_BYTES == 10 * 1024**3

def test_registry_image_ref_joins_short_name():
    assert (
        registry_image_ref("hub.freeblizz.com/acta", "ceos:4.37.0F")
        == "hub.freeblizz.com/acta/ceos:4.37.0F"
    )

def test_registry_image_ref_keeps_fully_qualified():
    full = "hub.freeblizz.com/acta/ceos:4.37.0F"
    assert registry_image_ref("hub.freeblizz.com/acta", full) == full

def test_registry_image_ref_strips_trailing_slash():
    assert (
        registry_image_ref("hub.freeblizz.com/acta/", "ceos:1")
        == "hub.freeblizz.com/acta/ceos:1"
    )

def test_redact_secrets_replaces_token():
    assert redact_secrets("login s3cret ok", ["s3cret"]) == "login **** ok"

def test_parse_images_json_rows():
    raw = '[{"Repository":"ceos","Tag":"4.37.0F","Id":"abc","Size":"2GB","CreatedAt":"2026"}]\n'
    rows = parse_images_json(raw)
    assert rows[0]["repository"] == "ceos"
    assert rows[0]["tag"] == "4.37.0F"

def test_assert_archive_name_rejects_bad_suffix():
    with pytest.raises(WebError) as ei:
        assert_archive_name("evil.exe")
    assert ei.value.status_code == 400
```

- [ ] **Step 2: Run — expect fail** (module missing)

Run: `.venv/bin/python -m pytest tests/test_web_images.py -k "registry_image_ref or redact or parse or assert_archive or upload_max" -v`  
Expected: FAIL import

- [ ] **Step 3: Implement `acta/web/images.py` (helpers only)**

```python
"""Lab-host image list / load / push / pull helpers for the Web UI."""

from __future__ import annotations

import json
import re
from typing import Any

from acta.web.errors import WebError

UPLOAD_MAX_BYTES = 10 * 1024**3
ALLOWED_ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".xz")

def assert_archive_name(filename: str) -> None:
    name = (filename or "").lower()
    if not any(name.endswith(suffix) for suffix in ALLOWED_ARCHIVE_SUFFIXES):
        raise WebError(
            400,
            "archive must be .tar, .tar.gz, .tgz, or .xz",
            fields={"file": "invalid"},
        )

def registry_image_ref(registry: str, image: str) -> str:
    reg = registry.strip().rstrip("/")
    img = image.strip()
    if not reg:
        raise WebError(400, "CLAB_REGISTRY is not set", fields={"CLAB_REGISTRY": "required"})
    if not img:
        raise WebError(400, "image is required", fields={"image": "required"})
    # Already under this registry (or another host/path with a slash before tag)
    if img.startswith(f"{reg}/"):
        return img
    # Fully-qualified elsewhere: contains / before :tag and looks like host/…
    if "/" in img.split(":")[0] and not img.startswith("localhost/"):
        return img
    return f"{reg}/{img}"

def redact_secrets(text: str, secrets: list[str]) -> str:
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "****")
    return out

def parse_images_json(raw: str) -> list[dict[str, str]]:
    """Parse ``docker/podman images --format json`` (array or NDJSON)."""
    text = (raw or "").strip()
    if not text:
        return []
    rows: list[Any]
    if text.startswith("["):
        rows = json.loads(text)
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "repository": str(row.get("Repository") or row.get("repository") or ""),
                "tag": str(row.get("Tag") or row.get("tag") or ""),
                "id": str(row.get("Id") or row.get("ID") or row.get("id") or "")[:12],
                "size": str(row.get("Size") or row.get("size") or ""),
                "created": str(
                    row.get("CreatedAt")
                    or row.get("createdAt")
                    or row.get("Created")
                    or row.get("created")
                    or ""
                ),
            }
        )
    return out
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/python -m pytest tests/test_web_images.py -k "registry_image_ref or redact or parse or assert_archive or upload_max" -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acta/web/images.py tests/test_web_images.py
git commit -m "$(cat <<'EOF'
feat(web): image ref helpers and archive validation

EOF
)"
```

---

### Task 3: List images on lab host + GET /api/images

**Files:**
- Modify: `acta/web/images.py`
- Create: `acta/web/routes_images.py`
- Modify: `acta/web/app.py` (include router)
- Modify: `tests/test_web_images.py`

**Interfaces:**
- Consumes: `resolve_clab_runtime`, `host_run`, `read_config` / settings for host+runtime
- Produces: `def list_host_images(*, host: str | None, runtime: str | None) -> list[dict[str, str]]`
- Produces: `GET /api/images` → `{ "images": [...], "runtime": "docker", "host": "" }`

- [ ] **Step 1: Failing tests with mocked host_run**

```python
def test_list_host_images_uses_runtime(monkeypatch):
    from acta.web import images as img

    calls = []

    def fake_host_run(host, script, args, data):
        calls.append((host, args))
        class R:
            returncode = 0
            stdout = '[{"Repository":"ceos","Tag":"4.37.0F","Id":"deadbeef","Size":"1","CreatedAt":"x"}]'
            stderr = ""
        return R()

    monkeypatch.setattr(img, "host_run", fake_host_run)
    monkeypatch.setattr(img, "resolve_clab_runtime", lambda host, preferred=None: "docker")
    rows = img.list_host_images(host=None, runtime="docker")
    assert rows[0]["repository"] == "ceos"
    assert calls and calls[0][1][0] == "docker"


def test_get_api_images(client, monkeypatch):  # use existing TestClient fixture pattern from test_web_api
    from acta.web import images as img
    monkeypatch.setattr(
        img,
        "list_host_images",
        lambda **kw: [{"repository": "ceos", "tag": "1", "id": "abc", "size": "1", "created": ""}],
    )
    monkeypatch.setattr(img, "resolve_clab_runtime", lambda host, preferred=None: "docker")
    # Also patch wherever the route imports list_host_images if different
    r = client.get("/api/images")
    assert r.status_code == 200
    assert r.json()["images"][0]["repository"] == "ceos"
```

Wire the test client the same way as `tests/test_web_api.py` / `test_web_ops.py` (`create_app(labs_root=tmp_path)`).

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement list + route**

`list_host_images` script (via `host_run`):

```bash
set -eu
runtime="$1"
# Prefer JSON; podman and docker both support --format json (docker 1.41+ / compose style varies)
# Use go-template JSON lines for broader docker compatibility:
exec "$runtime" images --format '{{json .}}'
```

Parse with `parse_images_json`. On nonzero returncode raise `WebError(502, stderr)`.

`routes_images.py`:

```python
@router.get("/api/images")
def get_images(request: Request) -> dict[str, Any]:
    settings = get_settings(Path(request.app.state.labs_root))
    host = str(settings.get("CLAB_HOST") or "").strip() or None
    preferred = str(settings.get("CLAB_RUNTIME") or os.environ.get("CLAB_RUNTIME") or "").strip().lower()
    if preferred not in {"docker", "podman"}:
        preferred = None
    runtime = resolve_clab_runtime(host, preferred)
    images = list_host_images(host=host, runtime=runtime)
    return {"images": images, "runtime": runtime, "host": host or ""}
```

Include router in `create_app`.

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(web): list lab-host container images via API

EOF
)"
```

---

### Task 4: Load job (upload → docker/podman load)

**Files:**
- Modify: `acta/web/images.py`
- Modify: `acta/web/routes_images.py`
- Modify: `tests/test_web_images.py`

**Interfaces:**
- Produces: `def load_archive_on_host(*, host, runtime, archive_path: Path, name: str | None, tag: str | None) -> None` (prints progress to stdout for job log)
- Produces: `POST /api/jobs/images/load` multipart: `file`, optional `name`, `tag`
- Behavior: save under `labs_root / ".acta-uploads" / <uuid><suffix>`; enforce size while streaming; submit job that loads then deletes local (and remote temp if used)

- [ ] **Step 1: Failing tests**

```python
def test_reject_oversized_upload_header(client):
    # If Content-Length > UPLOAD_MAX_BYTES, 400 before reading body
    ...

def test_load_job_calls_load(monkeypatch, client, tmp_path):
    seen = {}
    def fake_load(**kwargs):
        seen.update(kwargs)
        print("Loaded ceos:4.37.0F")
    monkeypatch.setattr("acta.web.images.load_archive_on_host", fake_load)
    # Or patch where route imports it
    data = b"not-a-real-tar-but-ok-for-route"
    r = client.post(
        "/api/jobs/images/load",
        files={"file": ("ceos.tar", data, "application/x-tar")},
        data={"name": "ceos", "tag": "4.37.0F"},
    )
    assert r.status_code == 200
    job_id = r.json()["id"]
    # poll until finished like test_web_ops
    ...
    assert seen["name"] == "ceos"
```

Also unit-test `load_archive_on_host` with mocked `host_run` verifying args contain `load`.

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement**

Streaming save:

```python
async def _save_upload(upload: UploadFile, dest: Path) -> int:
    total = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > UPLOAD_MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise WebError(400, "archive exceeds 10GB limit", fields={"file": "too large"})
            out.write(chunk)
    return total
```

If `Content-Length` present and `> UPLOAD_MAX_BYTES`, reject immediately.

`load_archive_on_host`:
- Local host: `docker|podman load -i <path>`
- Remote: `scp` archive to `/tmp/acta-upload-<id>.tar` (or `host_run` with base64 only for tiny files — **do not** base64 10GB; use `scp`/`rsync` via subprocess)
- Optional tag: parse `Loaded image: …` lines; if `name` and `tag` set, `docker tag <src> name:tag` (if load output has an ID/name, tag from that; else tag `name:tag` from the first loaded ref)

Always `unlink` temps in `finally`.

Job kind: `images.load`.

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(web): upload and load image archives on lab host

EOF
)"
```

---

### Task 5: Push + pull jobs

**Files:**
- Modify: `acta/web/images.py`
- Modify: `acta/web/routes_images.py`
- Modify: `tests/test_web_images.py`

**Interfaces:**
- Produces: `def push_image(*, host, runtime, image, registry, user, token) -> None`
- Produces: `def pull_image(*, host, runtime, image, registry, user, token) -> None`
- Produces: `POST /api/jobs/images/push` JSON `{ "image": "ceos:4.37.0F" }`
- Produces: `POST /api/jobs/images/pull` JSON `{ "image": "ceos:4.37.0F" }`
- Both require non-empty `CLAB_REGISTRY` from settings (400 otherwise)

- [ ] **Step 1: Failing tests**

```python
def test_push_requires_registry(client, tmp_path):
    r = client.post("/api/jobs/images/push", json={"image": "ceos:1"})
    assert r.status_code == 400

def test_push_job_redacts_token(monkeypatch, client, tmp_path):
    # save registry+token in settings; mock push to print token; assert job.log has ****
    ...
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement**

Login helper (password on stdin):

```bash
set -eu
runtime="$1"
server="$2"
user="$3"
printf '%s' "$LOGIN_TOKEN" | "$runtime" login --username "$user" --password-stdin "$server"
```

Pass token via env `LOGIN_TOKEN` in a dedicated `host_run` variant **or** extend call to pass env — if `host_run` has no env today, add optional `env: dict | None = None` to `host_run` in `acta/clab/support.py` and use it only for login. Redact token from job log via wrapping prints through `redact_secrets`.

Push: `tag` local → `registry_image_ref` → `push` that ref.  
Pull: resolve ref with `registry_image_ref` → `pull`.

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(web): push and pull images via configured registry

EOF
)"
```

---

### Task 6: SPA — Settings fields + Images page + nav

**Files:**
- Modify: `ui/src/pages/SettingsPage.tsx`
- Create: `ui/src/pages/ImagesPage.tsx`, `ui/src/pages/ImagesPage.css`
- Modify: `ui/src/App.tsx`, `ui/src/layout/LeftNav.tsx`
- Modify: `ui/src/api/client.ts`
- Optional: `ui/scripts/images-page-smoke.ts` only if valuable; otherwise rely on `npm run build`

**Interfaces:**
- Produces: client helpers `listImages()`, `loadImageArchive(file, {name?, tag?})`, `pushImage(image)`, `pullImage(image)`
- Produces: route `/images` with JobsDrawer for jobs

- [ ] **Step 1: Extend `client.ts`**

```typescript
export type HostImage = {
  repository: string;
  tag: string;
  id: string;
  size: string;
  created: string;
};

export function listImages() {
  return getJson<{ images: HostImage[]; runtime: string; host: string }>("/api/images");
}

export function loadImageArchive(
  file: File,
  opts: { name?: string; tag?: string } = {},
) {
  const body = new FormData();
  body.append("file", file);
  if (opts.name) body.append("name", opts.name);
  if (opts.tag) body.append("tag", opts.tag);
  return postForm<Job>("/api/jobs/images/load", body); // add postForm helper if missing
}

export function pushImage(image: string) {
  return postJson<Job>("/api/jobs/images/push", { image });
}

export function pullImage(image: string) {
  return postJson<Job>("/api/jobs/images/pull", { image });
}
```

If `postForm` does not exist, implement next to `postJson` (no JSON Content-Type; let browser set multipart boundary).

Client-side reject: `if (file.size > 10 * 1024 ** 3) throw …`.

- [ ] **Step 2: SettingsPage** — add inputs for `CLAB_HOST_IMAGE`, `CLAB_REGISTRY`, `CLAB_REGISTRY_USER`, `CLAB_REGISTRY_TOKEN` (token treated like other secrets / MASK).

- [ ] **Step 3: ImagesPage**

Layout:
1. Header + Refresh  
2. Table of images  
3. Row actions: Use as CLAB_IMAGE / Use as CLAB_HOST_IMAGE (PATCH settings)  
4. Upload & load form (file + optional name/tag) + short help text  
5. If settings.CLAB_REGISTRY: Push (selected/local image input) + Pull (image input)

Reuse `JobsDrawer` like `DeployPage`.

- [ ] **Step 4: Nav + route**

```tsx
// LeftNav PRIMARY
{ to: "/images", label: "Images", end: true },
{ to: "/settings", label: "Settings", end: true },

// App.tsx
<Route path="images" element={<ImagesPage />} />
```

- [ ] **Step 5: Build**

Run: `cd ui && npm run build`  
Expected: success

- [ ] **Step 6: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(ui): Images page with load and optional registry push/pull

EOF
)"
```

---

### Task 7: README note + final verification

**Files:**
- Modify: `README.md` (clab / images section near `CLAB_HOST_IMAGE` / build-host-image)

- [ ] **Step 1: Add short README note**

State that cEOS is not on Docker Hub; use Images → Upload & load (or `docker load`) from an Arista archive; optional registry for multi-host.

- [ ] **Step 2: Run full relevant tests**

```bash
.venv/bin/python -m pytest tests/test_web_images.py tests/test_web_settings.py tests/test_web_ops.py -q
cd ui && npm run build
```

Expected: all pass / build ok

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
docs: note cEOS image load and Images page registry flow

EOF
)"
```

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Settings registry + token mask | 1 |
| Expose `CLAB_HOST_IMAGE` | 1, 6 |
| List images | 3, 6 |
| Upload & load, 10GB cap, archive suffixes | 2, 4, 6 |
| Optional name/tag after load | 4, 6 |
| Push/pull when registry set | 5, 6 |
| Jobs + log drawer | 4, 5, 6 |
| Use as CLAB_IMAGE / HOST_IMAGE | 6 |
| No auto-pull on deploy | (explicit non-goal; no task) |
| README | 7 |
| Redact token in logs | 2, 5 |

## Placeholder / consistency review

- Upload path uses `.acta-uploads` under labs root; remote uses `scp` (not base64) for large files.
- `registry_image_ref` treats `localhost/…` as short (still prefixable) so host multitool can be pushed as `hub…/acta-host-multitool:…` when the local name is `localhost/…` — **adjust in Task 2 if tests desire**: for push, strip `localhost/` before joining, or pass repository without localhost. Prefer: when joining, if image starts with `localhost/`, replace with `registry/` + remainder after `localhost/`.

Add to Task 2 helper:

```python
def registry_image_ref(registry: str, image: str) -> str:
    ...
    if img.startswith("localhost/"):
        img = img[len("localhost/") :]
    ...
```

Update unit test accordingly.

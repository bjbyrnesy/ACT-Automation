"""Lab-host image list / load / push / pull helpers for the Web UI."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from acta.clab.support import host_run, resolve_clab_runtime
from acta.web.errors import WebError

UPLOAD_MAX_BYTES = 10 * 1024**3
ALLOWED_ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".xz")


def assert_archive_name(filename: str) -> None:
    """Reject upload names that are not an allowed image archive suffix."""
    name = (filename or "").lower()
    if not any(name.endswith(suffix) for suffix in ALLOWED_ARCHIVE_SUFFIXES):
        raise WebError(
            400,
            "archive must be .tar, .tar.gz, .tgz, or .xz",
            fields={"file": "invalid"},
        )


# host[:port] then optional path segments (Docker repository path rules, loosely).
_REGISTRY_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?::[0-9]{1,5})?"
    r"(?:/[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)*"
)


def assert_registry(registry: str) -> str:
    """Return the normalized ``CLAB_REGISTRY`` or raise a 400 if it is unsafe."""
    reg = (registry or "").strip().rstrip("/")
    if not reg:
        raise WebError(
            400,
            "CLAB_REGISTRY is not set",
            fields={"CLAB_REGISTRY": "required"},
        )
    if reg.startswith("-") or not _REGISTRY_RE.fullmatch(reg):
        raise WebError(
            400,
            "CLAB_REGISTRY must be host[:port][/path]",
            fields={"CLAB_REGISTRY": "invalid"},
        )
    return reg


def _has_registry_host(image: str) -> bool:
    """Docker rule: the first path segment is a registry host when it contains
    ``.`` or ``:`` or is exactly ``localhost`` (and a path follows it)."""
    if "/" not in image:
        return False
    first = image.split("/", 1)[0]
    return "." in first or ":" in first or first == "localhost"


def registry_image_ref(registry: str, image: str) -> str:
    """Join a short image name onto the lab registry.

    A leading ``localhost/`` is stripped, then the remainder is joined onto
    the registry (``localhost/acta-host:tag`` becomes
    ``<registry>/acta-host:tag``). A ref whose first path segment is a
    registry host (has ``.`` or ``:``) is returned unchanged; namespaced
    short names such as ``acta/ceos:1`` get the registry prefix.
    """
    reg = assert_registry(registry)
    img = image.strip()
    stripped_localhost = img.startswith("localhost/")
    if stripped_localhost:
        img = img.removeprefix("localhost/")
    if not img:
        raise WebError(400, "image is required", fields={"image": "required"})
    if img.startswith(f"{reg}/"):
        return img
    if not stripped_localhost and _has_registry_host(img):
        return img
    return f"{reg}/{img}"


def redact_secrets(text: str, secrets: list[str]) -> str:
    """Replace each non-empty secret in ``text`` with ``****``."""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "****")
    return out


def _humanize_size(value: Any) -> str:
    """Render a byte count (podman emits an int) as ``299.3MB``; pass strings through."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value or "")
    size = float(value)
    if size < 1024:
        return f"{int(size)}B"
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024 or unit == "GB":
            return f"{size:.1f}{unit}"
    return f"{size:.1f}GB"  # unreachable; keeps type checkers happy


def _format_created(row: dict[str, Any]) -> str:
    """Prefer ``CreatedAt``; format an int/float ``Created`` unix epoch for display."""
    text = row.get("CreatedAt") or row.get("createdAt")
    if text:
        return str(text)
    created = row.get("Created") or row.get("created")
    if isinstance(created, (int, float)) and not isinstance(created, bool):
        try:
            return datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S")
        except OverflowError, OSError, ValueError:
            return str(created)
    return str(created or "")


def parse_images_json(raw: str) -> list[dict[str, str]]:
    """Parse ``docker/podman images --format json`` (array or NDJSON).

    Podman reports ``Size`` and ``Created`` as ints; they are rendered as a
    human size and a local timestamp. Raises ``json.JSONDecodeError`` on junk.
    """
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
                "size": _humanize_size(
                    row["Size"]
                    if row.get("Size") not in (None, "")
                    else row.get("size")
                ),
                "created": _format_created(row),
            }
        )
    return out


# Runtime strings: ``docker``/``podman``, or ``sudo-podman`` when the lab host
# deploys with ``sudo containerlab`` (root's podman store, not the user's).
_SUDO_RUNTIMES = frozenset({"sudo-podman"})

# ``$1`` is the runtime in every script below; ``rt`` runs it (with ``sudo -n``
# for ``sudo-podman``) so list/load/tag/push/pull/login share one store.
_RT_FUNC = """set -eu
runtime="$1"
rt() {
  case "$runtime" in
    sudo-podman) sudo -n podman "$@" ;;
    docker|podman) "$runtime" "$@" ;;
    *) echo "unsupported runtime: $runtime" >&2; return 2 ;;
  esac
}
"""

# One JSON object per line works on both docker and podman.
_LIST_IMAGES_SCRIPT = _RT_FUNC + """rt images --format '{{json .}}'
"""


def list_host_images(*, host: str | None, runtime: str | None) -> list[dict[str, str]]:
    """List container images on the lab host using its docker/podman runtime."""
    resolved = (
        runtime if runtime in _SUDO_RUNTIMES else resolve_clab_runtime(host, runtime)
    )
    result = host_run(host, _LIST_IMAGES_SCRIPT, [resolved], "")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise WebError(502, detail or f"{resolved} images failed")
    try:
        return parse_images_json(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise WebError(502, f"could not parse {resolved} images output: {exc}") from exc


# No ":" -- scp would read it as a host/path separator (or IPv6 literal).
_HOST_RE = re.compile(r"[A-Za-z0-9_.@-]+")
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_TAG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}")
_LOADED_RE = re.compile(r"^Loaded image(?:\(s\)| ID)?:\s*(.+)$", re.MULTILINE)

_LOAD_SCRIPT = _RT_FUNC + """rt load -i "$2"
"""
_TAG_SCRIPT = _RT_FUNC + """rt tag "$2" "$3"
"""
_RM_SCRIPT = """rm -f -- "$1"
"""


def assert_image_name_tag(name: str | None, tag: str | None) -> None:
    """Require ``name`` and ``tag`` together (or neither) and valid characters."""
    if bool(name) != bool(tag):
        raise WebError(
            400,
            "name and tag must be provided together",
            fields={"name": "required with tag", "tag": "required with name"},
        )
    if name and not _NAME_RE.fullmatch(name):
        raise WebError(400, "invalid image name", fields={"name": "invalid"})
    if tag and not _TAG_RE.fullmatch(tag):
        raise WebError(400, "invalid image tag", fields={"tag": "invalid"})


_IMAGE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*")


def assert_image_ref(image: str) -> None:
    """Reject empty or option-like image refs before they reach a shell script."""
    if not image or not _IMAGE_REF_RE.fullmatch(image):
        raise WebError(400, "invalid image reference", fields={"image": "invalid"})


def parse_loaded_refs(output: str) -> list[str]:
    """Extract image refs from ``docker/podman load`` output."""
    refs: list[str] = []
    for match in _LOADED_RE.finditer(output or ""):
        refs.extend(ref.strip() for ref in match.group(1).split(",") if ref.strip())
    return refs


def archive_suffix(filename: str) -> str:
    """Return the allowed archive suffix of ``filename`` (``.tar.gz`` aware)."""
    lowered = (filename or "").lower()
    for suffix in sorted(ALLOWED_ARCHIVE_SUFFIXES, key=len, reverse=True):
        if lowered.endswith(suffix):
            return suffix
    return ""


def _print_output(result: Any) -> None:
    for stream in (result.stdout, result.stderr):
        text = (stream or "").strip()
        if text:
            print(text, flush=True)


def assert_scp_host(host: str) -> None:
    """Allow SSH aliases and ``user@host``; reject ``:`` and option-like values."""
    if host.startswith("-") or not _HOST_RE.fullmatch(host):
        raise WebError(400, "Invalid SSH host; use an SSH alias or user@hostname.")


def _scp_to_host(host: str, archive_path: Path, remote_path: str) -> None:
    """Copy the archive to ``host`` with scp (never base64 for large files)."""
    assert_scp_host(host)
    result = subprocess.run(
        [
            "scp",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "--",
            str(archive_path),
            f"{host}:{remote_path}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise WebError(502, detail or "scp failed")


def _remove_remote(host: str | None, remote_path: str) -> None:
    """Best-effort remote cleanup; never raises (must not mask the real error)."""
    try:
        result = host_run(host, _RM_SCRIPT, [remote_path], "")
    except Exception as exc:  # noqa: BLE001 - cleanup must not mask the job error
        print(f"WARNING: failed to remove {host}:{remote_path}: {exc}", flush=True)
        return
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        print(
            f"WARNING: failed to remove {host}:{remote_path}: {detail or 'rm failed'}",
            flush=True,
        )


# The token arrives on stdin (``host_run`` ``data``) so it works over ssh too
# and never appears in argv or the environment.
_LOGIN_SCRIPT = _RT_FUNC + """server="$2"
user="$3"
rt login --username "$user" --password-stdin "$server"
"""
_PUSH_SCRIPT = _RT_FUNC + """rt push "$2"
"""
_PULL_SCRIPT = _RT_FUNC + """rt pull "$2"
"""


def _display(runtime: str) -> str:
    """Human form of a runtime string (``sudo-podman`` -> ``sudo podman``)."""
    return runtime.replace("sudo-", "sudo ", 1)


# Exit 0: ``sudo -n podman`` works; 3: already root; anything else: no sudo.
_SUDO_PROBE_SCRIPT = """set -eu
if [ "$(id -u)" -eq 0 ]; then exit 3; fi
exec sudo -n podman images >/dev/null
"""


def elevate_runtime(host: str | None, runtime: str) -> tuple[str, str]:
    """Match deploy's privilege (``sudo -n containerlab``) for rootless podman.

    Returns ``(runtime, warning)``. When ``runtime`` is ``podman``, the lab-host
    user is not root, and ``sudo -n podman`` works, returns ``sudo-podman`` so
    images land in the store ``sudo containerlab deploy`` reads. If sudo is
    unavailable, keeps rootless podman and returns a warning (deploy may not
    see the images). Never raises: probe failures only produce the warning.
    """
    if runtime != "podman":
        return runtime, ""
    try:
        result = host_run(host, _SUDO_PROBE_SCRIPT, [], "")
    except Exception as exc:  # noqa: BLE001 - best effort; must not block images
        return runtime, f"{_SUDO_WARNING} (probe failed: {exc})"
    if result.returncode == 3:
        return runtime, ""
    if result.returncode == 0:
        return "sudo-podman", ""
    return runtime, _SUDO_WARNING


_SUDO_WARNING = (
    "WARNING: 'sudo -n podman' is not available on the lab host; using rootless "
    "podman. If deploy runs 'sudo containerlab', images must also be in root's "
    "store (run 'sudo podman load' on the host)."
)


def _registry_server(registry: str) -> str:
    """Return the login server (host[:port]) of a registry path."""
    return registry.strip().rstrip("/").split("/", 1)[0]


def _run_step(
    *,
    host: str | None,
    script: str,
    args: list[str],
    data: str,
    label: str,
    secrets: list[str],
) -> None:
    """Run one host script; print redacted output; raise a redacted 502 on failure."""
    result = host_run(host, script, args, data)
    for stream in (result.stdout, result.stderr):
        text = redact_secrets((stream or "").strip(), secrets)
        if text:
            print(text, flush=True)
    if result.returncode != 0:
        detail = redact_secrets((result.stderr or result.stdout or "").strip(), secrets)
        raise WebError(502, detail or f"{label} failed")


def _registry_login(
    *,
    host: str | None,
    runtime: str,
    registry: str,
    user: str,
    token: str,
) -> None:
    """Log in when both ``user`` and ``token`` are set; otherwise rely on existing auth."""
    if not (user and token):
        return
    server = _registry_server(registry)
    print(f"{_display(runtime)} login {server}", flush=True)
    _run_step(
        host=host,
        script=_LOGIN_SCRIPT,
        args=[runtime, server, user],
        data=token,
        label=f"{_display(runtime)} login",
        secrets=[token],
    )


def push_image(
    *,
    host: str | None,
    runtime: str,
    image: str,
    registry: str,
    user: str,
    token: str,
) -> None:
    """Log in, tag ``image`` into the lab registry, and push it."""
    ref = registry_image_ref(registry, image)
    secrets = [token]
    _registry_login(
        host=host, runtime=runtime, registry=registry, user=user, token=token
    )
    print(f"{_display(runtime)} tag {image} {ref}", flush=True)
    _run_step(
        host=host,
        script=_TAG_SCRIPT,
        args=[runtime, image, ref],
        data="",
        label=f"{_display(runtime)} tag",
        secrets=secrets,
    )
    print(f"{_display(runtime)} push {ref}", flush=True)
    _run_step(
        host=host,
        script=_PUSH_SCRIPT,
        args=[runtime, ref],
        data="",
        label=f"{_display(runtime)} push",
        secrets=secrets,
    )


def pull_image(
    *,
    host: str | None,
    runtime: str,
    image: str,
    registry: str,
    user: str,
    token: str,
) -> None:
    """Log in and pull the registry copy of ``image`` onto the lab host."""
    ref = registry_image_ref(registry, image)
    _registry_login(
        host=host, runtime=runtime, registry=registry, user=user, token=token
    )
    print(f"{_display(runtime)} pull {ref}", flush=True)
    _run_step(
        host=host,
        script=_PULL_SCRIPT,
        args=[runtime, ref],
        data="",
        label=f"{_display(runtime)} pull",
        secrets=[token],
    )


def load_archive_on_host(
    *,
    host: str | None,
    runtime: str,
    archive_path: Path,
    name: str | None,
    tag: str | None,
) -> None:
    """``docker|podman load`` an archive on the lab host, then optionally tag it.

    Remote hosts get the archive via ``scp`` to a temp path that is always
    removed afterwards. Progress is printed to stdout for the job log. The
    caller owns deleting ``archive_path``.
    """
    assert_image_name_tag(name, tag)
    load_path = str(archive_path)
    remote_path: str | None = None
    if host:
        remote_path = (
            f"/tmp/acta-upload-{uuid.uuid4().hex}{archive_suffix(archive_path.name)}"
        )
        load_path = remote_path
    try:
        if remote_path:
            print(f"Copying {archive_path.name} to {host}:{remote_path}", flush=True)
            _scp_to_host(str(host), archive_path, remote_path)
        print(f"{_display(runtime)} load -i {archive_path.name}", flush=True)
        result = host_run(host, _LOAD_SCRIPT, [runtime, load_path], "")
        _print_output(result)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise WebError(502, detail or f"{_display(runtime)} load failed")
        if name and tag:
            refs = parse_loaded_refs(result.stdout or "")
            if not refs:
                raise WebError(502, "could not determine loaded image to tag")
            target = f"{name}:{tag}"
            tagged = host_run(host, _TAG_SCRIPT, [runtime, refs[0], target], "")
            if tagged.returncode != 0:
                detail = (tagged.stderr or tagged.stdout or "").strip()
                raise WebError(502, detail or f"{_display(runtime)} tag failed")
            print(f"Tagged {refs[0]} as {target}", flush=True)
    finally:
        if remote_path:
            _remove_remote(host, remote_path)

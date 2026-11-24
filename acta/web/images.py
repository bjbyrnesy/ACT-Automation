"""Lab-host image list / load / push / pull helpers for the Web UI."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
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


def registry_image_ref(registry: str, image: str) -> str:
    """Join a short image name onto the lab registry.

    A leading ``localhost/`` is stripped, then the remainder is joined onto
    the registry (``localhost/acta-host:tag`` becomes
    ``<registry>/acta-host:tag``). A non-localhost ref that already names a
    registry path is returned unchanged.
    """
    reg = registry.strip().rstrip("/")
    img = image.strip()
    if not reg:
        raise WebError(
            400,
            "CLAB_REGISTRY is not set",
            fields={"CLAB_REGISTRY": "required"},
        )
    stripped_localhost = img.startswith("localhost/")
    if stripped_localhost:
        img = img.removeprefix("localhost/")
    if not img:
        raise WebError(400, "image is required", fields={"image": "required"})
    if img.startswith(f"{reg}/"):
        return img
    # Fully-qualified elsewhere: a slash in the name before the tag.
    # localhost names stay short so the registry prefix is still applied.
    if "/" in img.split(":")[0] and not stripped_localhost:
        return img
    return f"{reg}/{img}"


def redact_secrets(text: str, secrets: list[str]) -> str:
    """Replace each non-empty secret in ``text`` with ``****``."""
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


# One JSON object per line works on both docker and podman.
_LIST_IMAGES_SCRIPT = """set -eu
runtime="$1"
exec "$runtime" images --format '{{json .}}'
"""


def list_host_images(*, host: str | None, runtime: str | None) -> list[dict[str, str]]:
    """List container images on the lab host using its docker/podman runtime."""
    resolved = resolve_clab_runtime(host, runtime)
    result = host_run(host, _LIST_IMAGES_SCRIPT, [resolved], "")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise WebError(502, detail or f"{resolved} images failed")
    return parse_images_json(result.stdout or "")


_HOST_RE = re.compile(r"[A-Za-z0-9_.@:-]+")
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_TAG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}")
_LOADED_RE = re.compile(r"^Loaded image(?:\(s\)| ID)?:\s*(.+)$", re.MULTILINE)

_LOAD_SCRIPT = """set -eu
runtime="$1"
exec "$runtime" load -i "$2"
"""
_TAG_SCRIPT = """set -eu
exec "$1" tag "$2" "$3"
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


def _scp_to_host(host: str, archive_path: Path, remote_path: str) -> None:
    """Copy the archive to ``host`` with scp (never base64 for large files)."""
    if host.startswith("-") or not _HOST_RE.fullmatch(host):
        raise WebError(400, "Invalid SSH host; use an SSH alias or user@hostname.")
    result = subprocess.run(
        [
            "scp",
            "-o",
            "BatchMode=yes",
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
        print(f"{runtime} load -i {archive_path.name}", flush=True)
        result = host_run(host, _LOAD_SCRIPT, [runtime, load_path], "")
        _print_output(result)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise WebError(502, detail or f"{runtime} load failed")
        if name and tag:
            refs = parse_loaded_refs(result.stdout or "")
            if not refs:
                raise WebError(502, "could not determine loaded image to tag")
            target = f"{name}:{tag}"
            tagged = host_run(host, _TAG_SCRIPT, [runtime, refs[0], target], "")
            if tagged.returncode != 0:
                detail = (tagged.stderr or tagged.stdout or "").strip()
                raise WebError(502, detail or f"{runtime} tag failed")
            print(f"Tagged {refs[0]} as {target}", flush=True)
    finally:
        if remote_path:
            host_run(host, _RM_SCRIPT, [remote_path], "")

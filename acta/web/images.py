"""Lab-host image list / load / push / pull helpers for the Web UI."""

from __future__ import annotations

import json
from typing import Any

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

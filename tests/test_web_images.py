"""Unit tests for Web UI image ref, redact, and archive helpers."""

from __future__ import annotations

import pytest

from acta.web.errors import WebError
from acta.web.images import (
    ALLOWED_ARCHIVE_SUFFIXES,
    UPLOAD_MAX_BYTES,
    assert_archive_name,
    parse_images_json,
    redact_secrets,
    registry_image_ref,
)


def test_upload_max_is_10gib() -> None:
    assert UPLOAD_MAX_BYTES == 10 * 1024**3


def test_registry_image_ref_joins_short_name() -> None:
    assert (
        registry_image_ref("hub.freeblizz.com/acta", "ceos:4.37.0F")
        == "hub.freeblizz.com/acta/ceos:4.37.0F"
    )


def test_registry_image_ref_keeps_fully_qualified() -> None:
    full = "hub.freeblizz.com/acta/ceos:4.37.0F"
    assert registry_image_ref("hub.freeblizz.com/acta", full) == full


def test_registry_image_ref_strips_trailing_slash() -> None:
    assert (
        registry_image_ref("hub.freeblizz.com/acta/", "ceos:1")
        == "hub.freeblizz.com/acta/ceos:1"
    )


def test_registry_image_ref_strips_localhost_prefix() -> None:
    assert (
        registry_image_ref("hub.freeblizz.com/acta", "localhost/acta-host:tag")
        == "hub.freeblizz.com/acta/acta-host:tag"
    )


def test_registry_image_ref_prefixes_localhost_with_path() -> None:
    assert (
        registry_image_ref("hub.freeblizz.com/acta", "localhost/org/acta-host:tag")
        == "hub.freeblizz.com/acta/org/acta-host:tag"
    )


def test_redact_secrets_replaces_token() -> None:
    assert redact_secrets("login s3cret ok", ["s3cret"]) == "login **** ok"


def test_parse_images_json_rows() -> None:
    raw = '[{"Repository":"ceos","Tag":"4.37.0F","Id":"abc","Size":"2GB","CreatedAt":"2026"}]\n'
    rows = parse_images_json(raw)
    assert rows[0]["repository"] == "ceos"
    assert rows[0]["tag"] == "4.37.0F"


def test_assert_archive_name_rejects_bad_suffix() -> None:
    with pytest.raises(WebError) as ei:
        assert_archive_name("evil.exe")
    assert ei.value.status_code == 400


def test_allowed_archive_suffixes() -> None:
    assert ALLOWED_ARCHIVE_SUFFIXES == (".tar", ".tar.gz", ".tgz", ".xz")

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


def test_list_host_images_uses_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from acta.web import images as img

    calls: list[tuple[str | None, list[str]]] = []

    class _Result:
        returncode = 0
        stdout = '{"Repository":"ceos","Tag":"4.37.0F","Id":"deadbeef","Size":"1","CreatedAt":"x"}\n'
        stderr = ""

    def fake_host_run(host, script, args, data):  # type: ignore[no-untyped-def]
        calls.append((host, args))
        return _Result()

    monkeypatch.setattr(img, "host_run", fake_host_run)
    monkeypatch.setattr(
        img, "resolve_clab_runtime", lambda host, preferred=None: "docker"
    )
    rows = img.list_host_images(host=None, runtime="docker")
    assert rows[0]["repository"] == "ceos"
    assert calls and calls[0][1][0] == "docker"


def test_list_host_images_resolves_runtime_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from acta.web import images as img

    seen: list[str] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_host_run(host, script, args, data):  # type: ignore[no-untyped-def]
        seen.append(args[0])
        return _Result()

    monkeypatch.setattr(img, "host_run", fake_host_run)
    monkeypatch.setattr(
        img, "resolve_clab_runtime", lambda host, preferred=None: "podman"
    )
    assert img.list_host_images(host="lab1", runtime=None) == []
    assert seen == ["podman"]


def test_list_host_images_nonzero_raises_502(monkeypatch: pytest.MonkeyPatch) -> None:
    from acta.web import images as img

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "permission denied"

    monkeypatch.setattr(img, "host_run", lambda host, script, args, data: _Result())
    with pytest.raises(WebError) as ei:
        img.list_host_images(host=None, runtime="docker")
    assert ei.value.status_code == 502
    assert "permission denied" in ei.value.detail


@pytest.fixture
def client(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from acta.web.app import create_app

    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(labs_root=tmp_path))


def test_get_api_images(client, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    seen: dict[str, object] = {}

    def fake_list(**kw: object) -> list[dict[str, str]]:
        seen.update(kw)
        return [
            {"repository": "ceos", "tag": "1", "id": "abc", "size": "1", "created": ""}
        ]

    monkeypatch.setattr(img, "list_host_images", fake_list)
    monkeypatch.setattr(
        img, "resolve_clab_runtime", lambda host, preferred=None: "docker"
    )
    response = client.get("/api/images")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["images"][0]["repository"] == "ceos"
    assert body["runtime"] == "docker"
    assert body["host"] == ""
    assert seen == {"host": None, "runtime": "docker"}

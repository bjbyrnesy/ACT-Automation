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


class _Proc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_parse_loaded_refs() -> None:
    from acta.web.images import parse_loaded_refs

    out = "Loaded image: ceos:4.37.0F\nLoaded image(s): a:1, b:2\nLoaded image ID: sha256:abc\n"
    assert parse_loaded_refs(out) == ["ceos:4.37.0F", "a:1", "b:2", "sha256:abc"]
    assert parse_loaded_refs("nothing here") == []


def test_assert_image_name_tag_rejects_bad_values() -> None:
    from acta.web.images import assert_image_name_tag

    assert_image_name_tag(None, None)
    assert_image_name_tag("ceos", "4.37.0F")
    for name, tag in (("ceos", None), (None, "1"), ("bad name", "1"), ("ceos", "a b")):
        with pytest.raises(WebError) as ei:
            assert_image_name_tag(name, tag)
        assert ei.value.status_code == 400


def test_load_archive_local_runs_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    archive = tmp_path / "ceos.tar"
    archive.write_bytes(b"x")
    calls: list[tuple[str | None, list[str]]] = []

    def fake_host_run(host, script, args, data):  # type: ignore[no-untyped-def]
        calls.append((host, args))
        return _Proc(stdout="Loaded image: ceos:4.37.0F\n")

    monkeypatch.setattr(img, "host_run", fake_host_run)
    img.load_archive_on_host(
        host=None, runtime="docker", archive_path=archive, name=None, tag=None
    )
    assert calls == [(None, ["docker", str(archive)])]
    assert "load" in img._LOAD_SCRIPT
    assert "Loaded image: ceos:4.37.0F" in capsys.readouterr().out


def test_load_archive_tags_first_loaded_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    archive = tmp_path / "ceos.tar"
    archive.write_bytes(b"x")
    calls: list[list[str]] = []

    def fake_host_run(host, script, args, data):  # type: ignore[no-untyped-def]
        calls.append(args)
        return _Proc(stdout="Loaded image: localhost/ceos:old\n")

    monkeypatch.setattr(img, "host_run", fake_host_run)
    img.load_archive_on_host(
        host=None, runtime="podman", archive_path=archive, name="ceos", tag="4.37.0F"
    )
    assert calls[1] == ["podman", "localhost/ceos:old", "ceos:4.37.0F"]


def test_load_archive_failure_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    archive = tmp_path / "ceos.tar"
    archive.write_bytes(b"x")
    monkeypatch.setattr(
        img, "host_run", lambda *a: _Proc(returncode=1, stderr="bad archive")
    )
    with pytest.raises(WebError) as ei:
        img.load_archive_on_host(
            host=None, runtime="docker", archive_path=archive, name=None, tag=None
        )
    assert ei.value.status_code == 502
    assert "bad archive" in ei.value.detail


def test_load_archive_tag_without_loaded_ref_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    archive = tmp_path / "ceos.tar"
    archive.write_bytes(b"x")
    monkeypatch.setattr(img, "host_run", lambda *a: _Proc(stdout="ok\n"))
    with pytest.raises(WebError):
        img.load_archive_on_host(
            host=None, runtime="docker", archive_path=archive, name="a", tag="b"
        )


def test_load_archive_remote_uses_scp_and_cleans_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    archive = tmp_path / "ceos.tar.gz"
    archive.write_bytes(b"x")
    scp_calls: list[list[str]] = []
    runs: list[tuple[str | None, str, list[str]]] = []

    def fake_scp(cmd, **kw):  # type: ignore[no-untyped-def]
        scp_calls.append(cmd)
        return _Proc()

    def fake_host_run(host, script, args, data):  # type: ignore[no-untyped-def]
        runs.append((host, script, args))
        return _Proc(stdout="Loaded image: ceos:1\n")

    monkeypatch.setattr(img.subprocess, "run", fake_scp)
    monkeypatch.setattr(img, "host_run", fake_host_run)
    img.load_archive_on_host(
        host="lab1", runtime="docker", archive_path=archive, name=None, tag=None
    )
    assert scp_calls[0][0] == "scp"
    dest = scp_calls[0][-1]
    assert dest.startswith("lab1:/tmp/acta-upload-") and dest.endswith(".tar.gz")
    remote = dest.split(":", 1)[1]
    assert runs[0][0] == "lab1" and runs[0][2] == ["docker", remote]
    assert runs[-1][2] == [remote] and "rm" in runs[-1][1]


def test_load_archive_remote_cleans_remote_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    archive = tmp_path / "ceos.tar"
    archive.write_bytes(b"x")
    runs: list[list[str]] = []

    def fake_host_run(host, script, args, data):  # type: ignore[no-untyped-def]
        runs.append(args)
        return _Proc(returncode=1, stderr="boom") if len(runs) == 1 else _Proc()

    monkeypatch.setattr(img.subprocess, "run", lambda *a, **k: _Proc())
    monkeypatch.setattr(img, "host_run", fake_host_run)
    with pytest.raises(WebError):
        img.load_archive_on_host(
            host="lab1", runtime="docker", archive_path=archive, name=None, tag=None
        )
    assert len(runs) == 2 and len(runs[1]) == 1


def test_load_archive_scp_failure_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from acta.web import images as img

    archive = tmp_path / "ceos.tar"
    archive.write_bytes(b"x")
    monkeypatch.setattr(
        img.subprocess, "run", lambda *a, **k: _Proc(returncode=1, stderr="no route")
    )
    monkeypatch.setattr(img, "host_run", lambda *a: _Proc())
    with pytest.raises(WebError) as ei:
        img.load_archive_on_host(
            host="lab1", runtime="docker", archive_path=archive, name=None, tag=None
        )
    assert ei.value.status_code == 502


def _wait_job(job_id: str):  # type: ignore[no-untyped-def]
    import time

    from acta.web.jobs import get_job

    for _ in range(200):
        job = get_job(job_id)
        if job.status in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from acta.web import images as img

    monkeypatch.setattr(
        img, "resolve_clab_runtime", lambda host, preferred=None: "docker"
    )


def test_reject_oversized_upload_header(client, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from acta.web.images import UPLOAD_MAX_BYTES

    _patch_runtime(monkeypatch)
    r = client.post(
        "/api/jobs/images/load",
        files={"file": ("ceos.tar", b"x", "application/x-tar")},
        headers={"Content-Length": str(UPLOAD_MAX_BYTES + 1)},
    )
    assert r.status_code == 400
    assert not list((tmp_path / ".acta-uploads").glob("*"))


def test_reject_oversized_upload_streaming(client, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from acta.web import routes_images

    _patch_runtime(monkeypatch)
    monkeypatch.setattr(routes_images.images, "UPLOAD_MAX_BYTES", 10)
    r = client.post(
        "/api/jobs/images/load",
        files={"file": ("ceos.tar", b"x" * 64, "application/x-tar")},
    )
    assert r.status_code == 400
    assert not list((tmp_path / ".acta-uploads").glob("*"))


def test_load_rejects_bad_suffix(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_runtime(monkeypatch)
    r = client.post(
        "/api/jobs/images/load", files={"file": ("evil.exe", b"x", "text/plain")}
    )
    assert r.status_code == 400


def test_load_rejects_name_without_tag(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_runtime(monkeypatch)
    r = client.post(
        "/api/jobs/images/load",
        files={"file": ("ceos.tar", b"x", "application/x-tar")},
        data={"name": "ceos"},
    )
    assert r.status_code == 400


def test_load_job_calls_load(monkeypatch, client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _patch_runtime(monkeypatch)
    seen: dict[str, object] = {}

    def fake_load(**kwargs: object) -> None:
        seen.update(kwargs)
        path = kwargs["archive_path"]
        seen["existed"] = path.exists()  # type: ignore[attr-defined]
        seen["data"] = path.read_bytes()  # type: ignore[attr-defined]
        print("Loaded ceos:4.37.0F")

    monkeypatch.setattr("acta.web.images.load_archive_on_host", fake_load)
    data = b"not-a-real-tar-but-ok-for-route"
    r = client.post(
        "/api/jobs/images/load",
        files={"file": ("ceos.tar", data, "application/x-tar")},
        data={"name": "ceos", "tag": "4.37.0F"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "images.load"
    job = _wait_job(r.json()["id"])
    assert job.status == "succeeded", job.log
    assert "Loaded ceos:4.37.0F" in job.log
    assert seen["name"] == "ceos" and seen["tag"] == "4.37.0F"
    assert seen["host"] is None and seen["runtime"] == "docker"
    assert seen["data"] == data
    archive = seen["archive_path"]
    assert archive.parent == tmp_path / ".acta-uploads"  # type: ignore[attr-defined]
    assert archive.name.endswith(".tar")  # type: ignore[attr-defined]
    assert not archive.exists()  # type: ignore[attr-defined]


def test_load_job_deletes_archive_on_failure(monkeypatch, client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _patch_runtime(monkeypatch)
    seen: dict[str, object] = {}

    def fake_load(**kwargs: object) -> None:
        seen.update(kwargs)
        raise WebError(502, "load failed")

    monkeypatch.setattr("acta.web.images.load_archive_on_host", fake_load)
    r = client.post(
        "/api/jobs/images/load",
        files={"file": ("ceos.tgz", b"x", "application/gzip")},
    )
    job = _wait_job(r.json()["id"])
    assert job.status == "failed"
    assert "load failed" in job.log
    assert not seen["archive_path"].exists()  # type: ignore[attr-defined]
    assert seen["archive_path"].name.endswith(".tgz")  # type: ignore[attr-defined]

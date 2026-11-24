"""Tests for the Web UI ops façade and its job routes."""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from acta.web import ops
from acta.web.app import create_app
from acta.web.errors import WebError
from acta.web.jobs import get_job


def _preview_payload() -> dict[str, Any]:
    return {
        "hostname_prefix": "demo",
        "serial_prefix": "DEMO",
        "eos_version": "4.35.4M",
        "capacity": {
            "fabric_mode": "l3ls",
            "max_spines": 2,
            "max_leaves": 4,
            "max_mleafs_per_pair": 0,
            "spines": 2,
            "leaves": 2,
        },
        "mlag_pairs": True,
        "spine_mlag": False,
        "member_leaf_pairs": [],
        "member_leaves_per_pair": 0,
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # clab helpers read ./.config; keep them away from the real project config.
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(labs_root=tmp_path))


@pytest.fixture
def act_file(client: TestClient, tmp_path: Path) -> Path:
    preview = client.post("/api/preview", json=_preview_payload())
    assert preview.status_code == 200, preview.text
    written = client.post(
        "/api/topologies",
        json={"yaml_text": preview.json()["yaml_text"], "stem": "demo"},
    )
    assert written.status_code == 200, written.text
    return Path(written.json()["path"])


def _patch_clab(monkeypatch: pytest.MonkeyPatch, module: str, fn: Any) -> None:
    # ``acta.clab`` re-exports functions that shadow submodule attributes.
    target = importlib.import_module(f"acta.clab.{module}")
    monkeypatch.setattr(target, module, fn)


def _wait(job_id: str) -> Any:
    for _ in range(200):
        job = get_job(job_id)
        if job.status in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# --- require_written_path -------------------------------------------------


def test_require_written_path_none() -> None:
    with pytest.raises(WebError) as exc:
        ops.require_written_path(None)
    assert exc.value.status_code == 400


def test_require_written_path_missing(tmp_path: Path) -> None:
    with pytest.raises(WebError) as exc:
        ops.require_written_path(tmp_path / "nope.yml")
    assert exc.value.status_code == 400


def test_require_written_path_ok(tmp_path: Path) -> None:
    target = tmp_path / "a.yml"
    target.write_text("x")
    assert ops.require_written_path(target) == target


# --- real-code paths ------------------------------------------------------


def test_op_clab_generate_real(act_file: Path) -> None:
    out = ops.op_clab_generate(act_file, name="demo", image="ceos:4.35.4M")
    assert out == act_file.with_name(f"{act_file.stem}.clab.yml")
    assert "demo-spine1" in out.read_text()


def test_op_extend_real_returns_new_dated_path(act_file: Path) -> None:
    original = act_file.read_text()
    new = ops.op_extend(act_file, add="leaf", count=1)
    assert new != act_file
    assert new.is_file()
    assert "leaf3" in new.read_text()
    assert act_file.read_text() == original


def test_op_extend_requires_add(act_file: Path) -> None:
    with pytest.raises(WebError) as exc:
        ops.op_extend(act_file)
    assert exc.value.status_code == 400


def test_op_attach_real(act_file: Path) -> None:
    result = ops.op_attach(act_file, host="h1", to=["demo-leaf1"])
    assert result == act_file
    assert "h1" in act_file.read_text()


def test_op_detach_real(act_file: Path) -> None:
    ops.op_attach(act_file, host="h1", to=["demo-leaf1"])
    result = ops.op_detach(act_file, host="h1")
    assert result == act_file
    assert "h1:" not in act_file.read_text()


# --- mocked deploy-class ops ----------------------------------------------


def test_op_clab_deploy_delegates(
    act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    _patch_clab(monkeypatch, "deploy", lambda args: seen.update(vars(args)))
    ops.op_clab_deploy(act_file, host="lab1", runtime="docker")
    assert seen["host"] == "lab1"
    assert seen["runtime"] == "docker"
    assert seen["topology"] == str(act_file)


def test_op_clab_onboard_auto_confirms(
    act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers: list[str] = []

    def fake_onboard(args: Any) -> None:
        answers.append(input("Continue? [y/N] "))
        with pytest.raises(ValueError):
            input("CVaaS host: ")

    _patch_clab(monkeypatch, "onboard", fake_onboard)
    ops.op_clab_onboard(act_file)
    assert answers == ["y"]


def test_op_clab_deploy_missing_path(tmp_path: Path) -> None:
    with pytest.raises(WebError) as exc:
        ops.op_clab_deploy(tmp_path / "missing.clab.yml")
    assert exc.value.status_code == 400


def test_op_act_upload_delegates(
    act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, bool | None]] = []
    monkeypatch.setattr(
        "acta.upload.run_upload",
        lambda topology, *, deploy=None, tenant=None, **_: calls.append(
            (topology, deploy)
        ),
    )
    ops.op_act_upload(act_file, deploy=True)
    assert calls == [(act_file, True)]


def test_op_act_onboard_requires_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in ("ACT_USER", "ACT_API_KEY", "CVAAS_HOST", "CVAAS_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("acta.upload.PROJECT_DIR", tmp_path)
    with pytest.raises(ValueError, match="ACT_USER"):
        ops.op_act_onboard()


# --- routes ---------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "/api/jobs/clab/generate",
        "/api/jobs/clab/deploy",
        "/api/jobs/clab/destroy",
        "/api/jobs/clab/redeploy",
        "/api/jobs/clab/onboard",
        "/api/jobs/act/upload",
        "/api/extend",
        "/api/attach",
        "/api/detach",
    ],
)
def test_routes_missing_path_is_400(client: TestClient, url: str) -> None:
    assert client.post(url, json={}).status_code == 400
    assert client.post(url, json={"path": "nope.yml"}).status_code == 400


def test_route_rejects_path_outside_labs_root(client: TestClient) -> None:
    response = client.post("/api/extend", json={"path": "/etc/hosts", "add": "leaf"})
    assert response.status_code == 400


def test_route_clab_generate_job(client: TestClient, act_file: Path) -> None:
    response = client.post(
        "/api/jobs/clab/generate",
        json={"path": str(act_file), "name": "demo", "image": "ceos:4.35.4M"},
    )
    assert response.status_code == 200, response.text
    job = _wait(response.json()["id"])
    assert job.status == "succeeded", job.log
    assert act_file.with_name(f"{act_file.stem}.clab.yml").is_file()


def test_route_deploy_job_mocked(
    client: TestClient, act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        ops, "op_clab_deploy", lambda path, **kw: seen.update(path=path, **kw)
    )
    response = client.post(
        "/api/jobs/clab/deploy",
        json={
            "path": act_file.name,
            "host": "lab1",
            "runtime": "docker",
            "from_act": True,
        },
    )
    assert response.status_code == 200
    assert _wait(response.json()["id"]).status == "succeeded"
    assert seen == {
        "path": act_file,
        "host": "lab1",
        "runtime": "docker",
        "from_act": True,
    }


def test_route_deploy_uses_settings_runtime(
    client: TestClient, act_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from acta.config import save_config

    save_config(tmp_path / ".config", {"CLAB_RUNTIME": "docker"})
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        ops, "op_clab_deploy", lambda path, **kw: seen.update(path=path, **kw)
    )
    response = client.post(
        "/api/jobs/clab/deploy",
        json={"path": act_file.name, "from_act": True},
    )
    assert response.status_code == 200
    assert _wait(response.json()["id"]).status == "succeeded"
    assert seen["runtime"] == "docker"
    assert seen["from_act"] is True


def test_route_generate_uses_settings_images(
    client: TestClient, act_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Labs .config CLAB_IMAGE / CLAB_HOST_IMAGE must reach generate, not cwd .config."""
    from acta.config import save_config

    save_config(
        tmp_path / ".config",
        {
            "CLAB_IMAGE": "hub.freeblizz.com/ceosimage:4.37.0F",
            "CLAB_HOST_IMAGE": "localhost/acta-host-multitool:v0.10.0-mcast0.2.3",
        },
    )
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        ops, "op_clab_generate", lambda path, **kw: seen.update(path=path, **kw) or path
    )
    response = client.post(
        "/api/jobs/clab/generate",
        json={"path": act_file.name, "from_act": True},
    )
    assert response.status_code == 200
    assert _wait(response.json()["id"]).status == "succeeded"
    assert seen["image"] == "hub.freeblizz.com/ceosimage:4.37.0F"
    assert seen["host_image"] == "localhost/acta-host-multitool:v0.10.0-mcast0.2.3"


def test_route_deploy_uses_clab_runtime_env(
    client: TestClient, act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty labs .config still picks systemd Environment=CLAB_RUNTIME."""
    monkeypatch.setenv("CLAB_RUNTIME", "docker")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        ops, "op_clab_deploy", lambda path, **kw: seen.update(path=path, **kw)
    )
    response = client.post(
        "/api/jobs/clab/deploy",
        json={"path": act_file.name, "from_act": True},
    )
    assert response.status_code == 200
    assert _wait(response.json()["id"]).status == "succeeded"
    assert seen["runtime"] == "docker"


def test_op_clab_deploy_passes_none_runtime_through(
    act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Web ops must not force podman before deploy's auto-detect runs."""
    monkeypatch.delenv("CLAB_RUNTIME", raising=False)
    seen: dict[str, Any] = {}
    _patch_clab(monkeypatch, "deploy", lambda args: seen.update(vars(args)))
    ops.op_clab_deploy(act_file, host="lab1", runtime=None)
    assert seen["host"] == "lab1"
    assert seen.get("runtime") in (None, "")


def test_op_clab_deploy_honors_clab_runtime_env(
    act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """systemd Environment=CLAB_RUNTIME must reach deploy without a .config entry."""
    monkeypatch.setenv("CLAB_RUNTIME", "docker")
    seen: dict[str, Any] = {}
    _patch_clab(monkeypatch, "deploy", lambda args: seen.update(vars(args)))
    ops.op_clab_deploy(act_file, host="lab1")
    assert seen["runtime"] == "docker"


def test_route_job_failure_recorded(
    client: TestClient, act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(path: Path, **kw: Any) -> None:
        raise ValueError("deploy exploded")

    monkeypatch.setattr(ops, "op_clab_destroy", boom)
    response = client.post("/api/jobs/clab/destroy", json={"path": str(act_file)})
    job = _wait(response.json()["id"])
    assert job.status == "failed"
    assert "deploy exploded" in job.log


def test_route_act_upload_and_onboard_mocked(
    client: TestClient, act_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads: list[bool] = []
    monkeypatch.setattr(
        ops, "op_act_upload", lambda path, *, deploy=False, **kw: uploads.append(deploy)
    )
    onboards: list[dict[str, Any]] = []
    monkeypatch.setattr(ops, "op_act_onboard", lambda **kw: onboards.append(kw))

    up = client.post(
        "/api/jobs/act/upload", json={"path": str(act_file), "deploy": True}
    )
    assert _wait(up.json()["id"]).status == "succeeded"
    assert uploads == [True]

    on = client.post("/api/jobs/act/onboard", json={"tenant": "ce"})
    assert _wait(on.json()["id"]).status == "succeeded"
    assert onboards == [{"tenant": "ce"}]


def test_route_extend_sync(client: TestClient, act_file: Path) -> None:
    response = client.post(
        "/api/extend", json={"path": str(act_file), "add": "leaf", "count": 1}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == Path(body["path"]).name
    assert Path(body["path"]).is_file()
    assert body["path"] != str(act_file)


def test_route_extend_domain_error_is_400(client: TestClient, act_file: Path) -> None:
    response = client.post(
        "/api/extend", json={"path": str(act_file), "add": "leaf", "site": "A"}
    )
    assert response.status_code == 400


def test_route_attach_sync(client: TestClient, act_file: Path) -> None:
    response = client.post(
        "/api/attach",
        json={"path": str(act_file), "host": "h1", "to": ["demo-leaf1"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == act_file.name
    assert "h1" in act_file.read_text()


def test_route_attach_host_net(client: TestClient, act_file: Path) -> None:
    ops.op_clab_generate(act_file, name="demo", image="ceos:4.35.4M")
    response = client.post(
        "/api/attach",
        json={
            "path": str(act_file),
            "host": "h1",
            "to": ["demo-leaf1"],
            "host_net": True,
            "host_ip": "192.168.2.50",
            "host_subnet": "192.168.2.0/24",
            "host_gateway": "192.168.2.1",
        },
    )
    assert response.status_code == 200, response.text
    clab = act_file.with_name(f"{act_file.stem}.clab.yml").read_text()
    assert "192.168.2.50" in clab
    assert "192.168.2.1" in clab


def test_op_attach_host_net_passthrough(act_file: Path) -> None:
    ops.op_clab_generate(act_file, name="demo", image="ceos:4.35.4M")
    ops.op_attach(act_file, host="h1", to=["demo-leaf1"], host_net=True)
    clab = act_file.with_name(f"{act_file.stem}.clab.yml").read_text()
    assert "192.168.2.2" in clab


def test_route_attach_host_net_returns_assigned_ip(
    client: TestClient, act_file: Path
) -> None:
    ops.op_clab_generate(act_file, name="demo", image="ceos:4.35.4M")
    response = client.post(
        "/api/attach",
        json={
            "path": str(act_file),
            "host": "h1",
            "to": ["demo-leaf1"],
            "host_net": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["host_net_ip"] == "192.168.2.2/24"
    assert body["host_net_iface"] == "eth1"


def test_route_attach_host_net_without_sibling_is_400(
    client: TestClient, act_file: Path
) -> None:
    original = act_file.read_text()
    response = client.post(
        "/api/attach",
        json={
            "path": str(act_file),
            "host": "h1",
            "to": ["demo-leaf1"],
            "host_net": True,
        },
    )
    assert response.status_code == 400
    assert "sibling .clab.yml" in response.text
    assert act_file.read_text() == original


def test_regenerate_preserves_host_net(act_file: Path) -> None:
    import yaml

    from acta.attach import attach_host_act

    clab = ops.op_clab_generate(act_file, name="demo", image="ceos:4.35.4M")
    attach_host_act(
        act_file, "h1", to=["demo-leaf1"], host_net=True, host_ip="192.168.2.77"
    )
    artifacts = act_file.with_name(f"{act_file.stem}.host-net") / "h1"
    (artifacts / "bootstrap.sh").unlink()

    ops.op_clab_generate(act_file, name="demo", image="ceos:4.35.4M")

    node = yaml.safe_load(clab.read_text())["topology"]["nodes"]["h1"]
    assert node["labels"]["acta.host-net"] in ("true", True)
    assert node["labels"]["acta.host-ip"] == "192.168.2.77"
    assert node["exec"][-1] == "sh /etc/acta-host-net/bootstrap.sh"
    assert node["binds"][0].startswith(f"{act_file.stem}.host-net/h1/bootstrap.sh:")
    assert "192.168.2.77/24" in (artifacts / "bootstrap.sh").read_text()


def test_route_attach_host_net_bad_ip_is_400(
    client: TestClient, act_file: Path
) -> None:
    ops.op_clab_generate(act_file, name="demo", image="ceos:4.35.4M")
    response = client.post(
        "/api/attach",
        json={
            "path": str(act_file),
            "host": "h1",
            "to": ["demo-leaf1"],
            "host_net": True,
            "host_ip": "10.9.9.9",
        },
    )
    assert response.status_code == 400


def test_op_act_upload_rejects_bad_tenant(act_file: Path) -> None:
    with pytest.raises(WebError) as exc:
        ops.op_act_upload(act_file, tenant="evil.example.com/x#")
    assert exc.value.status_code == 400


def test_op_act_onboard_host_requires_token() -> None:
    with pytest.raises(WebError) as exc:
        ops.op_act_onboard(cvaas_host="attacker.example.com")
    assert exc.value.status_code == 400


def test_clab_body_rejects_output(client: TestClient, act_file: Path) -> None:
    response = client.post(
        "/api/jobs/clab/generate",
        json={"path": str(act_file), "output": "/tmp/x.clab.yml"},
    )
    assert response.status_code == 422


def test_op_act_onboard_rejects_bad_host() -> None:
    with pytest.raises(WebError) as exc:
        ops.op_act_onboard(
            user="u",
            api_key="k",
            cvaas_host="a.io\nshutdown",
            cvaas_token="t",
        )
    assert exc.value.status_code == 400

"""Tests for Web UI settings load/patch with masked secrets."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from acta.config import load_config, save_config
from acta.web.app import create_app
from acta.web.settings_api import MASK, get_settings, patch_settings


def test_get_masks_secrets_and_nulls_missing(tmp_path: Path) -> None:
    save_config(
        tmp_path / ".config",
        {
            "CLAB_HOST": "trogdor",
            "ACT_API_KEY": "super-secret",
            "CVAAS_TOKEN": "token-value",
            "GENERIC_PASSWORD": "pw",
        },
    )

    settings = get_settings(tmp_path)

    assert settings["CLAB_HOST"] == "trogdor"
    assert settings["ACT_API_KEY"] == MASK
    assert settings["CVAAS_TOKEN"] == MASK
    assert settings["GENERIC_PASSWORD"] == MASK
    assert settings["preview_auto"] is False
    assert settings["preview_debounce_ms"] == 400


def test_get_returns_null_when_secret_absent(tmp_path: Path) -> None:
    settings = get_settings(tmp_path)
    assert settings["ACT_API_KEY"] is None
    assert settings["CVAAS_TOKEN"] is None
    assert settings["GENERIC_PASSWORD"] is None
    assert settings["CLAB_HOST"] == ""


def test_patch_host_and_empty_means_local(tmp_path: Path) -> None:
    patched = patch_settings(tmp_path, {"CLAB_HOST": "lab-host"})
    assert patched["CLAB_HOST"] == "lab-host"
    assert load_config(tmp_path / ".config")["CLAB_HOST"] == "lab-host"

    cleared = patch_settings(tmp_path, {"CLAB_HOST": ""})
    assert cleared["CLAB_HOST"] == ""
    assert load_config(tmp_path / ".config")["CLAB_HOST"] == ""


def test_patch_runtime_docker_or_empty(tmp_path: Path) -> None:
    patched = patch_settings(tmp_path, {"CLAB_RUNTIME": "docker"})
    assert patched["CLAB_RUNTIME"] == "docker"
    assert load_config(tmp_path / ".config")["CLAB_RUNTIME"] == "docker"

    cleared = patch_settings(tmp_path, {"CLAB_RUNTIME": ""})
    assert cleared["CLAB_RUNTIME"] == ""
    assert load_config(tmp_path / ".config")["CLAB_RUNTIME"] == ""


def test_patch_runtime_rejects_unknown(tmp_path: Path) -> None:
    client = TestClient(create_app(labs_root=tmp_path))
    response = client.patch("/api/settings", json={"CLAB_RUNTIME": "containerd"})
    assert response.status_code == 400
    assert response.json()["detail"] == "CLAB_RUNTIME must be docker or podman"


def test_patch_rejects_keys_outside_allowlist(tmp_path: Path) -> None:
    client = TestClient(create_app(labs_root=tmp_path))
    response = client.patch("/api/settings", json={"NOT_A_KEY": "x", "MAX_SPINES": "2"})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Unsupported settings keys"
    assert "NOT_A_KEY" in body["fields"]
    assert "MAX_SPINES" in body["fields"]


def test_patch_preserves_secret_when_mask_sent(tmp_path: Path) -> None:
    save_config(tmp_path / ".config", {"ACT_API_KEY": "real-key"})
    client = TestClient(create_app(labs_root=tmp_path))

    response = client.patch(
        "/api/settings",
        json={"ACT_API_KEY": MASK, "CLAB_IMAGE": "ceos:4.35"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ACT_API_KEY"] == MASK
    assert body["CLAB_IMAGE"] == "ceos:4.35"
    assert load_config(tmp_path / ".config")["ACT_API_KEY"] == "real-key"


def test_http_get_and_patch_round_trip(tmp_path: Path) -> None:
    client = TestClient(create_app(labs_root=tmp_path))
    empty = client.get("/api/settings")
    assert empty.status_code == 200
    assert empty.json()["CLAB_HOST"] == ""

    patched = client.patch(
        "/api/settings",
        json={
            "CLAB_HOST": "remote",
            "ACT_TENANT": "demo",
            "ACT_API_KEY": "secret",
            "preview_auto": True,
            "preview_debounce_ms": 500,
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["CLAB_HOST"] == "remote"
    assert body["ACT_TENANT"] == "demo"
    assert body["ACT_API_KEY"] == MASK
    assert body["preview_auto"] is True
    assert body["preview_debounce_ms"] == 500

    stored = load_config(tmp_path / ".config")
    assert stored["ACT_API_KEY"] == "secret"
    assert stored["PREVIEW_AUTO"] == "true"
    assert stored["PREVIEW_DEBOUNCE_MS"] == "500"


def test_patch_registry_settings_masks_token(tmp_path: Path):
    from acta.web.settings_api import MASK, get_settings, patch_settings

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

from __future__ import annotations

import pytest

from acta.capacity import Capacity
from acta.create import FabricSpec
from acta.web import preview as preview_mod
from acta.web.errors import WebError
from acta.web.preview import png_bytes_from_yaml, preview_from_spec


def _spec(**overrides) -> FabricSpec:
    base = {
        "hostname_prefix": "demo",
        "serial_prefix": "DEMO",
        "eos_version": "4.35.4M",
        "capacity": Capacity("l3ls", 2, 4, 0, 1, 0),
        "mlag_pairs": True,
        "spine_mlag": False,
        "member_leaf_pairs": [],
        "member_leaves_per_pair": 0,
    }
    base.update(overrides)
    return FabricSpec(**base)


def test_preview_emits_yaml_and_optional_png():
    result = preview_from_spec(_spec())
    assert "demo-spine1" in result.yaml_text
    assert result.summary["node_count"] >= 1
    assert result.summary["fabric_mode"] == "l3ls"
    assert result.png_base64 is None or result.png_base64.startswith("iVBOR")


def test_preview_rejects_bad_spine_mlag_on_l3ls():
    with pytest.raises(WebError) as exc:
        preview_from_spec(_spec(spine_mlag=True))
    assert exc.value.status_code == 422


def test_preview_png_soft_fails_without_dot(monkeypatch):
    monkeypatch.setattr(preview_mod, "write_png", lambda dot, path: False)
    result = preview_from_spec(_spec())
    assert result.png_base64 is None
    assert "demo-spine1" in result.yaml_text


def test_png_bytes_from_yaml_none_without_dot(monkeypatch):
    monkeypatch.setattr(preview_mod, "write_png", lambda dot, path: False)
    assert png_bytes_from_yaml("nodes:\n") is None

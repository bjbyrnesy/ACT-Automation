"""FastAPI routes for settings and YAML diagram refresh."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from acta.web.preview import preview_from_yaml
from acta.web.settings_api import get_settings, patch_settings

router = APIRouter()


class SettingsPatchBody(BaseModel):
    model_config = ConfigDict(extra="allow")


class PreviewFromYamlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yaml_text: str = Field(min_length=1)


def _labs_root(request: Request) -> Path:
    return Path(request.app.state.labs_root)


@router.get("/api/settings")
def settings_get(request: Request) -> dict[str, Any]:
    return get_settings(_labs_root(request))


@router.patch("/api/settings")
def settings_patch(request: Request, body: SettingsPatchBody) -> dict[str, Any]:
    return patch_settings(_labs_root(request), body.model_dump(exclude_unset=True))


@router.post("/api/preview-from-yaml")
def preview_yaml(body: PreviewFromYamlBody) -> dict[str, Any]:
    """Render a PNG from stored ACT YAML (Show refresh; no SSH)."""
    result = preview_from_yaml(body.yaml_text)
    return {
        "yaml_text": result.yaml_text,
        "png_base64": result.png_base64,
        "summary": result.summary,
    }

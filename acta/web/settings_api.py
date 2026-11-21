"""Load and patch Web UI settings stored beside the labs root."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from acta.config import load_config, save_config
from acta.web.errors import WebError

MASK = "••••"
_SECRET_KEYS = frozenset({"ACT_API_KEY", "CVAAS_TOKEN", "GENERIC_PASSWORD"})
_EXACT_KEYS = frozenset(
    {
        "CLAB_HOST",
        "CLAB_IMAGE",
        "CLAB_NAME",
        "preview_auto",
        "preview_debounce_ms",
    }
)
_PREFIXES = ("ACT_", "CVAAS_", "GENERIC_")
_DEFAULT_DEBOUNCE_MS = 400


def config_path(labs_root: Path) -> Path:
    """Return the ``.config`` path used by the Web UI for *labs_root*."""
    return labs_root / ".config"


def _is_allowed(key: str) -> bool:
    if key in _EXACT_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in _PREFIXES)


def _preview_auto(raw: dict[str, str]) -> bool:
    value = raw.get("PREVIEW_AUTO", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _preview_debounce_ms(raw: dict[str, str]) -> int:
    value = raw.get("PREVIEW_DEBOUNCE_MS", "").strip()
    if not value:
        return _DEFAULT_DEBOUNCE_MS
    try:
        return max(0, int(value))
    except ValueError:
        return _DEFAULT_DEBOUNCE_MS


def _mask_value(key: str, value: str | None) -> str | None:
    if key not in _SECRET_KEYS:
        return value
    if value:
        return MASK
    return None


def get_settings(labs_root: Path) -> dict[str, Any]:
    """Return allowlisted settings with secrets masked."""
    raw = load_config(config_path(labs_root))
    out: dict[str, Any] = {
        "CLAB_HOST": raw.get("CLAB_HOST", ""),
        "CLAB_IMAGE": raw.get("CLAB_IMAGE", ""),
        "CLAB_NAME": raw.get("CLAB_NAME", ""),
        "preview_auto": _preview_auto(raw),
        "preview_debounce_ms": _preview_debounce_ms(raw),
    }
    for key, value in raw.items():
        if key.startswith(_PREFIXES) or key in {"CLAB_HOST", "CLAB_IMAGE", "CLAB_NAME"}:
            if key in {"CLAB_HOST", "CLAB_IMAGE", "CLAB_NAME"}:
                continue
            if not _is_allowed(key):
                continue
            out[key] = _mask_value(key, value)
    for key in sorted(_SECRET_KEYS):
        if key not in out:
            out[key] = _mask_value(key, raw.get(key))
    return out


def patch_settings(labs_root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Apply an allowlisted partial update and return masked settings."""
    if not isinstance(updates, dict):
        raise WebError(400, "Settings patch must be an object")

    unknown = [key for key in updates if not _is_allowed(key)]
    if unknown:
        raise WebError(
            400,
            "Unsupported settings keys",
            fields={key: "not allowlisted" for key in unknown},
        )

    path = config_path(labs_root)
    data = load_config(path)

    for key, value in updates.items():
        if key == "preview_auto":
            data["PREVIEW_AUTO"] = "true" if bool(value) else "false"
            continue
        if key == "preview_debounce_ms":
            try:
                millis = int(value)
            except (TypeError, ValueError) as exc:
                raise WebError(
                    400,
                    "preview_debounce_ms must be an integer",
                    fields={"preview_debounce_ms": "invalid"},
                ) from exc
            data["PREVIEW_DEBOUNCE_MS"] = str(max(0, millis))
            continue

        if value is None:
            data[key] = ""
            continue

        text = value if isinstance(value, str) else str(value)
        if key in _SECRET_KEYS and text == MASK:
            continue
        if key == "CLAB_HOST":
            data[key] = text.strip()
            continue
        data[key] = text

    save_config(path, data)
    return get_settings(labs_root)

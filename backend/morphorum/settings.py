from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .paths import DEFAULT_CONFIG, ROOT, USER_CONFIG, ensure_runtime_dirs

MODEL_FAMILY_DEFS = {
    "sdxl": {
        "label": "SDXL",
        "supports_loras": True,
        "source": "external",
        "lora_source": "external",
    },
    "flux": {
        "label": "Flux",
        "supports_loras": True,
        "source": "external",
        "lora_source": "external",
    },
    "zimage": {
        "label": "Z-Image",
        "supports_loras": True,
        "source": "managed",
        "lora_source": "external",
    },
}
MODEL_FAMILIES = tuple(MODEL_FAMILY_DEFS)
EXTERNAL_MODEL_FAMILIES = tuple(
    family for family, definition in MODEL_FAMILY_DEFS.items()
    if definition.get("source") == "external"
)
MANAGED_MODEL_FAMILIES = tuple(
    family for family, definition in MODEL_FAMILY_DEFS.items()
    if definition.get("source") == "managed"
)
LORA_PATH_FAMILIES = tuple(
    family for family, definition in MODEL_FAMILY_DEFS.items()
    if definition.get("supports_loras")
    and definition.get("lora_source", "external") == "external"
)
MODEL_PATH_KEYS = ("checkpoints", "loras")

UI_THEME_OPTIONS = {"midnight-glass"}
UI_FONT_STYLE_OPTIONS = {"modern", "humanist", "geometric", "technical"}
UI_MONO_FONT_STYLE_OPTIONS = {"modern-mono", "cascadia", "classic-mono", "compact-mono"}
UI_SCALE_OPTIONS = {"compact", "standard", "comfortable"}


def model_family_definitions() -> list[dict[str, Any]]:
    """Return the enabled model-family registry in stable UI order."""
    return [
        {"id": family, **definition}
        for family, definition in MODEL_FAMILY_DEFS.items()
    ]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _normalize_model_paths(settings: dict[str, Any]) -> dict[str, Any]:
    models = settings.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        settings["models"] = models

    for family in MODEL_FAMILIES:
        definition = MODEL_FAMILY_DEFS[family]
        family_settings = models.setdefault(family, {})
        if not isinstance(family_settings, dict):
            family_settings = {}
            models[family] = family_settings

        path_keys: list[str] = []
        if definition.get("source") == "external":
            path_keys.append("checkpoints")
        if family in LORA_PATH_FAMILIES:
            path_keys.append("loras")

        for path_key in path_keys:
            paths = family_settings.setdefault(path_key, [])
            if not isinstance(paths, list):
                paths = []
                family_settings[path_key] = paths
            family_settings[path_key] = [str(item) for item in paths if str(item).strip()]

    return settings


def _normalize_managed_models(settings: dict[str, Any]) -> dict[str, Any]:
    managed = settings.setdefault("managed_models", {})
    if not isinstance(managed, dict):
        managed = {}
        settings["managed_models"] = managed

    locations = managed.setdefault("locations", {})
    if not isinstance(locations, dict):
        locations = {}
        managed["locations"] = locations

    locations.setdefault("zimage", r".\ckpts\z-image")
    for family in MANAGED_MODEL_FAMILIES:
        value = str(locations.get(family, "")).strip()
        if not value:
            value = rf".\ckpts\{family.replace('zimage', 'z-image')}"
        locations[family] = value

    return settings


def managed_model_location(family: str, settings: dict[str, Any] | None = None) -> Path:
    source = settings or load_settings()
    raw = str(
        source.get("managed_models", {})
        .get("locations", {})
        .get(family, rf".\ckpts\{family}")
    ).strip()
    if os.name != "nt":
        raw = raw.replace("\\", "/")
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not expanded.is_absolute():
        expanded = ROOT / expanded
    return expanded.resolve(strict=False)


def _normalize_preferences(settings: dict[str, Any]) -> dict[str, Any]:
    ui = settings.setdefault("ui", {})
    if not isinstance(ui, dict):
        ui = {}
        settings["ui"] = ui
    theme = str(ui.get("theme", "midnight-glass")).strip().lower()
    ui["theme"] = theme if theme in UI_THEME_OPTIONS else "midnight-glass"

    font_style = str(ui.get("font_style", "modern")).strip().lower()
    ui["font_style"] = font_style if font_style in UI_FONT_STYLE_OPTIONS else "modern"

    mono_font_style = str(ui.get("mono_font_style", "modern-mono")).strip().lower()
    ui["mono_font_style"] = (
        mono_font_style if mono_font_style in UI_MONO_FONT_STYLE_OPTIONS else "modern-mono"
    )

    ui_scale = str(ui.get("ui_scale", "compact")).strip().lower()
    ui["ui_scale"] = ui_scale if ui_scale in UI_SCALE_OPTIONS else "compact"

    try:
        preview_limit = int(ui.get("image_preview_limit", 5))
    except (TypeError, ValueError):
        preview_limit = 5
    ui["image_preview_limit"] = max(1, min(preview_limit, 50))

    performance = settings.setdefault("performance", {})
    if not isinstance(performance, dict):
        performance = {}
        settings["performance"] = performance
    unload = performance.get("unload_after_generation", False)
    if not isinstance(unload, bool):
        unload = str(unload).strip().lower() in {"1", "true", "yes", "on"}
    performance["unload_after_generation"] = unload

    sdxl_vae_tiling = performance.get("sdxl_vae_tiling", False)
    if not isinstance(sdxl_vae_tiling, bool):
        sdxl_vae_tiling = str(sdxl_vae_tiling).strip().lower() in {
            "1", "true", "yes", "on"
        }
    performance["sdxl_vae_tiling"] = sdxl_vae_tiling
    return settings


def load_settings() -> dict[str, Any]:
    """Load shipped defaults merged with user settings.

    Unknown user keys are preserved so newer/legacy settings survive a UI round-trip.
    """
    ensure_runtime_dirs()
    defaults = _read_yaml(DEFAULT_CONFIG)
    user = _read_yaml(USER_CONFIG)
    return _normalize_preferences(
        _normalize_managed_models(_normalize_model_paths(_deep_merge(defaults, user)))
    )


def save_settings(update: dict[str, Any]) -> dict[str, Any]:
    """Merge a settings update into the current user configuration and write atomically."""
    if not isinstance(update, dict):
        raise ValueError("settings payload must be an object")

    ensure_runtime_dirs()
    current_user = _read_yaml(USER_CONFIG)
    merged_user = _normalize_preferences(
        _normalize_managed_models(_normalize_model_paths(_deep_merge(current_user, update)))
    )

    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix="config-",
        suffix=".yaml.tmp",
        dir=str(USER_CONFIG.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(merged_user, handle, sort_keys=False, allow_unicode=True)
        os.replace(temp_name, USER_CONFIG)
    finally:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass

    return load_settings()


def validate_path(raw_path: str) -> dict[str, Any]:
    value = str(raw_path or "").strip()
    if not value:
        return {
            "path": value,
            "exists": False,
            "is_directory": False,
            "readable": False,
            "message": "Path is empty.",
        }

    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    try:
        resolved = expanded.resolve(strict=False)
    except OSError:
        resolved = expanded

    exists = resolved.exists()
    is_directory = resolved.is_dir() if exists else False
    readable = os.access(resolved, os.R_OK) if exists else False

    if not exists:
        message = "Directory does not exist yet."
    elif not is_directory:
        message = "Path exists but is not a directory."
    elif not readable:
        message = "Directory exists but is not readable by Morphorum."
    else:
        message = "Directory is available."

    return {
        "path": value,
        "resolved_path": str(resolved),
        "exists": exists,
        "is_directory": is_directory,
        "readable": readable,
        "message": message,
    }


def validate_model_paths(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    source = settings or load_settings()
    models = source.get("models", {}) if isinstance(source, dict) else {}
    results: list[dict[str, Any]] = []

    for family in MODEL_FAMILIES:
        family_settings = models.get(family, {}) if isinstance(models, dict) else {}
        if not isinstance(family_settings, dict):
            continue
        path_keys: list[str] = []
        if family in EXTERNAL_MODEL_FAMILIES:
            path_keys.append("checkpoints")
        if family in LORA_PATH_FAMILIES:
            path_keys.append("loras")
        for path_key in path_keys:
            for raw_path in family_settings.get(path_key, []) or []:
                result = validate_path(str(raw_path))
                result.update({"family": family, "kind": path_key})
                results.append(result)

    return results

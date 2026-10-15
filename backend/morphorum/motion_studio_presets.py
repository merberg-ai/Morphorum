"""Reusable named continuous-camera presets shared across projects and browser clients.

Stored in Morphorum's data directory, never inside an animation project.
Only validated 3D preset form values are stored, never a draft layer ID,
camera render schedules, soundtrack information or project paths.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from .motion_lab import PRESETS, PRESET_AXES
from .paths import DATA_DIR

MAX_CUSTOM_PRESETS = 64
MAX_FILE_BYTES = 256 * 1024
_LOCK = threading.RLock()


class CustomPresetError(ValueError):
    pass


class CustomPresetConflict(CustomPresetError):
    pass


class CustomPresetMissing(CustomPresetError):
    pass


def _file() -> Path:
    return DATA_DIR / "motion-studio-presets.json"


def _read() -> list[dict[str, Any]]:
    path = _file()
    if not path.is_file():
        return []
    if path.stat().st_size > MAX_FILE_BYTES:
        raise CustomPresetError("Custom preset library exceeds the allowed size.")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CustomPresetError("Cannot read custom preset library; no changes were made.") from exc
    if not isinstance(doc, dict) or doc.get("version") != 1 or not isinstance(doc.get("presets"), list):
        raise CustomPresetError("Custom preset library uses an unsupported format.")
    return doc["presets"]


def _write(presets: list[dict[str, Any]]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".motion-presets-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "presets": presets}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _number(payload: dict[str, Any], key: str, low: float, high: float) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise CustomPresetError(f"{key} must be a finite number.")
    if not low <= value <= high:
        raise CustomPresetError(f"{key} must be between {low} and {high}.")
    return float(value)


def _validate(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CustomPresetError("Preset must be an object.")
    name = payload.get("name")
    if not isinstance(name, str):
        raise CustomPresetError("Provide a preset name.")
    name = name.strip()
    if not name or len(name) > 64 or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise CustomPresetError("Preset name must be 1–64 printable characters.")
    kind = payload.get("preset")
    if kind not in PRESETS:
        raise CustomPresetError("Unknown continuous camera preset.")
    blend = payload.get("blend")
    if blend not in ("add", "replace") or (kind == "still" and blend != "replace"):
        raise CustomPresetError("Invalid blend method for this preset.")
    axes = payload.get("axes")
    if (not isinstance(axes, list) or not axes or len(axes) > 6 or
        any(not isinstance(axis, str) or axis not in PRESET_AXES[kind] for axis in axes) or
        len(set(axes)) != len(axes)):
        raise CustomPresetError("Choose distinct camera axes supported by the preset.")
    strength = _number(payload, "strength", 0, 1)
    cycle = _number(payload, "cycle_seconds", .2, 600)
    fade = _number(payload, "fade_seconds", 0, 120)
    start = _number(payload, "start_ratio", 0, 1)
    end = _number(payload, "end_ratio", 0, 1)
    if start >= end:
        raise CustomPresetError("Preset end must be after start.")
    return {
        "name": name, "preset": kind, "blend": blend, "axes": axes,
        "strength": strength, "cycle_seconds": cycle, "fade_seconds": fade,
        "start_ratio": start, "end_ratio": end,
    }


def list_custom_presets() -> list[dict[str, Any]]:
    with _LOCK:
        return sorted(_read(), key=lambda item: (item["name"].casefold(), item["id"]))


def create_custom_preset(payload: dict[str, Any]) -> dict[str, Any]:
    item = _validate(payload)
    with _LOCK:
        rows = _read()
        if len(rows) >= MAX_CUSTOM_PRESETS:
            raise CustomPresetConflict("The library already contains 64 presets.")
        if any(existing["name"].casefold() == item["name"].casefold() for existing in rows):
            raise CustomPresetConflict("A preset with that name already exists. Select it and use Update.")
        item["id"] = uuid.uuid4().hex
        rows.append(item)
        _write(rows)
        return item


def update_custom_preset(preset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = _validate(payload)
    with _LOCK:
        rows = _read()
        index = next((i for i, existing in enumerate(rows) if existing["id"] == preset_id), -1)
        if index < 0:
            raise CustomPresetMissing("Custom preset not found.")
        if any(existing["id"] != preset_id and existing["name"].casefold() == item["name"].casefold()
               for existing in rows):
            raise CustomPresetConflict("Another preset already uses that name.")
        item["id"] = preset_id
        rows[index] = item
        _write(rows)
        return item


def delete_custom_preset(preset_id: str) -> None:
    with _LOCK:
        rows = _read()
        remaining = [item for item in rows if item["id"] != preset_id]
        if len(remaining) == len(rows):
            raise CustomPresetMissing("Custom preset not found.")
        _write(remaining)

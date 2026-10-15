"""MS6.2: bounded, read-only host folder checks and explicit path saves.

Folder checks identify possible files and indexed entries. They never claim that
an arbitrary weight file has been loaded or is runtime compatible.
"""
from __future__ import annotations

import json
import os
import struct
import threading
from pathlib import Path
from typing import Any

from .model_index import CHECKPOINT_EXTENSIONS, LORA_EXTENSIONS, list_models
from .settings import (
    EXTERNAL_MODEL_FAMILIES, LORA_PATH_FAMILIES,
    load_settings, save_settings, validate_path,
)

FAMILIES = {
    "checkpoints": EXTERNAL_MODEL_FAMILIES,
    "loras": LORA_PATH_FAMILIES,
}
_SAVE_LOCK = threading.RLock()
MAX_ENTRIES = 1500
MAX_DIRS = 128
MAX_DEPTH = 6
MAX_HEADER_BYTES = 1024 * 1024


class SetupFolderError(ValueError):
    pass


class SetupFolderConflict(SetupFolderError):
    pass


def _folder(family: str, kind: str) -> None:
    if kind not in FAMILIES or family not in FAMILIES[kind]:
        raise SetupFolderError("Unsupported setup folder family or kind.")


def _family_evidence(path: Path, kind: str) -> str | None:
    """Conservative hints; neither file names nor headers prove loadability."""
    filename = path.stem.lower()
    if path.suffix.lower() == ".safetensors":
        try:
            with path.open("rb") as handle:
                size_bytes = handle.read(8)
                if len(size_bytes) != 8:
                    raise ValueError("Unrecognized safetensors header")
                length = struct.unpack("<Q", size_bytes)[0]
                if length < 2 or length > MAX_HEADER_BYTES:
                    raise ValueError("Unrecognized safetensors header")
                header = json.loads(handle.read(length))
            if not isinstance(header, dict):
                raise ValueError("Unrecognized safetensors header")
            meta = header.get("__metadata__") or {}
            info = " ".join(str(meta.get(k, ""))[:250] for k in (
                "ss_base_model_version", "base_model", "baseModel", "modelspec.architecture",
                "ss_sd_model_name",
            )).lower() if isinstance(meta, dict) else ""
            sample_keys = " ".join(list(header.keys())[:60]).lower()
            text = info + " " + sample_keys
            if "z-image" in text or "zimage" in text or "z_image" in text:
                return "zimage"
            if "flux" in text or "double_blocks." in text or "single_blocks." in text:
                return "flux"
            if "sdxl" in text or "sd_xl" in text or "conditioner.embedders." in text:
                return "sdxl"
        except (OSError, ValueError, UnicodeError, TypeError, OverflowError):
            # Filename evidence still matters when a candidate has no valid header.
            pass
    # Filename clues only when explicit; these are not proof of family.
    if "z-image" in filename or "zimage" in filename:
        return "zimage"
    if "flux" in filename:
        return "flux"
    if "sdxl" in filename or "sd_xl" in filename:
        return "sdxl"
    raise ValueError("Unrecognized safetensors header")


def _candidates(root: Path, kind: str, *, recursive: bool) -> tuple[list[Path], int, bool]:
    extensions = CHECKPOINT_EXTENSIONS if kind == "checkpoints" else LORA_EXTENSIONS
    files: list[Path] = []
    seen = 0
    dirs = 0
    truncated = False
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        folder, depth = queue.pop(0)
        dirs += 1
        if dirs > MAX_DIRS:
            truncated = True
            break
        try:
            with os.scandir(folder) as items:
                for item in items:
                    seen += 1
                    if seen > MAX_ENTRIES:
                        truncated = True
                        break
                    try:
                        if item.is_file(follow_symlinks=False):
                            path = Path(item.path)
                            if path.suffix.lower() in extensions:
                                files.append(path)
                        elif recursive and depth < MAX_DEPTH and item.is_dir(follow_symlinks=False):
                            queue.append((Path(item.path), depth + 1))
                    except OSError:
                        continue
        except OSError:
            continue
        if truncated:
            break
    return files, seen, truncated


def inspect_folder(*, family: str, kind: str, path: str) -> dict[str, Any]:
    _folder(family, kind)
    if not isinstance(path, str) or len(path) > 4096:
        raise SetupFolderError("Folder path must be a string of at most 4096 characters.")
    validation = validate_path(path)
    result: dict[str, Any] = {
        **validation, "family": family, "kind": kind,
        "status": "invalid", "candidates": 0, "wrong_family": 0,
        "indexed": 0, "truncated": False, "examples": [],
    }
    if not validation["is_directory"] or not validation["readable"]:
        return result
    root = Path(validation["resolved_path"])
    recursive = bool(load_settings().get("scan", {}).get("recursive", True))
    found, count, truncated = _candidates(root, kind, recursive=recursive)
    wrong = [path for path in found if (hint := _family_evidence(path, kind)) and hint != family]
    possible = [item for item in found if item not in wrong]
    # Restrict indexed results to the exact requested host folder and family/kind.
    indexed = 0
    for entry in list_models(family=family, kind=kind, limit=2000):
        try:
            Path(str(entry["path"])).resolve(strict=False).relative_to(root)
            indexed += 1
        except (KeyError, ValueError, OSError):
            continue
    status = ("indexed" if indexed else "candidates") if possible else (
        "incompatible" if wrong else "empty"
    )
    if truncated and status == "empty":
        status = "partial"
    messages = {
        "empty": "Readable folder, but no matching file extensions were found.",
        "incompatible": "Files found with clues pointing to another model family.",
        "candidates": "Possible weight files found. Save and scan to index; loadability is not guaranteed.",
        "indexed": "Files are indexed and selectable; runtime loadability has not been tested.",
        "partial": "Inspection reached its safety limit before finding matching files.",
    }
    result.update(
        status=status,
        candidates=len(possible),
        wrong_family=len(wrong),
        indexed=indexed,
        truncated=truncated,
        inspected_entries=count,
        examples=[path.name for path in possible[:4]],
        message=messages[status] + (
            " Folder inspection was truncated." if truncated and status != "partial" else ""
        ),
    )
    return result


def save_setup_folders(*, kind: str, paths: dict[str, Any],
                       expected: dict[str, Any]) -> dict[str, Any]:
    """Save only this wizard page's directories, with compare-before-write.

    No implicit directory creation, file copying, download or GPU model loading.
    """
    if kind not in FAMILIES or not isinstance(paths, dict) or not isinstance(expected, dict):
        raise SetupFolderError("Invalid setup folder request.")
    if set(paths) != set(FAMILIES[kind]) or set(expected) != set(FAMILIES[kind]):
        raise SetupFolderError("Every supported family must be provided for this folder type.")
    cleaned: dict[str, list[str]] = {}
    for family in FAMILIES[kind]:
        proposed = paths[family]
        old = expected[family]
        if not isinstance(proposed, list) or not isinstance(old, list) or len(proposed) > 20:
            raise SetupFolderError("Folder lists must be arrays of at most 20 paths.")
        if any(not isinstance(p, str) for p in proposed + old):
            raise SetupFolderError("Folder paths must be strings.")
        values = list(dict.fromkeys(p.strip() for p in proposed if p.strip()))
        if len(values) != len([p for p in proposed if p.strip()]):
            raise SetupFolderError("Remove duplicate directory entries before saving.")
        for value in values:
            result = validate_path(value)
            if not (result["is_directory"] and result["readable"]):
                raise SetupFolderError(f"{family} {kind}: {result['message']}")
        cleaned[family] = values
    with _SAVE_LOCK:
        settings = load_settings()
        for family in FAMILIES[kind]:
            current = settings.get("models", {}).get(family, {}).get(kind, [])
            if current != expected[family]:
                raise SetupFolderConflict("Configured folders changed in another tab. Reload before saving.")
        changes = {"models": {family: {kind: cleaned[family]} for family in FAMILIES[kind]}}
        saved = save_settings(changes)
        return {"status": "saved", "paths": {
            family: saved["models"][family][kind] for family in FAMILIES[kind]
        }}

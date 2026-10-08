from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .animation_timeline import (
    NUMERIC_TRACK_DEFS,
    build_tracks_from_legacy,
    normalize_tracks,
    sync_legacy_from_tracks,
    track_keyframe_count,
)
from .console import emit_console
from .paths import PROJECTS_DIR, ensure_runtime_dirs

ANIMATION_PROJECT_SCHEMA = 2
_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_KNOWN_TOP_LEVEL = {
    "schema_version",
    "id",
    "name",
    "created_at",
    "updated_at",
    "animation",
    "model",
    "prompts",
    "negative_prompts",
    "motion",
    "camera_3d",
    "generation",
    "cadence",
    "tracks",
    "notes",
}


class AnimationProjectError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:48] or "animation"


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _safe_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _project_dir(project_id: str) -> Path:
    project_id = str(project_id or "").strip().lower()
    if not _PROJECT_ID.fullmatch(project_id):
        raise AnimationProjectError("Invalid animation project id.")
    root = PROJECTS_DIR.resolve(strict=False)
    path = (root / project_id).resolve(strict=False)
    if root not in path.parents:
        raise AnimationProjectError("Animation project path escaped the projects directory.")
    return path


def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def _default_project(name: str, project_id: str | None = None) -> dict[str, Any]:
    now = _utc_now()
    title = str(name or "").strip() or "Untitled Animation"
    pid = project_id or f"{_slugify(title)}-{uuid.uuid4().hex[:8]}"
    project = {
        "schema_version": ANIMATION_PROJECT_SCHEMA,
        "id": pid,
        "name": title,
        "created_at": now,
        "updated_at": now,
        "animation": {
            "max_frames": 120,
            "fps": 24.0,
            "width": 1024,
            "height": 1024,
            "prompt_transition": "blend",
            "mode": "2d",
            "start_mode": "prompt",
            "source_image": "",
            "source_image_name": "",
        },
        "model": {
            "model_id": "",
            "family": "",
            "variant": "",
        },
        "prompts": {
            "0": "",
        },
        "negative_prompts": {
            "0": "",
        },
        "motion": {
            "angle": "0:(0)",
            "zoom": "0:(1.0)",
            "translation_x": "0:(0)",
            "translation_y": "0:(0)",
            "border_mode": "replicate",
        },
        "camera_3d": {
            "translation_x": "0:(0)",
            "translation_y": "0:(0)",
            "translation_z": "0:(0)",
            "rotation_x": "0:(0)",
            "rotation_y": "0:(0)",
            "rotation_z": "0:(0)",
            "fov": "0:(40)",
            "depth_resolution": "auto",
        },
        "generation": {
            "strength": "0:(0.65)",
            "noise": "0:(0.02)",
            "steps": "0:(20)",
            "guidance": "0:(0)",
            "sampler": "flowmatch_euler",
            "seed": -1,
            "seed_behavior": "fixed",
            "seed_increment": 1,
        },
        "cadence": {
            "diffusion": "0:(1)",
        },
        "notes": "",
    }
    project["tracks"] = build_tracks_from_legacy(project)
    return project


def _normalize_prompt_map(value: Any, max_frames: int) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    normalized: dict[int, str] = {}
    for raw_frame, raw_prompt in source.items():
        try:
            frame = int(str(raw_frame).strip())
        except (TypeError, ValueError):
            continue
        if 0 <= frame < max_frames:
            normalized[frame] = str(raw_prompt or "")
    if 0 not in normalized:
        normalized[0] = ""
    return {str(frame): normalized[frame] for frame in sorted(normalized)}


def _normalize_string_section(
    value: Any,
    defaults: dict[str, str],
) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, Any] = {}
    for key, default in defaults.items():
        result[key] = str(source.get(key, default) or default).strip()
    for key, item in source.items():
        if key not in result:
            result[key] = deepcopy(item)
    return result


def _legacy_timeline_changed(
    payload: dict[str, Any],
    existing: dict[str, Any],
) -> bool:
    for key in ("prompts", "negative_prompts"):
        if key in payload and payload.get(key) != existing.get(key):
            return True

    payload_animation = payload.get("animation")
    existing_animation = existing.get("animation", {})
    if (
        isinstance(payload_animation, dict)
        and "prompt_transition" in payload_animation
        and payload_animation.get("prompt_transition")
        != (
            existing_animation.get("prompt_transition")
            if isinstance(existing_animation, dict)
            else None
        )
    ):
        return True

    for section, keys in {
        "motion": ("angle", "zoom", "translation_x", "translation_y"),
        "camera_3d": (
            "translation_x",
            "translation_y",
            "translation_z",
            "rotation_x",
            "rotation_y",
            "rotation_z",
            "fov",
        ),
        "generation": ("strength", "noise", "steps", "guidance"),
        "cadence": ("diffusion",),
    }.items():
        incoming = payload.get(section)
        current = existing.get(section, {})
        if not isinstance(incoming, dict):
            continue
        current = current if isinstance(current, dict) else {}
        for key in keys:
            if key in incoming and incoming.get(key) != current.get(key):
                return True

    return False


def _merge_legacy_timeline_changes(
    payload: dict[str, Any],
    existing: dict[str, Any],
    project: dict[str, Any],
    tracks: dict[str, Any],
) -> dict[str, Any]:
    merged = normalize_tracks(tracks, project=project)
    legacy = build_tracks_from_legacy(project)

    comparison = existing
    if existing is payload:
        comparison = deepcopy(project)
        comparison["tracks"] = deepcopy(merged)
        sync_legacy_from_tracks(comparison, comparison["tracks"])

    for payload_key, track_name in {
        "prompts": "positive",
        "negative_prompts": "negative",
    }.items():
        if payload_key in payload and payload.get(payload_key) != comparison.get(payload_key):
            merged["prompts"][track_name]["keyframes"] = deepcopy(
                legacy["prompts"][track_name]["keyframes"]
            )

    payload_animation = payload.get("animation")
    existing_animation = comparison.get("animation", {})
    if (
        isinstance(payload_animation, dict)
        and "prompt_transition" in payload_animation
        and payload_animation.get("prompt_transition")
        != (
            existing_animation.get("prompt_transition")
            if isinstance(existing_animation, dict)
            else None
        )
    ):
        mode = legacy["prompts"]["positive"]["interpolation"]
        merged["prompts"]["positive"]["interpolation"] = mode
        merged["prompts"]["negative"]["interpolation"] = mode

    for field, definition in NUMERIC_TRACK_DEFS.items():
        incoming = payload.get(definition["legacy_section"])
        current = comparison.get(definition["legacy_section"], {})
        if not isinstance(incoming, dict):
            continue
        current = current if isinstance(current, dict) else {}
        key = definition["legacy_key"]
        if key not in incoming or incoming.get(key) == current.get(key):
            continue

        replacement = legacy[definition["group"]][definition["name"]]
        target = merged[definition["group"]][definition["name"]]
        target["schedule"] = replacement["schedule"]
        target["keyframes"] = deepcopy(replacement["keyframes"])

    return normalize_tracks(merged, project=project)


def normalize_animation_project(
    payload: dict[str, Any] | None,
    *,
    existing: dict[str, Any] | None = None,
    project_id: str | None = None,
    prefer_tracks: bool | None = None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    had_existing = isinstance(existing, dict)
    base = deepcopy(existing) if had_existing else _default_project(
        str(payload.get("name") or "Untitled Animation"),
        project_id=project_id,
    )

    pid = project_id or str(base.get("id") or payload.get("id") or "").strip().lower()
    if not _PROJECT_ID.fullmatch(pid):
        raise AnimationProjectError("Invalid animation project id.")

    project = deepcopy(base)
    project["schema_version"] = ANIMATION_PROJECT_SCHEMA
    project["id"] = pid
    project["name"] = str(payload.get("name", project.get("name", "Untitled Animation")) or "").strip() or "Untitled Animation"
    project["created_at"] = str(project.get("created_at") or _utc_now())
    project["updated_at"] = _utc_now()

    animation_source = payload.get("animation", project.get("animation", {}))
    animation_source = animation_source if isinstance(animation_source, dict) else {}
    animation = dict(project.get("animation", {}))
    animation.update(animation_source)
    animation["max_frames"] = _safe_int(animation.get("max_frames"), 120, 1, 1_000_000)
    animation["fps"] = _safe_float(animation.get("fps"), 24.0, 1.0, 240.0)
    animation["width"] = _safe_int(animation.get("width"), 1024, 64, 8192)
    animation["height"] = _safe_int(animation.get("height"), 1024, 64, 8192)
    prompt_transition = str(animation.get("prompt_transition", "blend") or "blend").strip().lower()
    animation["prompt_transition"] = (
        prompt_transition if prompt_transition in {"blend", "hold"} else "blend"
    )
    raw_mode = str(animation.get("mode", "2d") or "2d").strip().lower()
    animation["mode"] = raw_mode if raw_mode in {"2d", "3d"} else "2d"
    raw_start_mode = animation.get("start_mode")
    if raw_start_mode is None:
        start_mode = "source" if animation.get("source_image") else "prompt"
    else:
        start_mode = str(raw_start_mode or "prompt").strip().lower()
    animation["start_mode"] = (
        start_mode if start_mode in {"prompt", "source"} else "prompt"
    )
    animation["source_image"] = str(animation.get("source_image") or "").strip()
    animation["source_image_name"] = str(animation.get("source_image_name") or "").strip()
    project["animation"] = animation

    model_source = payload.get("model", project.get("model", {}))
    model_source = model_source if isinstance(model_source, dict) else {}
    model = dict(project.get("model", {}))
    model.update(model_source)
    model["model_id"] = str(model.get("model_id") or "").strip()
    model["family"] = str(model.get("family") or "").strip().lower()
    model["variant"] = str(model.get("variant") or "").strip().lower()
    project["model"] = model

    project["prompts"] = _normalize_prompt_map(
        payload.get("prompts", project.get("prompts")),
        animation["max_frames"],
    )
    project["negative_prompts"] = _normalize_prompt_map(
        payload.get("negative_prompts", project.get("negative_prompts")),
        animation["max_frames"],
    )

    project["motion"] = _normalize_string_section(
        payload.get("motion", project.get("motion")),
        {
            "angle": "0:(0)",
            "zoom": "0:(1.0)",
            "translation_x": "0:(0)",
            "translation_y": "0:(0)",
            "border_mode": "replicate",
        },
    )
    border_mode = str(project["motion"].get("border_mode") or "replicate").strip().lower()
    project["motion"]["border_mode"] = (
        border_mode if border_mode in {"replicate", "wrap"} else "replicate"
    )

    project["camera_3d"] = _normalize_string_section(
        payload.get("camera_3d", project.get("camera_3d")),
        {
            "translation_x": "0:(0)",
            "translation_y": "0:(0)",
            "translation_z": "0:(0)",
            "rotation_x": "0:(0)",
            "rotation_y": "0:(0)",
            "rotation_z": "0:(0)",
            "fov": "0:(40)",
            "depth_resolution": "auto",
        },
    )
    depth_resolution = str(
        project["camera_3d"].get("depth_resolution") or "auto"
    ).strip().lower()
    project["camera_3d"]["depth_resolution"] = (
        depth_resolution
        if depth_resolution in {"auto", "384", "512", "768", "full"}
        else "auto"
    )

    generation_source = payload.get("generation", project.get("generation", {}))
    generation_source = generation_source if isinstance(generation_source, dict) else {}
    generation = dict(project.get("generation", {}))
    generation.update(generation_source)
    for key, default in {
        "strength": "0:(0.65)",
        "noise": "0:(0.02)",
        "steps": "0:(20)",
        "guidance": "0:(0)",
    }.items():
        generation[key] = str(generation.get(key, default) or default).strip()
    generation["sampler"] = str(generation.get("sampler") or "flowmatch_euler").strip().lower()
    generation["seed"] = _safe_int(generation.get("seed"), -1, -1, 2**32 - 1)
    behavior = str(generation.get("seed_behavior") or "fixed").strip().lower()
    generation["seed_behavior"] = behavior if behavior in {"fixed", "increment", "random"} else "fixed"
    generation["seed_increment"] = _safe_int(generation.get("seed_increment"), 1, -2**31, 2**31 - 1)
    project["generation"] = generation

    project["cadence"] = _normalize_string_section(
        payload.get("cadence", project.get("cadence")),
        {"diffusion": "0:(1)"},
    )

    project["notes"] = str(payload.get("notes", project.get("notes", "")) or "")

    incoming_tracks = payload.get("tracks")
    existing_tracks = existing.get("tracks") if had_existing else None
    use_incoming_tracks = isinstance(incoming_tracks, dict)

    if prefer_tracks is True:
        legacy_changed = False
    elif prefer_tracks is False:
        legacy_changed = True
    elif (
        had_existing
        and isinstance(existing, dict)
        and existing is payload
        and use_incoming_tracks
    ):
        track_candidate = deepcopy(project)
        track_candidate["tracks"] = normalize_tracks(
            incoming_tracks,
            project=track_candidate,
        )
        sync_legacy_from_tracks(track_candidate, track_candidate["tracks"])
        legacy_changed = _legacy_timeline_changed(payload, track_candidate)
    else:
        legacy_changed = (
            _legacy_timeline_changed(payload, existing)
            if had_existing and isinstance(existing, dict)
            else False
        )

    if use_incoming_tracks and isinstance(existing_tracks, dict) and had_existing:
        project["tracks"] = normalize_tracks(incoming_tracks, project=project)
        if legacy_changed:
            project["tracks"] = _merge_legacy_timeline_changes(
                payload,
                existing,
                project,
                project["tracks"],
            )
        sync_legacy_from_tracks(project, project["tracks"])
    elif use_incoming_tracks and (
        not had_existing
        or (
            not isinstance(existing_tracks, dict)
            and _safe_int(
                payload.get("schema_version"),
                1,
                1,
                1_000_000,
            ) >= ANIMATION_PROJECT_SCHEMA
        )
    ):
        project["tracks"] = normalize_tracks(incoming_tracks, project=project)
        sync_legacy_from_tracks(project, project["tracks"])
    else:
        project["tracks"] = build_tracks_from_legacy(project)

    # Native projects are forward-compatible: unknown top-level fields survive
    # a load/edit/save round trip just like future imported compatibility data.
    for key, value in payload.items():
        if key not in _KNOWN_TOP_LEVEL:
            project[key] = deepcopy(value)

    return project


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def create_animation_project(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_runtime_dirs()
    payload = payload if isinstance(payload, dict) else {}
    name = str(payload.get("name") or "Untitled Animation").strip() or "Untitled Animation"
    project_id = f"{_slugify(name)}-{uuid.uuid4().hex[:8]}"
    project = normalize_animation_project(payload, project_id=project_id)
    _write_atomic(_project_file(project_id), project)
    emit_console("info", "animation", f"Created animation project {project_id}: {project['name']}.")
    return project


def load_animation_project(project_id: str) -> dict[str, Any]:
    path = _project_file(project_id)
    if not path.is_file():
        raise AnimationProjectError("Animation project not found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise AnimationProjectError(f"Could not read animation project: {exc}") from exc
    if not isinstance(payload, dict):
        raise AnimationProjectError("Animation project file does not contain an object.")
    try:
        source_schema = int(payload.get("schema_version", 1) or 1)
    except (TypeError, ValueError):
        source_schema = 1
    migration_needed = (
        source_schema < ANIMATION_PROJECT_SCHEMA
        or not isinstance(payload.get("tracks"), dict)
    )
    project = normalize_animation_project(
        payload,
        existing=payload,
        project_id=project_id,
        prefer_tracks=True,
    )
    project["created_at"] = str(payload.get("created_at") or project["created_at"])
    project["updated_at"] = str(payload.get("updated_at") or project["updated_at"])
    if migration_needed:
        _write_atomic(path, project)
        emit_console(
            "info",
            "animation",
            f"Migrated animation project {project_id} to schema {ANIMATION_PROJECT_SCHEMA}.",
        )
    return project


def save_animation_project(
    project_id: str,
    payload: dict[str, Any],
    *,
    prefer_tracks: bool | None = None,
) -> dict[str, Any]:
    path = _project_file(project_id)
    if not path.is_file():
        raise AnimationProjectError("Animation project not found.")
    existing = load_animation_project(project_id)
    project = normalize_animation_project(
        payload,
        existing=existing,
        project_id=project_id,
        prefer_tracks=prefer_tracks,
    )
    project["created_at"] = existing["created_at"]
    project["updated_at"] = _utc_now()
    _write_atomic(path, project)
    emit_console("info", "animation", f"Saved animation project {project_id}: {project['name']}.")
    return project


def list_animation_projects() -> list[dict[str, Any]]:
    ensure_runtime_dirs()
    projects: list[dict[str, Any]] = []
    try:
        directories = sorted(PROJECTS_DIR.iterdir())
    except OSError:
        return []

    for directory in directories:
        if not directory.is_dir() or not _PROJECT_ID.fullmatch(directory.name):
            continue
        path = directory / "project.json"
        if not path.is_file():
            continue
        try:
            project = load_animation_project(directory.name)
        except AnimationProjectError:
            continue
        animation = project.get("animation", {})
        prompts = project.get("prompts", {})
        projects.append(
            {
                "id": project["id"],
                "name": project["name"],
                "schema_version": project["schema_version"],
                "created_at": project["created_at"],
                "updated_at": project["updated_at"],
                "max_frames": animation.get("max_frames"),
                "fps": animation.get("fps"),
                "width": animation.get("width"),
                "height": animation.get("height"),
                "model_id": project.get("model", {}).get("model_id", ""),
                "prompt_keyframes": (
                    track_keyframe_count(project, group="prompts", name="positive")
                    or (len(prompts) if isinstance(prompts, dict) else 0)
                ),
            }
        )

    projects.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return projects


def animation_project_directory(project_id: str) -> Path:
    return _project_dir(project_id)


def animation_project_path(project_id: str) -> str:
    return str(_project_file(project_id))

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .console import emit_console
from .paths import PROJECTS_DIR, ensure_runtime_dirs

ANIMATION_PROJECT_SCHEMA = 1
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
    "generation",
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
    return {
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
        "notes": "",
    }


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


def normalize_animation_project(
    payload: dict[str, Any] | None,
    *,
    existing: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    base = deepcopy(existing) if isinstance(existing, dict) else _default_project(
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
        },
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

    project["notes"] = str(payload.get("notes", project.get("notes", "")) or "")

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
    return normalize_animation_project(payload, existing=payload, project_id=project_id)


def save_animation_project(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    path = _project_file(project_id)
    if not path.is_file():
        raise AnimationProjectError("Animation project not found.")
    existing = load_animation_project(project_id)
    project = normalize_animation_project(payload, existing=existing, project_id=project_id)
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
                "prompt_keyframes": len(prompts) if isinstance(prompts, dict) else 0,
            }
        )

    projects.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return projects


def animation_project_path(project_id: str) -> str:
    return str(_project_file(project_id))

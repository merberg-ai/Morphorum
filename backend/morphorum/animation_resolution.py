from __future__ import annotations

from copy import deepcopy
from typing import Any

from .animation_timeline import (
    NUMERIC_TRACK_DEFS,
    TIMELINE_SCHEMA_VERSION,
    numeric_track,
    prompt_track,
    prompt_track_map,
)
from .schedules import (
    ScheduleError,
    resolve_numeric_schedule,
    resolve_prompt_transition,
    sample_schedule,
    validate_numeric_schedule,
)

SCHEDULE_FIELDS: dict[str, tuple[str, str, str]] = {
    field: (
        definition["legacy_section"],
        definition["legacy_key"],
        definition["value_type"],
    )
    for field, definition in NUMERIC_TRACK_DEFS.items()
}


def _project_context(project: dict[str, Any]) -> tuple[int, float, int]:
    animation = project.get("animation", {})
    generation = project.get("generation", {})
    max_frames = max(1, int(animation.get("max_frames", 120)))
    fps = max(1.0, float(animation.get("fps", 24.0)))
    seed = int(generation.get("seed", -1))
    expression_seed = seed if seed >= 0 else 0
    return max_frames, fps, expression_seed


def _schedule_text(project: dict[str, Any], field: str) -> str:
    track = numeric_track(project, field)
    value = str(track.get("schedule", "") or "").strip()
    if not value:
        raise ScheduleError(f"Animation schedule '{field}' is empty.")
    return value


def _track_interpolation(project: dict[str, Any], field: str) -> str:
    track = numeric_track(project, field)
    interpolation = str(track.get("interpolation") or "linear").strip().lower()
    if interpolation not in {"linear", "hold"}:
        raise ScheduleError(
            f"Unsupported schedule interpolation mode '{interpolation}' for '{field}'."
        )
    return interpolation


def _resolve_field(
    project: dict[str, Any],
    field: str,
    frame: int,
) -> float | int:
    max_frames, fps, expression_seed = _project_context(project)
    value = resolve_numeric_schedule(
        _schedule_text(project, field),
        frame=frame,
        max_frames=max_frames,
        seed=expression_seed,
        fps=fps,
        interpolation=_track_interpolation(project, field),
    )
    kind = SCHEDULE_FIELDS[field][2]
    if kind == "integer":
        return max(1, int(round(value)))
    return float(value)


def _resolved_seed(project: dict[str, Any], frame: int) -> dict[str, Any]:
    generation = project.get("generation", {})
    base_seed = int(generation.get("seed", -1))
    behavior = str(generation.get("seed_behavior", "fixed") or "fixed").lower()
    increment = int(generation.get("seed_increment", 1))

    resolved: int | None
    if base_seed < 0 or behavior == "random":
        resolved = None
    elif behavior == "increment":
        resolved = (base_seed + frame * increment) % (2**32)
    else:
        resolved = base_seed

    return {
        "base": base_seed,
        "behavior": behavior,
        "increment": increment,
        "resolved": resolved,
        "random_at_render": resolved is None,
    }


def _resolve_prompt_track(
    project: dict[str, Any],
    name: str,
    *,
    frame: int,
    max_frames: int,
):
    track = prompt_track(project, name)
    mode = str(track.get("interpolation") or "blend").strip().lower()
    return resolve_prompt_transition(
        prompt_track_map(track),
        frame=frame,
        max_frames=max_frames,
        mode=mode,
    )


def resolve_project_frame(
    project: dict[str, Any],
    frame: int,
) -> dict[str, Any]:
    max_frames, fps, _expression_seed = _project_context(project)
    if frame < 0 or frame >= max_frames:
        raise ScheduleError(
            f"Frame {frame} is outside the animation range 0..{max_frames - 1}."
        )

    animation = project.get("animation", {})
    positive = _resolve_prompt_track(
        project,
        "positive",
        frame=frame,
        max_frames=max_frames,
    )
    negative = _resolve_prompt_track(
        project,
        "negative",
        frame=frame,
        max_frames=max_frames,
    )

    motion = {
        key.split(".", 1)[1]: _resolve_field(project, key, frame)
        for key in SCHEDULE_FIELDS
        if key.startswith("motion.")
    }

    motion["border_mode"] = str(
        project.get("motion", {}).get("border_mode", "replicate") or "replicate"
    ).strip().lower()

    generation = {
        key.split(".", 1)[1]: _resolve_field(project, key, frame)
        for key in SCHEDULE_FIELDS
        if key.startswith("generation.")
    }
    source_generation = project.get("generation", {})
    generation["sampler"] = str(source_generation.get("sampler", "") or "")
    generation["seed"] = _resolved_seed(project, frame)

    tracks = project.get("tracks", {})
    timeline_schema = (
        int(tracks.get("schema_version", TIMELINE_SCHEMA_VERSION))
        if isinstance(tracks, dict)
        else TIMELINE_SCHEMA_VERSION
    )

    return {
        "frame": frame,
        "max_frames": max_frames,
        "fps": fps,
        "time_seconds": frame / fps,
        "timeline": {
            "schema_version": timeline_schema,
            "source": "tracks",
        },
        "dimensions": {
            "width": int(animation.get("width", 1024)),
            "height": int(animation.get("height", 1024)),
        },
        "model": deepcopy(project.get("model", {})),
        "prompts": {
            "positive": positive.to_dict(),
            "negative": negative.to_dict(),
        },
        "motion": motion,
        "generation": generation,
    }


def validate_project_schedules(project: dict[str, Any]) -> dict[str, Any]:
    max_frames, fps, expression_seed = _project_context(project)
    fields: dict[str, Any] = {}
    all_issues: list[dict[str, Any]] = []

    for field in SCHEDULE_FIELDS:
        try:
            interpolation = _track_interpolation(project, field)
            result = validate_numeric_schedule(
                _schedule_text(project, field),
                max_frames=max_frames,
                seed=expression_seed,
                fps=fps,
                interpolation=interpolation,
            )
            result["interpolation"] = interpolation
        except ScheduleError as exc:
            result = {
                "valid": False,
                "issues": [{"severity": "error", "message": str(exc)}],
                "keyframes": [],
                "interpolation": "linear",
            }

        fields[field] = result
        for issue in result["issues"]:
            all_issues.append({"field": field, **issue})

    for name in ("positive", "negative"):
        try:
            track = prompt_track(project, name)
            mode = str(track.get("interpolation") or "blend").strip().lower()
            if mode not in {"blend", "hold"}:
                raise ScheduleError(
                    f"Unsupported prompt transition mode '{mode}'."
                )
        except ScheduleError as exc:
            all_issues.append(
                {
                    "field": f"tracks.prompts.{name}",
                    "severity": "error",
                    "message": str(exc),
                }
            )

    return {
        "valid": not any(issue["severity"] == "error" for issue in all_issues),
        "issues": all_issues,
        "fields": fields,
    }


def project_schedule_series(
    project: dict[str, Any],
    field: str,
    *,
    sample_count: int = 120,
) -> dict[str, Any]:
    if field not in SCHEDULE_FIELDS:
        raise ScheduleError(f"Unknown animation schedule field '{field}'.")

    max_frames, fps, expression_seed = _project_context(project)
    schedule = _schedule_text(project, field)
    interpolation = _track_interpolation(project, field)
    validation = validate_numeric_schedule(
        schedule,
        max_frames=max_frames,
        seed=expression_seed,
        fps=fps,
        interpolation=interpolation,
    )
    if not validation["valid"]:
        first_error = next(
            issue for issue in validation["issues"] if issue["severity"] == "error"
        )
        raise ScheduleError(first_error["message"])

    return {
        "field": field,
        "schedule": schedule,
        "interpolation": interpolation,
        "max_frames": max_frames,
        "samples": sample_schedule(
            schedule,
            max_frames=max_frames,
            seed=expression_seed,
            fps=fps,
            interpolation=interpolation,
            sample_count=sample_count,
        ),
        "keyframes": validation["keyframes"],
        "issues": validation["issues"],
    }

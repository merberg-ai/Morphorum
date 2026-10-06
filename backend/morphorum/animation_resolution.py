from __future__ import annotations

from copy import deepcopy
from typing import Any

from .schedules import (
    ScheduleError,
    resolve_numeric_schedule,
    resolve_prompt_transition,
    sample_schedule,
    validate_numeric_schedule,
)

SCHEDULE_FIELDS: dict[str, tuple[str, str, str]] = {
    "motion.angle": ("motion", "angle", "float"),
    "motion.zoom": ("motion", "zoom", "float"),
    "motion.translation_x": ("motion", "translation_x", "float"),
    "motion.translation_y": ("motion", "translation_y", "float"),
    "generation.strength": ("generation", "strength", "float"),
    "generation.noise": ("generation", "noise", "float"),
    "generation.steps": ("generation", "steps", "integer"),
    "generation.guidance": ("generation", "guidance", "float"),
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
    definition = SCHEDULE_FIELDS.get(field)
    if definition is None:
        raise ScheduleError(f"Unknown animation schedule field '{field}'.")
    section, key, _kind = definition
    source = project.get(section, {})
    if not isinstance(source, dict):
        raise ScheduleError(f"Animation project section '{section}' is invalid.")
    value = str(source.get(key, "") or "").strip()
    if not value:
        raise ScheduleError(f"Animation schedule '{field}' is empty.")
    return value


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
        interpolation="linear",
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
    prompt_mode = str(animation.get("prompt_transition", "blend") or "blend").lower()

    positive = resolve_prompt_transition(
        project.get("prompts", {}),
        frame=frame,
        max_frames=max_frames,
        mode=prompt_mode,
    )
    negative = resolve_prompt_transition(
        project.get("negative_prompts", {}),
        frame=frame,
        max_frames=max_frames,
        mode=prompt_mode,
    )

    motion = {
        key.split(".", 1)[1]: _resolve_field(project, key, frame)
        for key in SCHEDULE_FIELDS
        if key.startswith("motion.")
    }

    generation = {
        key.split(".", 1)[1]: _resolve_field(project, key, frame)
        for key in SCHEDULE_FIELDS
        if key.startswith("generation.")
    }
    source_generation = project.get("generation", {})
    generation["sampler"] = str(source_generation.get("sampler", "") or "")
    generation["seed"] = _resolved_seed(project, frame)

    return {
        "frame": frame,
        "max_frames": max_frames,
        "fps": fps,
        "time_seconds": frame / fps,
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
            result = validate_numeric_schedule(
                _schedule_text(project, field),
                max_frames=max_frames,
                seed=expression_seed,
                fps=fps,
                interpolation="linear",
            )
        except ScheduleError as exc:
            result = {
                "valid": False,
                "issues": [{"severity": "error", "message": str(exc)}],
                "keyframes": [],
            }

        fields[field] = result
        for issue in result["issues"]:
            all_issues.append({"field": field, **issue})

    prompt_mode = str(
        project.get("animation", {}).get("prompt_transition", "blend") or "blend"
    ).lower()
    if prompt_mode not in {"blend", "hold"}:
        all_issues.append(
            {
                "field": "animation.prompt_transition",
                "severity": "error",
                "message": f"Unsupported prompt transition mode '{prompt_mode}'.",
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
    validation = validate_numeric_schedule(
        schedule,
        max_frames=max_frames,
        seed=expression_seed,
        fps=fps,
        interpolation="linear",
    )
    if not validation["valid"]:
        first_error = next(
            issue for issue in validation["issues"] if issue["severity"] == "error"
        )
        raise ScheduleError(first_error["message"])

    return {
        "field": field,
        "schedule": schedule,
        "max_frames": max_frames,
        "samples": sample_schedule(
            schedule,
            max_frames=max_frames,
            seed=expression_seed,
            fps=fps,
            interpolation="linear",
            sample_count=sample_count,
        ),
        "keyframes": validation["keyframes"],
        "issues": validation["issues"],
    }

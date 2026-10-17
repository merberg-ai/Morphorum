"""Read-only pre-render checks against the current animation generation backend.

The report is advisory to the browser. The normal render submit path retains
its own authoritative validation; this module never enqueues or saves a job.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .animation_hybrid_render import HybridRenderError, validate_hybrid_composite
from .camera_safety import camera_motion_advisories
from .animation_render import MAX_RENDER_FRAMES
from .animation_resolution import (
    project_schedule_series,
    resolve_project_frame,
    validate_project_schedules,
)
from .generation import (
    FAMILY_IMAGE_EXTENSIONS,
    SUPPORTED_FAMILIES,
    generation_manager,
)
from .managed_models import ManagedModelManager
from .model_index import get_model
from .schedules import ScheduleError


def check_animation_render_preflight(
    project: dict[str, Any], source_path: Path,
) -> dict[str, Any]:
    """Validate a proposed render without modifying project files or GPU state."""
    issues: list[dict[str, str]] = []

    def add(severity: str, field: str, message: str, action: str = "editor") -> None:
        issues.append({
            "severity": severity, "field": field, "message": str(message),
            "action": action,
        })

    animation = project.get("animation") or {}
    generation = project.get("generation") or {}
    total = int(animation.get("max_frames", 0))
    width, height = int(animation.get("width", 0)), int(animation.get("height", 0))
    start_mode = str(animation.get("start_mode") or "prompt").lower()
    hybrid_enabled = bool((project.get("hybrid") or {}).get("enabled"))

    if total < 1 or total > MAX_RENDER_FRAMES:
        add("error", "animation.max_frames",
            f"Render supports 1 to {MAX_RENDER_FRAMES} frames. Change Max frames.")
    if start_mode not in {"source", "prompt"}:
        add("error", "animation.start_mode", "Choose Prompt or Starting Image for frame 0.")
    if start_mode == "source" and not hybrid_enabled and not source_path.is_file():
        add("error", "animation.source_image",
            "Starting Image mode requires an uploaded source image. Upload one in Project Editor.")

    if width < 64 or width > 4096 or height < 64 or height > 4096:
        add("error", "animation.width",
            "Output width and height must each be between 64 and 4096 pixels.")

    try:
        validate_hybrid_composite(project)
    except (HybridRenderError, ScheduleError, TypeError, ValueError) as exc:
        add("error", "hybrid.composite_opacity", str(exc))

    schedules_valid = True
    try:
        validation = validate_project_schedules(project)
        schedules_valid = bool(validation["valid"])
        for entry in validation.get("issues", []):
            add(str(entry.get("severity") or "warning"),
                str(entry.get("field") or "tracks"),
                str(entry.get("message") or "Invalid animation schedule."))
    except (ScheduleError, TypeError, ValueError) as exc:
        schedules_valid = False
        add("error", "tracks", str(exc))

    model_id = str((project.get("model") or {}).get("model_id") or "").strip()
    model = get_model(model_id) if model_id else None
    model_name = str(model.get("name") or model_id) if model else ""
    family = str(model.get("family") or "").lower() if model else ""
    capability: dict[str, Any] = {}
    if not model:
        add("error", "model.model_id",
            "Choose an indexed animation checkpoint. Open Models and scan or repair its folder.",
            "models")
    elif model.get("kind") != "checkpoints":
        add("error", "model.model_id", "Select a checkpoint, not a LoRA.", "models")
    elif family not in SUPPORTED_FAMILIES:
        add("error", "model.family",
            f"Model family '{family or 'unknown'}' is unsupported. Choose SDXL, Flux, or Z-Image.",
            "models")
    else:
        capability = generation_manager._effective_capability(model)
        declared_family = str((project.get("model") or {}).get("family") or "").lower()
        if declared_family and declared_family != family:
            add("error", "model.family",
                "The saved project model family does not match the indexed checkpoint. "
                "Reselect the correct checkpoint and save the project.", "models")
        model_path = Path(str(model.get("path") or ""))
        if family == "zimage":
            if (model.get("source") != "managed" or not model_path.is_dir()
                    or not ManagedModelManager._installed(model_path)):
                add("error", "model.model_id",
                    "The managed Z-Image package is missing or incomplete. Repair it in Models.",
                    "models")
        elif not model_path.is_file():
            add("error", "model.model_id",
                "The indexed checkpoint file no longer exists. Verify its directory and rescan Models.",
                "models")
        elif model_path.suffix.lower() not in FAMILY_IMAGE_EXTENSIONS.get(family, set()):
            add("error", "model.model_id",
                "This indexed checkpoint format cannot be loaded by the selected generation adapter.",
                "models")

        divisor = 16 if family in {"flux", "zimage"} else 8
        if 64 <= width <= 4096 and 64 <= height <= 4096:
            if width % divisor or height % divisor:
                add("error", "animation.width",
                    f"{capability.get('label', family)} requires dimensions divisible by {divisor}.")

        sampler = str(generation.get("sampler") or "")
        choices = {str(item.get("id")) for item in
                   capability.get("samplers", {}).get("options", [])
                   if isinstance(item, dict) and item.get("id")}
        if sampler not in choices:
            add("error", "generation.sampler",
                f"Sampler '{sampler or 'none'}' is unavailable for {capability.get('label', family)}. "
                "Select a supported sampler in Generation State.")

        if family == "sdxl":
            schedule_type = str(generation.get("schedule_type") or "normal").lower()
            schedule_options = capability.get("schedule_types", {}).get("options", [])
            supported_schedules = {
                str(item.get("id")) for item in schedule_options
                if isinstance(item, dict) and item.get("id")
            }
            if schedule_type not in supported_schedules:
                add("error", "generation.schedule_type",
                    f"Schedule Type '{schedule_type}' is unavailable for SDXL. "
                    "Choose a supported schedule in Generation State.")
            elif sampler == "ddim" and schedule_type != "normal":
                add("error", "generation.schedule_type",
                    "DDIM supports only Normal scheduling. Change the schedule or sampler.")
            elif schedule_type == "trailing" and sampler not in {
                "euler", "euler_a", "dpmpp_2m", "dpmpp_2m_sde", "lms", "heun", "unipc"
            }:
                add("error", "generation.schedule_type",
                    "Trailing spacing is not supported for this SDXL sampler.")
            elif schedule_type in {"exponential", "beta"} and sampler not in {
                "euler", "dpmpp_2m", "dpmpp_2m_sde", "unipc"
            }:
                add("error", "generation.schedule_type",
                    "The selected SDXL sampler does not support this schedule.")

    checked_frames = 0
    if schedules_valid and 1 <= total <= MAX_RENDER_FRAMES:
        # The same resolver used by the render pipeline handles timeline
        # interpolation and formula expressions. Large projects use an even,
        # explicitly disclosed sample; rendering rechecks every actual frame.
        limit = min(total, 500)
        series: dict[str, list[dict[str, Any]]] = {}
        for field in ("generation.steps", "generation.guidance"):
            try:
                series[field] = project_schedule_series(
                    project, field, sample_count=limit,
                )["samples"]
            except (ScheduleError, TypeError, ValueError) as exc:
                add("error", field, str(exc))
        if series:
            checked_frames = max(len(samples) for samples in series.values())
        if capability and len(series) == 2:
            for field, key in (("generation.steps", "steps"),
                               ("generation.guidance", "guidance")):
                config = capability.get(key, {})
                low = float(config.get("min", 1 if key == "steps" else 0))
                high = float(config.get("max", 150 if key == "steps" else 30))
                for sample in series[field]:
                    value, frame = float(sample["value"]), int(sample["frame"])
                    if not low <= value <= high:
                        add("error", field,
                            f"Frame {frame}: {key.capitalize()} {value:g} is outside "
                            f"{low:g}–{high:g} for {capability.get('label', family)}.")
                        break
        if start_mode == "prompt" and model is not None:
            try:
                first = resolve_project_frame(project, 0)
                positive = first.get("prompts", {}).get("positive", {})
                if not str(positive.get("from_text") or
                           positive.get("to_text") or "").strip():
                    add("error", "tracks.prompts.positive",
                        "Frame 0 needs a positive prompt in Prompt start mode.")
            except (ScheduleError, ValueError, TypeError) as exc:
                add("error", "tracks.prompts.positive", str(exc))
        if total > checked_frames:
            add("warning", "generation",
                f"Checked {checked_frames} of {total} frames for steps and guidance. "
                "Other frames are checked during generation; preview a short run first.")

    camera_safety = {"sampled_frames": 0, "total_frames": total,
                     "issues": [], "basis": "not-applicable"}
    if schedules_valid and str(animation.get("mode") or "2d").lower() == "3d":
        camera_safety = camera_motion_advisories(project)
        issues.extend(camera_safety["issues"])

    return {
        "camera_safety": camera_safety,
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "issues": issues,
        "errors": sum(item["severity"] == "error" for item in issues),
        "warnings": sum(item["severity"] == "warning" for item in issues),
        "checked_frames": checked_frames,
        "total_frames": total,
        "model_name": model_name,
        "model_family": family,
    }

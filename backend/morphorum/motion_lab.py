"""Morphorum Motion Lab: deterministic, render-independent six-axis authoring.

Motion Lab compiles per-frame native 3D camera *increments* into existing
animation tracks. No separate diffusion/motion renderer is introduced.
"""
from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .animation_timeline import numeric_track
from .schedules import ScheduleError, resolve_numeric_schedule

AXES = (
    "translation_x", "translation_y", "translation_z",
    "rotation_x", "rotation_y", "rotation_z",
)
PRESETS = (
    "still", "gentle-drift", "wave", "spiral", "figure-eight",
    "rocking", "push-in", "pull-out",
)
PRESET_AXES = {
    "still": AXES,
    "gentle-drift": ("translation_x", "translation_y", "rotation_y"),
    "wave": ("translation_x", "translation_y", "rotation_y"),
    "spiral": ("translation_x", "translation_y", "translation_z", "rotation_z"),
    "figure-eight": ("translation_x", "translation_y"),
    "rocking": ("rotation_x", "rotation_z"),
    "push-in": ("translation_z",),
    "pull-out": ("translation_z",),
}
# Native Morphorum scene units per rendered frame, and degrees/frame.
AMPLITUDE = {
    "translation_x": 0.018,
    "translation_y": 0.018,
    "translation_z": 0.025,
    "rotation_x": 0.4,
    "rotation_y": 0.4,
    "rotation_z": 0.4,
}
DEFAULT_LIMITS = {
    "translation_x": 0.12, "translation_y": 0.12, "translation_z": 0.12,
    "rotation_x": 2.0, "rotation_y": 2.0, "rotation_z": 2.0,
}
MAX_LAYERS = 24
MAX_COMPOSE_FRAMES = 3000


class MotionLabError(ValueError):
    pass


def _number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise MotionLabError(f"{label} must be a number.")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise MotionLabError(f"{label} must be a number.") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise MotionLabError(f"{label} must be between {low:g} and {high:g}.")
    return result


def _integer(value: Any, label: str, low: int, high: int) -> int:
    number = _number(value, label, low, high)
    if not number.is_integer():
        raise MotionLabError(f"{label} must be a whole number.")
    return int(number)


def _frames(project: dict[str, Any]) -> tuple[int, float]:
    animation = project.get("animation") or {}
    count = _integer(animation.get("max_frames", 120), "Frame count", 1, MAX_COMPOSE_FRAMES)
    fps = _number(animation.get("fps", 24), "FPS", 1, 240)
    return count, fps


def normalize_layers(layers: Any, project: dict[str, Any]) -> list[dict[str, Any]]:
    count, _fps = _frames(project)
    if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
        raise MotionLabError(f"Motion layers must be a list of at most {MAX_LAYERS} items.")
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(layers):
        if not isinstance(raw, dict):
            raise MotionLabError(f"Layer {index + 1} must be an object.")
        preset = str(raw.get("preset", "")).strip().lower()
        if preset not in PRESETS:
            raise MotionLabError(f"Layer {index + 1} has an unsupported preset: {preset}.")
        mode = str(raw.get("blend", "add")).strip().lower()
        if mode not in {"add", "replace"}:
            raise MotionLabError(f"Layer {index + 1} blend must be add or replace.")
        start = _integer(raw.get("start_frame", 0), "Layer start", 0, count - 1)
        end = _integer(raw.get("end_frame", count), "Layer end", start + 1, count)
        output.append({
            "id": str(raw.get("id") or f"layer-{index + 1}")[:64],
            "type": "preset",
            "preset": preset,
            "enabled": raw.get("enabled", True) is True,
            "blend": mode,
            "start_frame": start,
            "end_frame": end,
            "strength": _number(raw.get("strength", 0.5), "Layer strength", 0, 1),
            "cycle_seconds": _number(raw.get("cycle_seconds", 8), "Cycle seconds", 0.2, 600),
            "fade_seconds": _number(raw.get("fade_seconds", 0.5), "Fade seconds", 0, 120),
        })
    if len({item["id"] for item in output}) != len(output):
        raise MotionLabError("Motion layer IDs must be unique.")
    return output


def normalize_motion_lab(raw: Any, project: dict[str, Any]) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    limits_in = data.get("limits", {})
    if not isinstance(limits_in, dict):
        raise MotionLabError("Motion Lab limits must be an object.")
    limits = {
        axis: _number(limits_in.get(axis, value), axis + " limit", 0.00001, 30)
        for axis, value in DEFAULT_LIMITS.items()
    }
    base = data.get("base_tracks")
    applied = data.get("last_applied_tracks")
    def _snapshot(value, field):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != set(AXES):
            raise MotionLabError(f"Motion Lab {field} must contain all six axes.")
        snapshot = {}
        for axis in AXES:
            track = value[axis]
            if not isinstance(track, dict):
                raise MotionLabError(f"Invalid {field} entry for {axis}.")
            schedule = str(track.get("schedule") or "").strip()
            interp = str(track.get("interpolation") or "linear").strip()
            if not schedule or len(schedule) > 250000 or interp not in {"linear", "hold"}:
                raise MotionLabError(f"Invalid {field} schedule for {axis}.")
            snapshot[axis] = {"schedule": schedule, "interpolation": interp}
        return snapshot
    return {
        "schema_version": 1,
        "layers": normalize_layers(data.get("layers", []), project),
        "limits": limits,
        "base_tracks": _snapshot(base, "base_tracks"),
        "last_applied_tracks": _snapshot(applied, "last_applied_tracks"),
    }


def _camera_snapshot(project: dict[str, Any]) -> dict[str, dict[str, str]]:
    result = {}
    for axis in AXES:
        native = numeric_track(project, "camera_3d." + axis)
        result[axis] = {
            "schedule": str(native["schedule"]),
            "interpolation": str(native.get("interpolation") or "linear"),
        }
    return result


def _preset_frame(layer: dict[str, Any], frame: int, fps: float) -> dict[str, float]:
    start = layer["start_frame"]
    end = layer["end_frame"]
    if frame < start or frame >= end or not layer["enabled"]:
        return {}
    name = layer["preset"]
    t = (frame - start) / fps
    cycle = layer["cycle_seconds"]
    phase = 2 * math.pi * t / cycle
    amp = AMPLITUDE
    s = layer["strength"]
    values = {axis: 0.0 for axis in PRESET_AXES[name]}
    if name == "gentle-drift":
        values.update(translation_x=amp["translation_x"] * .35,
                      translation_y=amp["translation_y"] * .2,
                      rotation_y=amp["rotation_y"] * .35 * math.sin(phase))
    elif name == "wave":
        values.update(translation_x=amp["translation_x"] * math.sin(phase),
                      translation_y=amp["translation_y"] * .5 * math.cos(phase),
                      rotation_y=amp["rotation_y"] * .6 * math.sin(phase))
    elif name == "spiral":
        # A real helical move: circular X/Y velocity + continuous forward
        # travel and roll. Use the full axis amplitudes rather than the old
        # 0.55/0.3 multipliers that were barely visible in short previews.
        values.update(translation_x=amp["translation_x"] * 1.6 * math.cos(phase),
                      translation_y=amp["translation_y"] * 1.6 * math.sin(phase),
                      translation_z=amp["translation_z"] * .9,
                      rotation_z=amp["rotation_z"] * 1.4)
    elif name == "figure-eight":
        values.update(translation_x=amp["translation_x"] * math.sin(phase),
                      translation_y=amp["translation_y"] * math.sin(phase * 2))
    elif name == "rocking":
        values.update(rotation_x=amp["rotation_x"] * .6 * math.sin(phase),
                      rotation_z=amp["rotation_z"] * math.sin(phase))
    elif name == "push-in":
        values["translation_z"] = amp["translation_z"]
    elif name == "pull-out":
        values["translation_z"] = -amp["translation_z"]
    fade = layer["fade_seconds"]
    if fade > 0:
        remaining = max(0., (end - 1 - frame) / fps)
        enter = min(1., t / fade)
        leave = min(1., remaining / fade)
        ramp = min(enter, leave)
        envelope = .5 - .5 * math.cos(math.pi * ramp)
    else:
        envelope = 1.
    # Never jump on frame zero: Morphorum's initial image is not camera warped.
    if frame == 0:
        envelope = 0.
    return {axis: value * s * envelope for axis, value in values.items()}


def compile_motion_lab(
    project: dict[str, Any],
    *,
    layers: list[dict[str, Any]] | None = None,
    conflict_policy: str = "reject",
    include_series: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile draft layers to real camera_3d tracks, without saving anything.

    A prior applied snapshot protects hand-edited timeline tracks from
    accidental overwrite. Re-application starts from the original base.
    Preview can opt in to using newly edited camera tracks as a temporary
    base, and Apply requires a separate explicit rebase confirmation.
    The returned copy is safe to pass to save_animation_project.
    """
    project = deepcopy(project)
    if str(project.get("animation", {}).get("mode") or "2d").lower() != "3d":
        raise MotionLabError("Motion Lab six-axis presets require 3D animation mode.")
    count, fps = _frames(project)
    data = deepcopy(project.get("motion_lab") or {})
    if layers is not None:
        data["layers"] = layers
    lab = normalize_motion_lab(data, project)
    if conflict_policy not in {"reject", "use-current"}:
        raise MotionLabError("Unknown Motion Lab camera conflict policy.")
    current = _camera_snapshot(project)
    last = lab["last_applied_tracks"]
    camera_changed = last is not None and current != last
    if camera_changed and conflict_policy == "reject":
        raise MotionLabError(
            "Camera schedules changed since Motion Lab last applied them. "
            "Confirm 'Use current camera as base' before replacing existing motion."
        )
    # A rebase treats the user's CURRENT hand-edited timeline as the new base.
    # Preview never saves it; explicit Apply can persist the rebased result.
    base = current if camera_changed else (lab["base_tracks"] or current)
    if not lab["layers"]:
        raise MotionLabError("Add at least one Motion Lab preset layer.")
    seed = max(0, int((project.get("generation") or {}).get("seed", -1)))
    signals: dict[str, list[float]] = {}
    for axis, track in base.items():
        try:
            signals[axis] = [
                float(resolve_numeric_schedule(
                    track["schedule"], frame=frame, max_frames=count,
                    fps=fps, seed=seed, interpolation=track["interpolation"],
                )) for frame in range(count)
            ]
        except (ScheduleError, ValueError, OverflowError) as exc:
            raise MotionLabError(f"Cannot resolve base camera {axis}: {exc}") from exc
        if not all(math.isfinite(x) for x in signals[axis]):
            raise MotionLabError(f"Base camera {axis} contains invalid values.")
    for layer in lab["layers"]:
        if not layer["enabled"]:
            continue
        for frame in range(layer["start_frame"], layer["end_frame"]):
            values = _preset_frame(layer, frame, fps)
            for axis, delta in values.items():
                if layer["blend"] == "replace":
                    signals[axis][frame] = delta
                else:
                    signals[axis][frame] += delta
    # Per-axis limits are useful safeguards, not a guarantee of perfect visual
    # quality. Report every limited axis so the editor can show diagnostics.
    limited: dict[str, int] = {}
    for axis, samples in signals.items():
        limit = lab["limits"][axis]
        limited[axis] = sum(1 for v in samples if abs(v) > limit)
        signals[axis] = [max(-limit, min(limit, v)) for v in samples]
    tracks = project["tracks"]["camera_3d"]
    applied = {}
    for axis, samples in signals.items():
        schedule = ", ".join(f"{frame}:({value:.9g})" for frame, value in enumerate(samples))
        tracks[axis]["schedule"] = schedule
        tracks[axis]["interpolation"] = "linear"
        project["camera_3d"][axis] = schedule
        applied[axis] = {"schedule": schedule, "interpolation": "linear"}
    lab["base_tracks"] = base
    lab["last_applied_tracks"] = applied
    project["motion_lab"] = lab
    result = {
        "frames": count, "fps": fps, "layer_count": len(lab["layers"]),
        "camera_changed": camera_changed,
        "rebased": camera_changed and conflict_policy == "use-current",
        "limited": {axis: count for axis, count in limited.items() if count},
        "samples": [
            {"frame": frame, **{axis: signals[axis][frame] for axis in AXES}}
            for frame in sorted(set([0, count - 1] + list(range(0, count, max(1, count // 36)))))
        ],
    }
    # ML1: expose exactly the six resolved, clipped native per-frame values
    # for browser-side curves and camera-path visualizations. This never
    # triggers GPU/depth inference and is only requested for draft preview.
    if include_series:
        result["series"] = {
            axis: [round(value, 9) for value in signals[axis]]
            for axis in AXES
        }
    return project, result

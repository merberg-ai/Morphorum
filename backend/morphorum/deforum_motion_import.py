"""Read-only Deforum Motion Studio/Deforum six-axis import inspection (DMI1).

Accepts JSON Deforum settings, never reads soundtrack paths or executes formulas.
Preview values are sparse numeric schedule interpolations, NOT a project mutation.
"""
from __future__ import annotations

import math
import re
import hashlib
from copy import deepcopy
from typing import Any

from .deforum_import import DeforumImportError, parse_deforum_source
from .motion_lab import AXES
from .animation_projects import save_animation_project
from .animation_resolution import validate_project_schedules

SOURCE_AXIS = {
    "translation_x": "translation_x", "translation_y": "translation_y",
    "translation_z": "translation_z", "rotation_3d_x": "rotation_x",
    "rotation_3d_y": "rotation_y", "rotation_3d_z": "rotation_z",
}
_KEYFRAME = re.compile(r"\s*(\d+)\s*:\s*\(\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*\)\s*")
_MAX_SOURCE_FRAMES = 30000

# Deforum anim_frame_warp_3d translates by 1/200 with X/Z inversions.
# Morphorum uses different depth scene units, so this is an initial mapping.
DEFORUM_TRANSLATION = {"translation_x": -0.005, "translation_y": 0.005, "translation_z": -0.005}


def conversion_options(raw: Any = None) -> dict[str, Any]:
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - {"mode", "translation_strength", "rotation_strength"}:
        raise DeforumImportError("Invalid motion conversion options.")
    mode = raw.get("mode", "deforum")
    if mode not in {"deforum", "raw"}:
        raise DeforumImportError("Conversion mode must be deforum or raw.")
    result = {"mode": mode}
    for key in ("translation_strength", "rotation_strength"):
        value = raw.get(key, 1.0)
        if isinstance(value, bool):
            raise DeforumImportError(f"{key} must be between 0 and 2.")
        try:
            value = float(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise DeforumImportError(f"{key} must be between 0 and 2.") from exc
        if not math.isfinite(value) or not 0 <= value <= 2:
            raise DeforumImportError(f"{key} must be between 0 and 2.")
        result[key] = value
    return result


def converted_schedule(raw: str, axis: str, options: dict[str, Any], frames: int) -> str:
    multiplier = DEFORUM_TRANSLATION.get(axis, 1.0) if options["mode"] == "deforum" else 1.0
    multiplier *= options["translation_strength"] if axis.startswith("translation") else options["rotation_strength"]
    return ",".join(
        f"{frame}:({format(value * multiplier, '.12g')})"
        for frame, value in _parse_schedule(raw, axis, frames)
    )


def conversion_digest(options: dict[str, Any]) -> str:
    import json
    return hashlib.sha256(
        json.dumps(options, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()



def _positive_number(raw: Any, name: str, maximum: float) -> float:
    try:
        if isinstance(raw, bool) or raw is None:
            raise ValueError()
        value = float(raw)
    except (ValueError, TypeError, OverflowError) as exc:
        raise DeforumImportError(f"{name} must be a finite positive number.") from exc
    if not math.isfinite(value) or not 0 < value <= maximum:
        raise DeforumImportError(f"{name} must be a finite positive number up to {maximum:g}.")
    return value


def _parse_schedule(raw: Any, name: str, frames: int) -> list[tuple[int, float]]:
    if not isinstance(raw, str) or len(raw) > 250000:
        raise DeforumImportError(f"{name}: expected a bounded numeric keyframe schedule.")
    if not raw.strip():
        raise DeforumImportError(f"{name}: empty camera schedule.")
    results: list[tuple[int, float]] = []
    for item in raw.split(","):
        match = _KEYFRAME.fullmatch(item)
        if not match:
            raise DeforumImportError(
                f"{name}: only literal numeric 'frame:(value)' keyframes are supported; "
                "expressions are not executed."
            )
        frame, value = int(match.group(1)), float(match.group(2))
        if frame >= frames or not math.isfinite(value) or abs(value) > 10000:
            raise DeforumImportError(f"{name}: out-of-range frame or nonfinite/excessive value.")
        if results and frame <= results[-1][0]:
            raise DeforumImportError(f"{name}: keyframes must be strictly increasing.")
        results.append((frame, value))
        if len(results) > 3000:
            raise DeforumImportError(f"{name}: too many keyframes.")
    if results[0][0] != 0:
        raise DeforumImportError(f"{name}: motion schedules must begin at frame zero.")
    return results


def _value_at(keys: list[tuple[int, float]], frame: float) -> float:
    if frame <= keys[0][0]:
        return keys[0][1]
    for index in range(1, len(keys)):
        a, av = keys[index - 1]
        b, bv = keys[index]
        if frame <= b:
            return av + (bv - av) * (frame - a) / (b - a)
    return keys[-1][1]


def preview_motion_settings(
    content: Any, *, filename: str = "", project: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = parse_deforum_source(content, filename=filename)
    source_frames = _positive_number(settings.get("max_frames"), "max_frames", _MAX_SOURCE_FRAMES)
    if not source_frames.is_integer() or source_frames < 2:
        raise DeforumImportError("max_frames must be an integer of at least 2.")
    frames = int(source_frames)
    fps = _positive_number(settings.get("fps"), "fps", 240)
    if str(settings.get("animation_mode", "3D")).strip().lower() != "3d":
        raise DeforumImportError("The six-axis motion importer requires Deforum 3D settings.")
    schedules: dict[str, list[tuple[int, float]]] = {}
    missing: list[str] = []
    for source_axis, axis in SOURCE_AXIS.items():
        if source_axis not in settings:
            missing.append(source_axis)
            schedules[axis] = [(0, 0.0)]
        else:
            schedules[axis] = _parse_schedule(settings[source_axis], source_axis, frames)
    if len(missing) == len(SOURCE_AXIS):
        raise DeforumImportError("No six-axis Deforum camera schedules were found.")
    cadence = settings.get("diffusion_cadence", "1")
    if isinstance(cadence, (int, float)) and not isinstance(cadence, bool):
        cadence = str(cadence)
    if not isinstance(cadence, str) or len(cadence) > 250000:
        raise DeforumImportError("diffusion_cadence is invalid.")
    if cadence.strip().isdigit():
        cadence_keys = [(0, float(cadence.strip()))]
    else:
        cadence_keys = _parse_schedule(cadence, "diffusion_cadence", frames)
    if any(v != int(v) or v < 1 or v > 30 for _, v in cadence_keys):
        raise DeforumImportError("diffusion_cadence must use integers from 1 to 30.")
    target = project or {}
    animation = target.get("animation") or {}
    current_fps = float(animation.get("fps") or fps)
    current_frames = int(animation.get("max_frames") or frames)
    raw_current_cadence = (target.get("cadence") or {}).get("diffusion", "0:(1)")
    try:
        current_cadence_keys = _parse_schedule(str(raw_current_cadence), "project cadence", current_frames)
        current_cadence = int(current_cadence_keys[0][1]) if len(current_cadence_keys) == 1 else None
    except DeforumImportError:
        current_cadence = None
    source_cadence = int(cadence_keys[0][1]) if len(cadence_keys) == 1 else None
    warnings: list[str] = []
    if missing:
        warnings.append("Missing axes default to zero: " + ", ".join(missing))
    if frames > 3000:
        warnings.append("Source exceeds Morphorum's 3000-frame limit. Motion cannot be applied unchanged.")
    if not math.isclose(current_fps, fps, rel_tol=0, abs_tol=1e-6):
        warnings.append("FPS differs from current project; importing without retiming would alter synchronization.")
    if current_frames != frames:
        warnings.append("Frame count differs from current project; review duration and existing motion before applying.")
    if len(cadence_keys) > 1:
        warnings.append("Source cadence varies across frames; inspect its compatibility with project cadence.")
    if source_cadence is None or current_cadence is None or source_cadence != current_cadence:
        warnings.append("Cadence differs from the project or varies; review before importing.")
    raw_path = settings.get("soundtrack_path")
    if raw_path is not None and not isinstance(raw_path, str):
        raise DeforumImportError("soundtrack_path must be text.")
    # Explicitly expose the embedded reference for display/copy only. Never resolve
    # or open it on the server; importing a settings file grants no file access.
    if raw_path is not None and (len(raw_path) > 4096 or any(ord(c) < 32 for c in raw_path)):
        raise DeforumImportError("soundtrack_path contains invalid characters or is too long.")
    basename = raw_path.replace("\\", "/").split("/")[-1][:160] if raw_path else None
    count = min(frames, 241)
    positions = sorted(set(round(i * (frames - 1) / (count - 1)) for i in range(count)))
    samples = [
        {"frame": frame, "seconds": round(frame / fps, 6),
         **{axis: round(_value_at(keys, frame), 9) for axis, keys in schedules.items()}}
        for frame in positions
    ]
    return {
        "source": {"filename": filename[:160], "fps": fps, "max_frames": frames,
                   "duration_seconds": frames / fps, "cadence": source_cadence,
                   "cadence_keyframes": [{"frame": f, "value": int(v)} for f, v in cadence_keys],
                   "soundtrack_path": raw_path or None,
                   "soundtrack_filename": basename,
                   "soundtrack_attached": bool(raw_path and settings.get("add_soundtrack") == "File")},
        "project_comparison": {"fps": current_fps, "max_frames": current_frames,
                               "duration_seconds": current_frames / current_fps,
                               "fps_matches": math.isclose(current_fps, fps, rel_tol=0, abs_tol=1e-6),
                               "frames_match": current_frames == frames,
                               "cadence": current_cadence,
                               "cadence_matches": source_cadence is not None and source_cadence == current_cadence},
        "axes": {axis: {"source_key": source, "keyframes": len(schedules[axis]),
                       "min": min(v for _, v in schedules[axis]),
                       "max": max(v for _, v in schedules[axis])}
                 for source, axis in SOURCE_AXIS.items()},
        "samples": samples, "warnings": warnings,
        "can_apply_unchanged": frames <= 3000 and not missing and current_frames == frames
            and math.isclose(current_fps, fps, rel_tol=0, abs_tol=1e-6)
            and source_cadence is not None and source_cadence == current_cadence,
        "read_only": True,
    }


def _source_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def prepare_motion_import(
    content: Any, *, filename: str, project: dict[str, Any],
    options: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Preview a copy of the changed project, rejecting unsafe timing conflicts.

    Only six camera schedules are touched. FPS, frame count, cadence, models,
    prompts, audio, Motion Lab layers and all other configuration stay unchanged.
    """
    report = preview_motion_settings(content, filename=filename, project=project)
    if not report["can_apply_unchanged"]:
        raise DeforumImportError(
            "Imported FPS, frames, cadence or axes do not match this project. "
            "Use a matching project for motion-only import; no automatic retiming."
        )
    if str(project.get("animation", {}).get("mode", "")).lower() != "3d":
        raise DeforumImportError("Select a 3D project before importing 3D camera motion.")
    lab = project.get("motion_lab") or {}
    if lab.get("layers") or lab.get("last_applied_tracks"):
        raise DeforumImportError(
            "This project has Motion Lab layers or previously applied motion. "
            "Import into a fresh 3D project to avoid overriding those layers."
        )
    source = parse_deforum_source(content, filename=filename)
    settings = conversion_options(options)
    changed = deepcopy(project)
    for source_axis, target_axis in SOURCE_AXIS.items():
        schedule = converted_schedule(source[source_axis], target_axis, settings, report["source"]["max_frames"])
        changed["tracks"]["camera_3d"][target_axis]["schedule"] = schedule
        changed["tracks"]["camera_3d"][target_axis]["interpolation"] = "linear"
        changed["camera_3d"][target_axis] = schedule
    diagnostics = validate_project_schedules(changed)
    if not diagnostics.get("valid", False):
        raise DeforumImportError(
            "Imported camera schedules failed Morphorum validation; no changes applied."
        )
    report["source_sha256"] = _source_digest(content)
    report["conversion"] = settings
    report["conversion_sha256"] = conversion_digest(settings)
    report["converted_schedules"] = {
        axis: changed["tracks"]["camera_3d"][axis]["schedule"]
        for axis in SOURCE_AXIS.values()
    }
    report["changed_axes"] = list(AXES)
    report["import_mode"] = "replace_camera_only"
    return changed, report


def apply_motion_import(
    project_id: str, content: Any, *, filename: str,
    expected_source_sha256: str, expected_project_sha256: str,
    options: Any = None, expected_conversion_sha256: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Explicitly guarded save, requiring matching source and current project."""
    import json
    from .animation_projects import load_animation_project

    current = load_animation_project(project_id)
    current_digest = hashlib.sha256(
        json.dumps(current, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if current_digest != expected_project_sha256 or _source_digest(content) != expected_source_sha256:
        raise DeforumImportError("Project or import source changed since preview. Preview again.")
    selected = conversion_options(options)
    if conversion_digest(selected) != expected_conversion_sha256:
        raise DeforumImportError("Motion conversion changed since review; review again.")
    candidate, report = prepare_motion_import(content, filename=filename, project=current, options=selected)
    saved = save_animation_project(project_id, candidate, prefer_tracks=True)
    return saved, report

"""Read-only Deforum Motion Studio/Deforum six-axis import inspection (DMI1).

Accepts JSON Deforum settings, never reads soundtrack paths or executes formulas.
Preview values are sparse numeric schedule interpolations, NOT a project mutation.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .deforum_import import DeforumImportError, parse_deforum_source
from .motion_lab import AXES

SOURCE_AXIS = {
    "translation_x": "translation_x", "translation_y": "translation_y",
    "translation_z": "translation_z", "rotation_3d_x": "rotation_x",
    "rotation_3d_y": "rotation_y", "rotation_3d_z": "rotation_z",
}
_KEYFRAME = re.compile(r"\s*(\d+)\s*:\s*\(\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*\)\s*")
_MAX_SOURCE_FRAMES = 30000


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
    # Never return the host's local path; it is metadata, not a usable file locator.
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

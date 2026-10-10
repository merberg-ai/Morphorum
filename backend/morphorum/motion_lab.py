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
MAX_KEYFRAMES_PER_LAYER = 128
MAX_RECORDING_SAMPLES = MAX_COMPOSE_FRAMES
# Dense ML2 rows are device-neutral replay data; source is provenance only.
RECORDING_SOURCES = ("keyboard", "touch", "gamepad", "mixed", "unknown")


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


def _normalize_keyframe_layer(
    raw: dict[str, Any],
    *,
    index: int,
    count: int,
    start: int,
    end: int,
    mode: str,
) -> dict[str, Any]:
    """Validate a sparse, single-axis native velocity keyframe layer."""
    axis = str(raw.get("axis", "")).strip().lower()
    if axis not in AXES:
        raise MotionLabError(f"Layer {index + 1} must specify one of the six camera axes.")
    interpolation = str(raw.get("interpolation", "linear")).strip().lower()
    if interpolation not in {"linear", "hold", "smoothstep", "smootherstep", "cubic"}:
        raise MotionLabError(
            "Curve interpolation must be linear, hold, smoothstep, smootherstep or cubic."
        )
    raw_keys = raw.get("keys", [])
    if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= MAX_KEYFRAMES_PER_LAYER:
        raise MotionLabError(
            f"Curve layer must have 1–{MAX_KEYFRAMES_PER_LAYER} keyframes."
        )
    keys: list[dict[str, Any]] = []
    used: set[int] = set()
    for n, item in enumerate(raw_keys):
        if not isinstance(item, dict):
            raise MotionLabError(f"Keyframe {n + 1} must be an object.")
        frame = _integer(item.get("frame"), "Keyframe position", start, end - 1)
        # Keyframes edit per-render-frame velocity. The first output frame is
        # unwarped, so a nonzero frame-0 delta would be misleading.
        value = _number(item.get("value"), "Keyframe value", -30, 30)
        if frame == 0 and value != 0:
            raise MotionLabError("Frame 0 must have zero camera movement.")
        if frame in used:
            raise MotionLabError(f"Duplicate keyframe at frame {frame}.")
        used.add(frame)
        keys.append({"frame": frame, "value": value})
    keys.sort(key=lambda key: key["frame"])
    return {
        "id": str(raw.get("id") or f"layer-{index + 1}")[:64],
        "type": "keyframes",
        "axis": axis,
        "keys": keys,
        "interpolation": interpolation,
        "enabled": raw.get("enabled", True) is True,
        "blend": mode,
        "start_frame": start,
        "end_frame": end,
    }


def _normalize_recording_layer(
    raw: dict[str, Any],
    *,
    index: int,
    count: int,
    start: int,
    end: int,
    mode: str,
    fps: float,
) -> dict[str, Any]:
    """Validate a dense, frame-aligned six-axis recording take.

    Samples are always stored in canonical AXES order. The axes list controls
    which values participate in composition, so Replace never zeros unrelated
    authored camera axes. Recording FPS is intentionally locked to project FPS:
    native Motion Lab values are per-frame deltas, and silent resampling would
    change travel distance and rotation semantics.
    """
    capture_version = _integer(
        raw.get("capture_version", 1), "Recording capture version", 1, 1,
    )
    capture_fps = _number(raw.get("fps", fps), "Recording FPS", 1, 240)
    if not math.isclose(capture_fps, fps, rel_tol=0.0, abs_tol=1e-9):
        raise MotionLabError(
            f"Recording FPS {capture_fps:g} does not match project FPS {fps:g}; "
            "retime the take explicitly or re-record it."
        )
    source = str(raw.get("source") or "unknown").strip().lower()
    if source not in RECORDING_SOURCES:
        raise MotionLabError(
            "Recording source must be keyboard, touch, gamepad, mixed or unknown."
        )
    raw_axes = raw.get("axes", list(AXES))
    if not isinstance(raw_axes, list) or not 1 <= len(raw_axes) <= len(AXES):
        raise MotionLabError("Recording must arm at least one axis.")
    axes = [str(axis).strip().lower() for axis in raw_axes]
    if any(axis not in AXES for axis in axes):
        raise MotionLabError("Recording axes must use the six camera axes.")
    if len(set(axes)) != len(axes):
        raise MotionLabError("Recording axes must be unique.")

    raw_samples = raw.get("samples")
    expected = end - start
    if not isinstance(raw_samples, list):
        raise MotionLabError("Recording sample rows must be a list.")
    if len(raw_samples) != expected or len(raw_samples) > MAX_RECORDING_SAMPLES:
        raise MotionLabError(
            f"Recording must contain exactly one sample per frame "
            f"({expected} sample rows for frames {start}–{end - 1})."
        )
    armed = set(axes)
    samples: list[list[float]] = []
    for offset, row in enumerate(raw_samples):
        if not isinstance(row, list) or len(row) != len(AXES):
            raise MotionLabError(
                f"Recording sample {offset + 1} must contain six numeric values."
            )
        values = [
            _number(value, f"Recording sample {offset + 1} {AXES[n]}", -30, 30)
            for n, value in enumerate(row)
        ]
        frame = start + offset
        if frame == 0 and any(value != 0 for value in values):
            raise MotionLabError("Frame 0 must have zero camera movement.")
        for n, axis in enumerate(AXES):
            if axis not in armed and values[n] != 0:
                raise MotionLabError(
                    f"Recording sample {offset + 1} has movement on unarmed axis {axis}."
                )
        samples.append(values)
    name = str(raw.get("name") or f"Recorded take {index + 1}").strip()[:96]
    if not name:
        name = f"Recorded take {index + 1}"
    return {
        "id": str(raw.get("id") or f"layer-{index + 1}")[:64],
        "type": "recording",
        "name": name,
        "enabled": raw.get("enabled", True) is True,
        "blend": mode,
        "start_frame": start,
        "end_frame": end,
        "fps": capture_fps,
        "source": source,
        "capture_version": capture_version,
        "axes": axes,
        "samples": samples,
    }


def _normalize_audio_layer(
    raw: dict[str, Any], *, index: int, start: int, end: int,
    mode: str, fps: float,
) -> dict[str, Any]:
    """Validate preanalyzed audio values as native velocity data.

    Audio analysis must happen through the managed project upload endpoint.
    An embedded bounded envelope makes the layer deterministic after reload.
    """
    from .audio_motion import balanced_pulses, AudioMotionError, onset_strength
    axis = str(raw.get("axis") or "translation_z").lower()
    if axis not in AXES:
        raise MotionLabError("Audio layer must select a native camera axis.")
    source_hash = str(raw.get("sha256") or "")
    if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
        raise MotionLabError("Audio layer requires an SHA256 source hash.")
    audio_fps = _number(raw.get("fps"), "Audio analysis FPS", 1, 240)
    if not math.isclose(audio_fps, fps, abs_tol=1e-9, rel_tol=0):
        raise MotionLabError("Audio analysis FPS differs from project FPS; reanalyze the audio.")
    values = raw.get("envelope")
    if not isinstance(values, list) or len(values) != end - start:
        raise MotionLabError("Audio envelope must provide one sample per layer frame.")
    envelope = [_number(v, "Audio envelope sample", 0, 1) for v in values]
    detection = str(raw.get("detection", "level")).lower()
    if detection not in ("level", "transient"):
        raise MotionLabError("Audio detection must be level or transient.")
    band = str(raw.get("band", "fullband")).lower()
    if band not in ("fullband", "kick", "bass", "snare", "highs"):
        raise MotionLabError("Unsupported audio frequency band.")
    sensitivity = _number(raw.get("sensitivity", .35), "Transient sensitivity", 0, 1)
    threshold = _number(raw.get("threshold", .25), "Audio threshold", 0, 1)
    distance = _number(raw.get("distance", .04), "Audio pulse distance", 0, 1)
    attack = _integer(raw.get("attack_frames", 1), "Audio attack frames", 1, 120)
    release = _integer(raw.get("release_frames", 3), "Audio release frames", 1, 120)
    cooldown = _integer(raw.get("cooldown_frames", 3), "Audio cooldown frames", 0, 120)
    offset = _integer(raw.get("offset_frames", 0), "Audio offset frames", -3000, 3000)
    try:
        pulses = balanced_pulses(
            onset_strength(envelope, sensitivity) if detection == "transient" else envelope,\n            threshold=threshold, distance=distance,
            attack_frames=attack, release_frames=release,
            cooldown_frames=cooldown, offset_frames=offset,
        )
    except AudioMotionError as exc:
        raise MotionLabError(str(exc)) from exc
    return {
        "id": str(raw.get("id") or f"layer-{index + 1}")[:64],
        "type": "audio", "enabled": raw.get("enabled", True) is True,
        "blend": mode, "start_frame": start, "end_frame": end,
        "name": str(raw.get("name") or "Audio pulses")[:96],
        "axis": axis, "fps": audio_fps, "sha256": source_hash,
        "envelope": envelope, "threshold": threshold, "distance": distance,\n        "band": band, "detection": detection, "sensitivity": sensitivity,
        "attack_frames": attack, "release_frames": release,
        "cooldown_frames": cooldown, "offset_frames": offset,
        "pulses": pulses,
    }


def normalize_layers(layers: Any, project: dict[str, Any]) -> list[dict[str, Any]]:
    count, fps = _frames(project)
    if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
        raise MotionLabError(f"Motion layers must be a list of at most {MAX_LAYERS} items.")
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(layers):
        if not isinstance(raw, dict):
            raise MotionLabError(f"Layer {index + 1} must be an object.")
        mode = str(raw.get("blend", "add")).strip().lower()
        if mode not in {"add", "replace"}:
            raise MotionLabError(f"Layer {index + 1} blend must be add or replace.")
        start = _integer(raw.get("start_frame", 0), "Layer start", 0, count - 1)
        end = _integer(raw.get("end_frame", count), "Layer end", start + 1, count)
        kind = str(raw.get("type", "preset")).strip().lower()
        if kind == "keyframes":
            output.append(_normalize_keyframe_layer(
                raw, index=index, count=count, start=start, end=end, mode=mode,
            ))
            continue
        if kind == "audio":
            output.append(_normalize_audio_layer(
                raw, index=index, start=start, end=end, mode=mode, fps=fps,
            ))
            continue
        if kind == "recording":
            output.append(_normalize_recording_layer(
                raw, index=index, count=count, start=start, end=end, mode=mode, fps=fps,
            ))
            continue
        if kind != "preset":
            raise MotionLabError(f"Layer {index + 1} has an unsupported type: {kind}.")
        preset = str(raw.get("preset", "")).strip().lower()
        if preset not in PRESETS:
            raise MotionLabError(f"Layer {index + 1} has an unsupported preset: {preset}.")
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


def _monotone_tangent(points: list[tuple[int, float]], index: int) -> float:
    """PCHIP-style shape-preserving derivative at a nonuniform keyframe."""
    length = len(points)
    if length <= 1:
        return 0.0
    if length == 2:
        return (points[1][1] - points[0][1]) / (points[1][0] - points[0][0])

    def segment(i: int) -> tuple[float, float]:
        h = float(points[i + 1][0] - points[i][0])
        return h, (points[i + 1][1] - points[i][1]) / h

    if index in (0, length - 1):
        if index == 0:
            h0, d0 = segment(0)
            h1, d1 = segment(1)
        else:
            h0, d0 = segment(length - 2)
            h1, d1 = segment(length - 3)
        derivative = ((2.0 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if d0 == 0 or derivative * d0 <= 0:
            return 0.0
        if d0 * d1 < 0 and abs(derivative) > 3.0 * abs(d0):
            return 3.0 * d0
        return derivative

    h0, d0 = segment(index - 1)
    h1, d1 = segment(index)
    if d0 * d1 <= 0:
        return 0.0
    w0 = 2.0 * h1 + h0
    w1 = h1 + 2.0 * h0
    return (w0 + w1) / (w0 / d0 + w1 / d1)


def _keyframe_value(layer: dict[str, Any], frame: int) -> float:
    """Piecewise interpolation of sparse native per-frame velocity keyframes.

    Missing lead-in samples start at zero at the layer start. After the last
    keyframe the last value holds until the layer end. Frame zero is unwarped.
    """
    if frame == 0 or frame < layer["start_frame"] or frame >= layer["end_frame"]:
        return 0.0
    keys = layer["keys"]
    if frame >= keys[-1]["frame"]:
        return float(keys[-1]["value"])
    if frame < keys[0]["frame"]:
        left_frame, left_value = layer["start_frame"], 0.0
        right = keys[0]
    else:
        left = keys[0]
        right = keys[-1]
        for n in range(len(keys) - 1):
            if keys[n]["frame"] <= frame < keys[n + 1]["frame"]:
                left, right = keys[n], keys[n + 1]
                break
        left_frame, left_value = left["frame"], float(left["value"])
    right_frame = right["frame"]
    mode = layer["interpolation"]
    if mode == "hold" or right_frame == left_frame:
        return left_value
    factor = (frame - left_frame) / (right_frame - left_frame)
    right_value = float(right["value"])
    if mode == "smoothstep":
        # Ease in/out with zero slope at both keyframes; no overshoot.
        factor = factor * factor * (3.0 - 2.0 * factor)
    elif mode == "smootherstep":
        # C2-smooth, gentler starts/stops than smoothstep.
        factor = factor ** 3 * (factor * (factor * 6.0 - 15.0) + 10.0)
    elif mode == "cubic":
        # Shape-preserving PCHIP-style Hermite interpolation. Tangents meet
        # continuously across interior keys without ringing past extrema.
        # A leading implicit zero at the layer start is a real interpolation
        # anchor, but is never persisted as a user-authored keyframe.
        points = [(key["frame"], float(key["value"])) for key in keys]
        if points[0][0] > layer["start_frame"]:
            points.insert(0, (layer["start_frame"], 0.0))
        right_index = next(i for i, p in enumerate(points) if p[0] == right_frame)
        left_index = right_index - 1
        h = right_frame - left_frame
        m0 = _monotone_tangent(points, left_index)
        m1 = _monotone_tangent(points, right_index)
        t2 = factor * factor
        t3 = t2 * factor
        value = (
            (2 * t3 - 3 * t2 + 1) * left_value
            + (t3 - 2 * t2 + factor) * h * m0
            + (-2 * t3 + 3 * t2) * right_value
            + (t3 - t2) * h * m1
        )
        # Numerical guard: cubic smoothing must never overshoot adjacent keys.
        return max(min(left_value, right_value), min(max(left_value, right_value), value))
    return left_value + factor * (right_value - left_value)


def _recording_frame(layer: dict[str, Any], frame: int) -> dict[str, float]:
    """Return armed native per-frame deltas from a validated recording layer."""
    if frame == 0 or frame < layer["start_frame"] or frame >= layer["end_frame"]:
        return {}
    row = layer["samples"][frame - layer["start_frame"]]
    return {axis: float(row[AXES.index(axis)]) for axis in layer["axes"]}


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
        raise MotionLabError("Add at least one Motion Lab layer.")
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
            if layer["type"] == "keyframes":
                values = {layer["axis"]: _keyframe_value(layer, frame)}
            elif layer["type"] == "recording":
                values = _recording_frame(layer, frame)
            elif layer["type"] == "audio":
                pulse = layer["pulses"][frame - layer["start_frame"]]
                values = {layer["axis"]: pulse} if pulse else {}
            else:
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

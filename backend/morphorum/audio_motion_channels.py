"""MS3: deterministic independent audio frequency channels for native six-axis motion.

Audio channel documents are self-contained frame-aligned snapshots bound to a
project-owned WAV SHA-256. Preview/Apply never decode media or mutate the source.
Independent channel envelopes are analyzed by audio_channel_bands.py.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .audio_motion import AudioMotionError, balanced_pulses, onset_strength
from .motion_lab import AXES, AMPLITUDE

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9 _.-]{1,64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MODES = ("hits", "intensity", "ripple")
MAX_CHANNELS = 8


def _float(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise AudioMotionError(f"{label} must be numeric.")
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise AudioMotionError(f"Invalid {label}.") from exc
    if not math.isfinite(value) or not low <= value <= high:
        raise AudioMotionError(f"{label} must be between {low:g} and {high:g}.")
    return value


def _int(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise AudioMotionError(f"{label} must be an integer from {low} to {high}.")
    return value


def validate_channel_document(payload: dict[str, Any], *, fps: float, frames: int) -> dict:
    """Strictly validate all channels before any camera layers are compiled."""
    if not isinstance(payload, dict):
        raise AudioMotionError("Audio channel document must be an object.")
    source = payload.get("source_sha256")
    if not isinstance(source, str) or not _DIGEST.fullmatch(source):
        raise AudioMotionError("Audio channels require a valid WAV SHA-256.")
    clock = _float(fps, "Project FPS", 1, 240)
    count = _int(frames, "Project frames", 1, 3000)
    saved_fps = _float(payload.get("fps"), "Audio FPS", 1, 240)
    if not math.isclose(saved_fps, clock, abs_tol=1e-9):
        raise AudioMotionError("Channel analysis FPS differs from the project; reanalyze WAV.")
    if payload.get("max_frames") != count:
        raise AudioMotionError("Channel frame count differs from the project; reanalyze WAV.")
    incoming = payload.get("channels")
    if not isinstance(incoming, list) or len(incoming) > MAX_CHANNELS:
        raise AudioMotionError("Audio channel list must have at most 8 entries.")
    channels = []
    used = set()
    for index, raw in enumerate(incoming):
        if not isinstance(raw, dict):
            raise AudioMotionError("Audio channel must be an object.")
        ident = raw.get("id")
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in used:
            raise AudioMotionError("Audio channel IDs must be unique and safe.")
        used.add(ident)
        name = raw.get("name", ident)
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise AudioMotionError("Audio channel name is invalid.")
        enabled = raw.get("enabled", True)
        if type(enabled) is not bool:
            raise AudioMotionError("Audio channel enabled must be boolean.")
        mode = raw.get("mode", "hits")
        if mode not in MODES:
            raise AudioMotionError("Audio channel mode must be Hits, Intensity or Ripple.")
        axis = raw.get("axis", "translation_z")
        if axis not in AXES:
            raise AudioMotionError("Audio channel axis must be a native camera axis.")
        low = _float(raw.get("low_hz"), "Band low Hz", 20, 20000)
        high = _float(raw.get("high_hz"), "Band high Hz", 20, 20000)
        if high - low < 10:
            raise AudioMotionError("Audio channel band must span at least 10 Hz.")
        values = raw.get("envelope")
        if not isinstance(values, list) or len(values) != count:
            raise AudioMotionError("Channel envelope must contain one value per project frame.")
        envelope = [round(_float(v, "Audio envelope", 0, 1), 7) for v in values]
        start = _int(raw.get("start_frame", 0), "Channel start", 0, count - 1)
        end = _int(raw.get("end_frame", count), "Channel end", start + 1, count)
        channels.append({
            "id": ident, "name": name, "enabled": enabled,
            "axis": axis, "mode": mode, "low_hz": low, "high_hz": high,
            "threshold": _float(raw.get("threshold", .3), "Threshold", 0, 1),
            "sensitivity": _float(raw.get("sensitivity", .35), "Sensitivity", 0, 1),
            "strength": _float(raw.get("strength", .5), "Strength", 0, 1),
            "attack_frames": _int(raw.get("attack_frames", 2), "Attack frames", 1, 120),
            "release_frames": _int(raw.get("release_frames", 6), "Release frames", 1, 120),
            "cooldown_frames": _int(raw.get("cooldown_frames", 3), "Cooldown frames", 0, 120),
            "offset_frames": _int(raw.get("offset_frames", 0), "Offset frames", -3000, 3000),
            "start_frame": start, "end_frame": end, "envelope": envelope,
        })
    return {"schema_version": 1, "source_sha256": source,
            "fps": saved_fps, "max_frames": count, "channels": channels}


def _movement_positions(channel: dict, signal: list[float], frames: int) -> list[float]:
    """Make a bounded relative camera displacement, never a drifting velocity."""
    first, end = channel["start_frame"], channel["end_frame"]
    attack, release = channel["attack_frames"], channel["release_frames"]
    strength, threshold = channel["strength"], channel["threshold"]
    mode = channel["mode"]
    amount = strength * AMPLITUDE[channel["axis"]] * 4
    target = [0.] * frames
    offset = channel["offset_frames"]
    if mode == "intensity":
        up, down = 1 / attack, 1 / release
        smoothed = 0.
        for frame in range(first, end):
            sample = frame - offset
            value = signal[sample] if 0 <= sample < frames else 0.
            desired = amount * value if value >= threshold else 0.
            smoothed += (desired - smoothed) * (up if desired > smoothed else down)
            target[frame] = smoothed
    else:  # Ripple is a decaying, time-bounded oscillation triggered by a transient.
        rises = onset_strength(signal, channel["sensitivity"])
        last = -100000
        for source_frame, value in enumerate(rises):
            if value < threshold or value == 0 or source_frame <= last + channel["cooldown_frames"]:
                continue
            position = source_frame + offset
            length = attack + release
            if position < first or position + length >= end:
                continue
            last = source_frame + length
            for step in range(length + 1):
                progress = step / length
                target[position + step] += (amount * value *
                    math.sin(4 * math.pi * progress) * math.exp(-3 * progress))
    # Return to the original camera path at the active interval boundary.
    target[end - 1] = 0.
    return target


def compile_channel_tracks(document: dict, *, fps: float, frames: int) -> dict[str, list[float]]:
    """Compose all channels into deterministic native per-frame velocity signals.

    Hits produce exact balanced impulses; Intensity and Ripple sample a bounded
    displacement and differentiate it, so their total contribution sums to
    approximately zero. Final clipping remains Motion Lab's responsibility.
    """
    clean = validate_channel_document(document, fps=fps, frames=frames)
    outputs = {axis: [0.] * frames for axis in AXES}
    for channel in clean["channels"]:
        if not channel["enabled"] or channel["strength"] == 0:
            continue
        first, end = channel["start_frame"], channel["end_frame"]
        envelope = channel["envelope"]
        axis = channel["axis"]
        if channel["mode"] == "hits":
            rises = onset_strength(envelope, channel["sensitivity"])
            pulses = balanced_pulses(
                rises[first:end], threshold=channel["threshold"],
                distance=channel["strength"] * AMPLITUDE[axis] * 4,
                attack_frames=channel["attack_frames"],
                release_frames=channel["release_frames"],
                cooldown_frames=channel["cooldown_frames"],
                offset_frames=channel["offset_frames"],
            )
            for i, delta in enumerate(pulses, start=first):
                outputs[axis][i] += delta
        else:
            target = _movement_positions(channel, envelope, frames)
            previous = 0.
            for i in range(first, end):
                current = target[i]
                outputs[axis][i] += current - previous
                previous = current
    return outputs

"""DA4.1 project-owned, audio-bound Motion Director cue store.

Cue times are in source seconds, independent of project FPS. Compilation into
native six-axis motion is intentionally reserved for DA4.5.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from .animation_projects import animation_project_directory
from .audio_motion import AudioMotionError

_SOURCE = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,95}$")
_MAX_CUES = 3000
_PRESETS = frozenset({
    "push_zoom_in", "push_return", "roll_right_left", "roll_left_right",
    "dolly_out", "shake", "ripple", "reveal_drift", "fly_through",
})
_EASINGS = frozenset({"linear", "smoothstep", "ease_in", "ease_out", "ease_in_out"})


def _file(project_id: str, source_sha256: str) -> Path:
    if not isinstance(source_sha256, str) or not _SOURCE.fullmatch(source_sha256):
        raise AudioMotionError("Motion cue source hash must be a SHA-256 hex digest.")
    return animation_project_directory(project_id) / "motion_lab_audio" / (source_sha256 + ".cues.json")


def validate_cues(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AudioMotionError("Motion cue document must be an object.")
    source_sha256 = payload.get("source_sha256")
    if not isinstance(source_sha256, str) or not _SOURCE.fullmatch(source_sha256):
        raise AudioMotionError("Invalid source SHA-256.")
    try:
        duration = float(payload["duration_seconds"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AudioMotionError("Motion cue document requires an audio duration.") from exc
    if not math.isfinite(duration) or not 0 < duration <= 180:
        raise AudioMotionError("Motion cue audio duration must be 0–180 seconds.")
    incoming = payload.get("cues")
    if not isinstance(incoming, list) or len(incoming) > _MAX_CUES:
        raise AudioMotionError("Motion cues must be a list with at most 3000 entries.")
    used: set[str] = set()
    cues: list[dict[str, Any]] = []
    for index, raw in enumerate(incoming):
        if not isinstance(raw, dict):
            raise AudioMotionError(f"Motion cue {index} must be an object.")
        cue_id = raw.get("id")
        if not isinstance(cue_id, str) or not _ID.fullmatch(cue_id) or cue_id in used:
            raise AudioMotionError(f"Motion cue {index} has an invalid or duplicate ID.")
        used.add(cue_id)
        preset = raw.get("preset")
        if preset not in _PRESETS:
            raise AudioMotionError(f"Motion cue {index} has an unsupported preset.")
        easing = raw.get("easing", "ease_in_out")
        if easing not in _EASINGS:
            raise AudioMotionError(f"Motion cue {index} has invalid easing.")
        enabled = raw.get("enabled", True)
        if type(enabled) is not bool:
            raise AudioMotionError(f"Motion cue {index} enabled must be boolean.")
        try:
            time = float(raw["time_seconds"])
            length = float(raw.get("duration_seconds", .6))
            strength = float(raw.get("intensity", .5))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise AudioMotionError(f"Motion cue {index} has malformed timing or intensity.") from exc
        if not math.isfinite(time) or time < 0 or time >= duration:
            raise AudioMotionError(f"Motion cue {index} must start within the audio.")
        if not math.isfinite(length) or not 0.01 <= length <= 30:
            raise AudioMotionError(f"Motion cue {index} duration must be 0.01–30 seconds.")
        if not math.isfinite(strength) or not 0 <= strength <= 1:
            raise AudioMotionError(f"Motion cue {index} intensity must be 0–1.")
        source_event_id = raw.get("source_event_id")
        if source_event_id is not None and (
            not isinstance(source_event_id, str) or not _ID.fullmatch(source_event_id)
        ):
            raise AudioMotionError(f"Motion cue {index} references an invalid event ID.")
        cues.append({
            "id": cue_id, "preset": preset, "time_seconds": round(time, 6),
            "duration_seconds": round(length, 6), "intensity": round(strength, 6),
            "easing": easing, "enabled": enabled, "source_event_id": source_event_id,
        })
    cues.sort(key=lambda cue: (cue["time_seconds"], cue["id"]))
    return {"schema_version": 1, "source_sha256": source_sha256,
            "duration_seconds": duration, "cues": cues}


def load_motion_cues(project_id: str, source_sha256: str) -> dict[str, Any] | None:
    path = _file(project_id, source_sha256)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AudioMotionError("Stored motion cues cannot be read.") from exc
    clean = validate_cues(document)
    if clean["source_sha256"] != source_sha256:
        raise AudioMotionError("Stored motion cues belong to a different WAV.")
    return clean


def save_motion_cues(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    document = validate_cues(payload)
    digest = document["source_sha256"]
    path = _file(project_id, digest)
    if not (path.parent / (digest + ".wav")).is_file():
        raise AudioMotionError("The source WAV is not stored in this project.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".cues.tmp")
    try:
        temporary.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return document


def cue_frame_index(time_seconds: float, fps: float, max_frames: int) -> int:
    """Project cue timestamp to a frame only when asked to compile/preview."""
    if not math.isfinite(time_seconds) or time_seconds < 0:
        raise AudioMotionError("Cue time must be finite and nonnegative.")
    if not math.isfinite(fps) or not 1 <= fps <= 240:
        raise AudioMotionError("Project FPS must be 1–240.")
    if type(max_frames) is not int or not 1 <= max_frames <= 3000:
        raise AudioMotionError("Project must have 1–3000 frames.")
    return min(max_frames - 1, max(0, int(math.floor(time_seconds * fps + .5))))

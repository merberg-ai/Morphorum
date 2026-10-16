"""Project-owned, source-bound drum marker overrides for DA3.2."""
from __future__ import annotations

import json
import math
import os
import re

from .animation_projects import animation_project_directory
from .audio_motion import AudioMotionError

_HASH = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED = {"kick", "snare", "highs"}
_MAX_EVENTS = 12000


def _path(project_id: str, source_sha256: str):
    if not isinstance(source_sha256, str) or not _HASH.fullmatch(source_sha256):
        raise AudioMotionError("Invalid WAV source hash.")
    return animation_project_directory(project_id) / "motion_lab_audio" / (source_sha256 + ".markers.json")


def read_marker_overrides(project_id: str, source_sha256: str) -> dict | None:
    path = _path(project_id, source_sha256)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AudioMotionError("Stored audio marker edits could not be read.") from exc
    if not isinstance(data, dict) or data.get("source_sha256") != source_sha256:
        raise AudioMotionError("Stored audio markers do not match this WAV.")
    return data


def write_marker_overrides(project_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise AudioMotionError("Marker edits must be an object.")
    digest = payload.get("source_sha256")
    path = _path(project_id, digest)
    if not (path.parent / (digest + ".wav")).is_file():
        raise AudioMotionError("The referenced WAV is not stored in this project.")
    try:
        duration = float(payload.get("duration_seconds"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise AudioMotionError("Invalid audio marker duration.") from exc
    if not math.isfinite(duration) or not 0 < duration <= 180:
        raise AudioMotionError("Invalid audio marker duration.")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > _MAX_EVENTS:
        raise AudioMotionError("Marker events must be a bounded list.")
    normalized = []
    used = set()
    for item in events:
        if not isinstance(item, dict):
            raise AudioMotionError("Invalid marker event.")
        ident = item.get("id")
        if not isinstance(ident, str) or not 1 <= len(ident) <= 96 or ident in used:
            raise AudioMotionError("Invalid or repeated marker ID.")
        used.add(ident)
        kind = item.get("kind")
        if kind not in _ALLOWED:
            raise AudioMotionError("Unknown marker type.")
        enabled = item.get("enabled")
        if type(enabled) is not bool:
            raise AudioMotionError("Marker enabled must be boolean.")
        try:
            time = float(item.get("time_seconds"))
        except (ValueError, TypeError, OverflowError) as exc:
            raise AudioMotionError("Invalid marker time.") from exc
        if not math.isfinite(time) or time < 0 or time >= duration:
            raise AudioMotionError("Marker time is outside the WAV.")
        normalized.append({"id": ident, "kind": kind, "enabled": enabled,
                           "time_seconds": round(time, 6)})
    normalized.sort(key=lambda e: (e["time_seconds"], e["id"]))
    result = {"schema_version": 1, "source_sha256": digest,
              "duration_seconds": duration, "events": normalized}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".markers.tmp")
    try:
        temp.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return result

"""PS6.2: read-only, revisionable fingerprint for Studio beat alignment.

WAV, saved manual markers, attached soundtrack/offset and project timing
are all verified server-side. This endpoint cannot stage or save prompts.
"""
from __future__ import annotations

import hashlib
import json
import re

from .animation_projects import animation_project_directory, load_animation_project
from .audio_marker_overrides import read_marker_overrides
from .audio_motion import AudioMotionError
from .project_assets import motion_wav_descriptor, soundtrack_descriptor
from .imported_soundtrack import read_soundtrack

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_MARKER_BYTES = 3 * 1024 * 1024


def audio_alignment_context(project_id: str, source_sha256: str) -> dict:
    if not isinstance(source_sha256, str) or not _SHA.fullmatch(source_sha256):
        raise AudioMotionError("Invalid analyzed WAV identifier.")
    project = load_animation_project(project_id)
    animation = project["animation"]
    asset = motion_wav_descriptor(project_id, source_sha256)
    if asset["kind"] != "motion_lab_wav" or asset["sha256"] != source_sha256:
        raise AudioMotionError("Analyzed project WAV verification failed.")
    folder = animation_project_directory(project_id) / "motion_lab_audio"
    marker_path = folder / f"{source_sha256}.markers.json"
    if folder.is_symlink() or marker_path.is_symlink():
        raise AudioMotionError("Saved marker file must not be a symlink.")
    marker_sha256 = None
    if marker_path.exists():
        if not marker_path.is_file() or marker_path.stat().st_size > _MAX_MARKER_BYTES:
            raise AudioMotionError("Saved marker document is invalid or oversized.")
        # Validate ownership/source identity before trusting the file fingerprint.
        markers = read_marker_overrides(project_id, source_sha256)
        if not isinstance(markers, dict) or not isinstance(markers.get("events"), list):
            raise AudioMotionError("Saved Motion Studio markers are invalid.")
        marker_sha256 = hashlib.sha256(marker_path.read_bytes()).hexdigest()

    soundtrack = soundtrack_descriptor(project_id)
    original = read_soundtrack(project_id) if soundtrack else None
    soundtrack_sha256 = soundtrack["sha256"] if soundtrack else None
    offset = float(original["offset_seconds"]) if original else None
    details = {
        "source_sha256": source_sha256,
        "markers_sha256": marker_sha256,
        "marker_mode": "saved-edits" if marker_sha256 else "detected",
        "soundtrack_sha256": soundtrack_sha256,
        "soundtrack_offset_seconds": offset,
        "fps": float(animation["fps"]),
        "max_frames": int(animation["max_frames"]),
    }
    digest = hashlib.sha256(json.dumps(
        details, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    return {"schema_version": 1, "project_id": project_id, **details, "stamp": digest}

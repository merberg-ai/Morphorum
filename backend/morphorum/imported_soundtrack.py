"""Project-owned soundtrack attachment metadata for Deforum imports.

This is separate from project.json and existing Motion Lab WAV files. No export
changes are made until DMI3 synchronization testing establishes correct behavior.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from .animation_projects import animation_project_directory

MAX_IMPORT_AUDIO_BYTES = 40 * 1024 * 1024
EXTENSIONS = {".wav": "wav", ".mp3": "mp3", ".ogg": "ogg", ".flac": "flac"}


class ImportedSoundtrackError(ValueError):
    pass


def _directory(project_id: str) -> Path:
    return animation_project_directory(project_id) / "imported_soundtrack"


def _metadata(project_id: str) -> Path:
    return _directory(project_id) / "attachment.json"


def _valid_offset(offset: object) -> float:
    if isinstance(offset, bool):
        raise ImportedSoundtrackError("Audio offset must be a finite number.")
    try:
        value = float(offset)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ImportedSoundtrackError("Audio offset must be a finite number.") from exc
    if not math.isfinite(value) or abs(value) > 30:
        raise ImportedSoundtrackError("Audio offset must be within -30 and +30 seconds.")
    return value


def read_soundtrack(project_id: str) -> dict | None:
    path = _metadata(project_id)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImportedSoundtrackError("Stored soundtrack metadata is unreadable.") from exc
    if not isinstance(record, dict) or record.get("format") not in EXTENSIONS.values():
        raise ImportedSoundtrackError("Stored soundtrack metadata is invalid.")
    digest = record.get("sha256", "")
    if not isinstance(digest, str) or len(digest) != 64 or any(x not in "0123456789abcdef" for x in digest):
        raise ImportedSoundtrackError("Stored soundtrack checksum is invalid.")
    if not (_directory(project_id) / (digest + "." + record["format"])).is_file():
        raise ImportedSoundtrackError("Stored soundtrack file is missing.")
    return record


def store_soundtrack(project_id: str, data: bytes, *, filename: str, offset_seconds: float) -> dict:
    if not isinstance(data, bytes) or len(data) == 0 or len(data) > MAX_IMPORT_AUDIO_BYTES:
        raise ImportedSoundtrackError("Audio must be nonempty and at most 40 MiB.")
    basename = filename.replace("\\", "/").split("/")[-1]
    ext = Path(basename).suffix.lower()
    if ext not in EXTENSIONS:
        raise ImportedSoundtrackError("Only WAV, MP3, OGG and FLAC can be attached.")
    # Format-specific file signatures; never trust extensions or browser MIME alone.
    valid = ((ext == ".wav" and data[:4] == b"RIFF" and data[8:12] == b"WAVE")
             or (ext == ".mp3" and (data.startswith(b"ID3") or
                  (len(data) > 2 and data[0] == 0xff and data[1] & 0xe0 == 0xe0)))
             or (ext == ".ogg" and data.startswith(b"OggS"))
             or (ext == ".flac" and data.startswith(b"fLaC")))
    if not valid:
        raise ImportedSoundtrackError("The uploaded file does not match its audio format.")
    offset = _valid_offset(offset_seconds)
    sha = hashlib.sha256(data).hexdigest()
    destination = _directory(project_id)
    destination.mkdir(parents=True, exist_ok=True)
    name = sha + ext
    path = destination / name
    if not path.is_file():
        fd, temp = tempfile.mkstemp(prefix=".audio-", dir=destination)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    record = {
        "schema_version": 1, "sha256": sha, "format": EXTENSIONS[ext],
        "filename": basename[:160], "bytes": len(data),
        "offset_seconds": offset,
    }
    fd, temp = tempfile.mkstemp(prefix=".meta-", dir=destination)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
        os.replace(temp, _metadata(project_id))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return record


def update_offset(project_id: str, offset_seconds: float) -> dict:
    record = read_soundtrack(project_id)
    if record is None:
        raise ImportedSoundtrackError("Attach a local soundtrack before saving its offset.")
    offset = _valid_offset(offset_seconds)
    record["offset_seconds"] = offset
    destination = _directory(project_id)
    fd, temp = tempfile.mkstemp(prefix=".meta-", dir=destination)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
        os.replace(temp, _metadata(project_id))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return record

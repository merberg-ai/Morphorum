"""DB2.3 project-owned media descriptors and bounded transfer utilities.

No arbitrary user-provided filesystem paths or generic filesystem browser.
All assets resolve under an existing validated animation project ID.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import AsyncIterable

from .animation_projects import animation_project_directory
from .animation_motion import SOURCE_MAX_BYTES
from .audio_motion_upload import MAX_AUDIO_BYTES
from .imported_soundtrack import read_soundtrack

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 1024 * 1024


class ProjectAssetError(ValueError):
    pass


class ProjectAssetTooLarge(ProjectAssetError):
    pass


async def read_bounded(chunks: AsyncIterable[bytes], *, limit: int,
                       expected_digest: str | None = None) -> bytes:
    """Consume an HTTP body without permitting unbounded memory growth."""
    if expected_digest is not None and not _DIGEST.fullmatch(expected_digest):
        raise ProjectAssetError("X-Content-SHA256 must be 64 lowercase hexadecimal characters.")
    collected = bytearray()
    digest = hashlib.sha256()
    async for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise ProjectAssetError("Upload stream contains non-binary data.")
        if len(collected) + len(chunk) > limit:
            raise ProjectAssetTooLarge(f"Upload exceeds its {limit // (1024 * 1024)} MiB limit.")
        collected.extend(chunk)
        digest.update(chunk)
    if not collected:
        raise ProjectAssetError("Upload is empty.")
    if expected_digest is not None and digest.hexdigest() != expected_digest:
        raise ProjectAssetError("Uploaded file SHA-256 does not match X-Content-SHA256.")
    return bytes(collected)


def digest_file(path: Path, *, max_bytes: int | None = None) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ProjectAssetError("Project asset not found.")
    size = path.stat().st_size
    if size < 1 or (max_bytes is not None and size > max_bytes):
        raise ProjectAssetError("Project asset has invalid file size.")
    hash_ = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            hash_.update(chunk)
    return hash_.hexdigest(), size


def descriptor(*, project_id: str, kind: str, filename: str, path: Path,
               media_type: str, url: str, asset_id: str,
               max_bytes: int | None = None, expected_sha256: str | None = None) -> dict:
    sha256, size = digest_file(path, max_bytes=max_bytes)
    if expected_sha256 is not None and sha256 != expected_sha256:
        raise ProjectAssetError("Stored project asset SHA-256 is inconsistent.")
    return {
        "schema_version": 1, "project_id": project_id,
        "kind": kind, "id": asset_id, "filename": filename,
        "bytes": size, "media_type": media_type, "sha256": sha256, "url": url,
    }


def source_descriptor(project_id: str) -> dict | None:
    root = animation_project_directory(project_id)
    path = root / "assets" / "source.png"
    if not path.exists():
        return None
    return descriptor(
        project_id=project_id, kind="source_image",
        filename="source.png", path=path, media_type="image/png",
        asset_id="source-image", max_bytes=SOURCE_MAX_BYTES * 4,
        url=f"/api/animation/projects/{project_id}/source-image",
    )


def soundtrack_path(project_id: str) -> tuple[Path, dict]:
    record = read_soundtrack(project_id)
    if record is None:
        raise ProjectAssetError("This project has no attached soundtrack.")
    if not _DIGEST.fullmatch(record["sha256"]):
        raise ProjectAssetError("Stored soundtrack SHA-256 is invalid.")
    path = (animation_project_directory(project_id) / "imported_soundtrack"
            / f"{record['sha256']}.{record['format']}")
    if path.is_symlink() or not path.is_file():
        raise ProjectAssetError("Stored soundtrack file is unavailable.")
    return path, record


def soundtrack_descriptor(project_id: str) -> dict | None:
    try:
        path, record = soundtrack_path(project_id)
    except ProjectAssetError as exc:
        if str(exc) == "This project has no attached soundtrack.":
            return None
        raise
    from .imported_soundtrack import MAX_IMPORT_AUDIO_BYTES
    mimetypes = {
        "wav": "audio/wav", "mp3": "audio/mpeg",
        "ogg": "audio/ogg", "flac": "audio/flac",
    }
    return descriptor(
        project_id=project_id, kind="soundtrack",
        asset_id=record["sha256"], filename=record["filename"],
        path=path, media_type=mimetypes[record["format"]],
        expected_sha256=record["sha256"], max_bytes=MAX_IMPORT_AUDIO_BYTES,
        url=f"/api/animation/projects/{project_id}/motion-import/soundtrack/file",
    )


def motion_wav_path(project_id: str, sha256: str) -> Path:
    if not _DIGEST.fullmatch(sha256):
        raise ProjectAssetError("Invalid analyzed WAV identifier.")
    path = animation_project_directory(project_id) / "motion_lab_audio" / f"{sha256}.wav"
    actual, _ = digest_file(path, max_bytes=MAX_AUDIO_BYTES)
    if actual != sha256:
        raise ProjectAssetError("Stored analyzed WAV checksum does not match its identifier.")
    return path


def motion_wav_descriptor(project_id: str, sha256: str) -> dict:
    path = motion_wav_path(project_id, sha256)
    return descriptor(
        project_id=project_id, kind="motion_lab_wav", asset_id=sha256,
        filename=f"{sha256}.wav", path=path, media_type="audio/wav",
        expected_sha256=sha256, max_bytes=MAX_AUDIO_BYTES,
        url=f"/api/animation/projects/{project_id}/motion-lab/audio/{sha256}",
    )


def catalog(project_id: str) -> list[dict]:
    items = []
    source = source_descriptor(project_id)
    if source:
        items.append(source)
    audio = soundtrack_descriptor(project_id)
    if audio:
        items.append(audio)
    folder = animation_project_directory(project_id) / "motion_lab_audio"
    if folder.exists():
        if folder.is_symlink() or not folder.is_dir():
            raise ProjectAssetError("Project Motion Lab asset store is invalid.")
        for path in sorted(folder.glob("*.wav"))[:100]:
            if _DIGEST.fullmatch(path.stem):
                items.append(motion_wav_descriptor(project_id, path.stem))
    return items

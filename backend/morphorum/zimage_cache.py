"""Z2.9 read-only cache verification and exclusive conversion reservation.

Does not authorize runtime loading. A conversion reservation is explicit and
never deletes another process's lock or any published cache artifact.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 64 * 1024
CHUNK = 4 * 1024 * 1024


class CacheIntegrityError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_staged_cache(directory: str | Path) -> dict[str, Any]:
    """Independently check staged artifact hashes and unverified manifest."""
    folder = Path(directory)
    if folder.is_symlink() or not folder.is_dir():
        raise CacheIntegrityError("Cache directory is absent or a symlink.")
    manifest_path = folder / "manifest.json"
    weights = folder / "diffusion_pytorch_model.safetensors"
    if any(p.is_symlink() or not p.is_file() for p in (manifest_path, weights)):
        raise CacheIntegrityError("Cache manifest or weights are missing or unsafe.")
    if not 0 < manifest_path.stat().st_size <= MAX_MANIFEST_BYTES:
        raise CacheIntegrityError("Invalid manifest size.")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise CacheIntegrityError("Malformed cache manifest.") from exc
    if not isinstance(data, dict) or data.get("loadable") is not False or data.get("runtime_verified") is not False:
        raise CacheIntegrityError("Unexpected cache authorization flags.")
    expected = data.get("output_sha256", data.get("staged_sha256"))
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise CacheIntegrityError("Missing valid output digest.")
    if sha256_file(weights) != expected:
        raise CacheIntegrityError("Cached weights differ from manifest SHA-256.")
    source = data.get("source")
    if not isinstance(source, str) or not source:
        raise CacheIntegrityError("Manifest missing source.")
    # Do not trust a cached artifact as ready, even after checksum verification.
    return {"integrity": "verified", "cache_directory": str(folder),
            "source": source, "ready": False, "loadable": False}


class ExclusiveCacheReservation:
    """Cross-process lock using O_EXCL. Stale locks require manual intervention."""

    def __init__(self, destination: str | Path):
        self.destination = Path(destination)
        self.lock = self.destination.with_name(self.destination.name + ".lock")
        self._fd: int | None = None

    def __enter__(self):
        if self.destination.exists() or self.destination.is_symlink():
            raise CacheIntegrityError("Cache destination already exists.")
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise CacheIntegrityError("Another conversion holds the cache reservation.") from exc
        os.write(self._fd, str(os.getpid()).encode("ascii"))
        os.fsync(self._fd)
        return self

    def __exit__(self, *_):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            self.lock.unlink(missing_ok=True)

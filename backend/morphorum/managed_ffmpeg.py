"""P4.4.3 managed FFmpeg installer.

Opt-in only. The release and SHA256 are obtained from BtbN GitHub release
metadata, with an exact allowlisted artifact name and URL. Downloaded bytes
must match the published SHA256 before extraction or execution.

Uses GPL static builds for compatibility with Morphorum's libx264/libvpx
video export paths. Include the upstream GPL notice and build provenance.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import ffmpeg_tools

RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest"
RELEASE_PAGE = "https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest"
PROJECT_URL = "https://github.com/BtbN/FFmpeg-Builds"
SOURCE_URL = "https://github.com/FFmpeg/FFmpeg"
MANAGED_ROOT = ffmpeg_tools.ROOT / "tools" / "ffmpeg"
MAX_RELEASE_JSON = 3 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 480 * 1024 * 1024
MAX_BINARY_BYTES = 400 * 1024 * 1024
MAX_DOC_BYTES = 12 * 1024 * 1024
NETWORK_TIMEOUT = 30
READ_SIZE = 1024 * 1024
DONE = {"installed", "failed", "cancelled"}
DOWNLOAD_STATES = {"checking", "downloading", "verifying", "extracting", "installing"}
# Static GPL variants include required video codec support. No shared DLL/so dependencies.
ASSETS = {
    ("windows", "x86_64"): "ffmpeg-n8.1-latest-win64-gpl-8.1.zip",
    ("windows", "arm64"): "ffmpeg-n8.1-latest-winarm64-gpl-8.1.zip",
    ("linux", "x86_64"): "ffmpeg-n8.1-latest-linux64-gpl-8.1.tar.xz",
    ("linux", "arm64"): "ffmpeg-n8.1-latest-linuxarm64-gpl-8.1.tar.xz",
}


class ManagedFFmpegError(RuntimeError):
    pass


class _Cancelled(ManagedFFmpegError):
    pass


def supported_asset(system: str | None = None, machine: str | None = None) -> str | None:
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    normalized = {
        "amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64",
    }.get(machine, machine)
    if system not in {"windows", "linux"}:
        return None
    return ASSETS.get((system, normalized))


def _read_release() -> dict[str, Any]:
    request = urllib.request.Request(RELEASE_API, headers={
        "User-Agent": "Morphorum-FFmpeg-Manager/1.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response:
        raw = response.read(MAX_RELEASE_JSON + 1)
        if len(raw) > MAX_RELEASE_JSON:
            raise ManagedFFmpegError("Release metadata exceeds the allowed size.")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ManagedFFmpegError("FFmpeg release metadata is invalid.") from exc
    if not isinstance(parsed, dict) or parsed.get("tag_name") != "latest":
        raise ManagedFFmpegError("Unexpected FFmpeg release tag.")
    return parsed


def release_asset(asset_name: str) -> dict[str, Any]:
    if asset_name not in ASSETS.values():
        raise ManagedFFmpegError("Unsupported FFmpeg distribution.")
    release = _read_release()
    matching = [a for a in release.get("assets", []) if
                isinstance(a, dict) and a.get("name") == asset_name]
    if len(matching) != 1:
        raise ManagedFFmpegError("The expected FFmpeg package is not published yet.")
    asset = matching[0]
    expected_url = (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/" + asset_name
    )
    size = asset.get("size")
    digest = str(asset.get("digest") or "").lower()
    if (asset.get("browser_download_url") != expected_url or
            not isinstance(size, int) or not 1 <= size <= MAX_DOWNLOAD_BYTES or
            not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)):
        raise ManagedFFmpegError(
            "Release metadata has no trustworthy package SHA-256, or exceeds the size limit."
        )
    return {
        "filename": asset_name, "url": expected_url, "sha256": digest[7:],
        "size_bytes": size, "release": RELEASE_PAGE, "tag": "latest",
    }


def _check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise _Cancelled("Managed FFmpeg installation cancelled.")


def _download(record: dict[str, Any], output: Path, cancel: threading.Event, progress) -> None:
    req = urllib.request.Request(record["url"], headers={
        "User-Agent": "Morphorum-FFmpeg-Manager/1.0",
        "Accept": "application/octet-stream",
    })
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT) as response:
        # GitHub release files redirect to GitHub-controlled asset hosts.
        target = urllib.parse.urlsplit(response.geturl())
        host = (target.hostname or "").lower()
        if target.scheme != "https" or not (
            host == "github.com" or host.endswith(".githubusercontent.com")
        ):
            raise ManagedFFmpegError("Download redirected outside approved GitHub asset hosts.")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_DOWNLOAD_BYTES:
            raise ManagedFFmpegError("FFmpeg package exceeds the download size limit.")
        with output.open("wb") as stream:
            while True:
                _check_cancel(cancel)
                chunk = response.read(READ_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES or total > record["size_bytes"]:
                    raise ManagedFFmpegError("FFmpeg package exceeded its published size.")
                stream.write(chunk)
                digest.update(chunk)
                progress(total, record["size_bytes"])
    _check_cancel(cancel)
    if total != record["size_bytes"] or digest.hexdigest() != record["sha256"]:
        raise ManagedFFmpegError("FFmpeg SHA-256 or size mismatch. No binaries were installed.")


def _wanted_file(name: str) -> str | None:
    # Only these two executables are unpacked; all paths are reduced to
    # validated names, never joined directly to their archive paths.
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or len(p.parts) > 9:
        raise ManagedFFmpegError("FFmpeg archive contains an unsafe entry.")
    leaf = p.name.lower()
    return leaf if leaf in {"ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"} else None


def _extract_binary(source, destination: Path, limit: int, cancel: threading.Event) -> None:
    copied = 0
    with destination.open("xb") as out:
        while True:
            _check_cancel(cancel)
            chunk = source.read(READ_SIZE)
            if not chunk:
                break
            copied += len(chunk)
            if copied > limit:
                raise ManagedFFmpegError("FFmpeg archive member exceeds extraction limit.")
            out.write(chunk)
    if not copied:
        raise ManagedFFmpegError("FFmpeg archive contains an empty executable.")


def _extract(archive: Path, staging: Path, cancel: threading.Event) -> None:
    bin_dir = staging / "bin"
    bin_dir.mkdir(parents=True, exist_ok=False)
    needed = {"ffmpeg.exe", "ffprobe.exe"} if os.name == "nt" else {"ffmpeg", "ffprobe"}
    found: set[str] = set()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for item in zf.infolist():
                _check_cancel(cancel)
                name = _wanted_file(item.filename)
                if name not in needed or item.is_dir():
                    continue
                # Disallow symlink members disguised as regular files.
                entry_mode = (item.external_attr >> 16) & 0xFFFF
                if stat.S_IFMT(entry_mode) == stat.S_IFLNK:
                    raise ManagedFFmpegError("FFmpeg archive contains a symlink executable.")
                if name in found or item.file_size > MAX_BINARY_BYTES:
                    raise ManagedFFmpegError("Duplicate or oversized FFmpeg executable.")
                with zf.open(item) as stream:
                    _extract_binary(stream, bin_dir / name, MAX_BINARY_BYTES, cancel)
                found.add(name)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive, mode="r:*") as tf:
            for item in tf:
                _check_cancel(cancel)
                name = _wanted_file(item.name)
                if name not in needed:
                    continue
                if not item.isfile() or name in found or item.size > MAX_BINARY_BYTES:
                    raise ManagedFFmpegError("Unsafe, duplicate or oversized FFmpeg executable.")
                stream = tf.extractfile(item)
                if stream is None:
                    raise ManagedFFmpegError("Could not read FFmpeg executable from archive.")
                with stream:
                    _extract_binary(stream, bin_dir / name, MAX_BINARY_BYTES, cancel)
                found.add(name)
    else:
        raise ManagedFFmpegError("FFmpeg archive format is unsupported or corrupt.")
    if found != needed:
        raise ManagedFFmpegError("FFmpeg package is missing ffmpeg or ffprobe.")
    if os.name != "nt":
        for name in needed:
            (bin_dir / name).chmod(0o755)


def _notice(staging: Path, record: dict[str, Any]) -> None:
    # Binary source/attribution links are saved with every install and survive
    # the removal of the downloaded archive. The app does not claim a license.
    (staging / "LICENSE-NOTICE.txt").write_text(
        "FFmpeg managed download notice\n"
        "Provider: BtbN FFmpeg-Builds (" + PROJECT_URL + ")\n"
        "Project source: " + SOURCE_URL + "\n"
        "Package: " + record["filename"] + "\n"
        "Release: " + record["release"] + "\n"
        "Variant: GPL static (includes optional GPL-licensed encoders).\n"
        "FFmpeg is licensed under LGPL/GPL depending on enabled components.\n"
        "See upstream release for source code, license texts and dependencies.\n"
        "This software is provided by its respective authors, not OpenAI.\n",
        encoding="utf-8",
    )
    (staging / "installation.json").write_text(json.dumps({
        "managed_by": "Morphorum", "provider": PROJECT_URL,
        "source": SOURCE_URL, **record,
    }, indent=2) + "\n", encoding="utf-8")


class ManagedFFmpegManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else MANAGED_ROOT
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._job: dict[str, Any] | None = None

    def _owned(self) -> bool:
        current = self.root / "current"
        record = current / "installation.json"
        try:
            info = json.loads(record.read_text(encoding="utf-8"))
            return info.get("managed_by") == "Morphorum" and info.get("provider") == PROJECT_URL
        except (OSError, ValueError, AttributeError):
            return False

    def status(self) -> dict[str, Any]:
        with self._lock:
            job = dict(self._job) if self._job else None
        current = self.root / "current"
        artifact = supported_asset()
        return {
            "supported": artifact is not None,
            "asset_name": artifact,
            "installed": self._owned(),
            "managed_path": str(current / "bin"),
            "job": job,
            "provider": PROJECT_URL, "release": RELEASE_PAGE,
            "license": "GPL static (upstream FFmpeg and dependency licenses apply)",
            "message": ("Managed installation is unsupported on this OS/CPU."
                        if not artifact else
                        "Choose Install to fetch an upstream-verified FFmpeg and FFprobe pair."),
        }

    def start(self) -> dict[str, Any]:
        if not supported_asset():
            raise ManagedFFmpegError("Managed FFmpeg is unsupported on this OS/architecture.")
        with self._lock:
            if self._job and self._job["status"] in DOWNLOAD_STATES:
                raise ManagedFFmpegError("Managed FFmpeg installation is already running.")
            if (self.root / "current").exists() and not self._owned():
                raise ManagedFFmpegError(
                    "Unmanaged files exist at tools/ffmpeg/current; refusing to overwrite them."
                )
            self._cancel = threading.Event()
            job = {
                "id": uuid.uuid4().hex, "status": "checking",
                "message": "Checking upstream FFmpeg release and checksum…",
                "downloaded_bytes": 0, "total_bytes": 0, "progress": 0.0,
                "error": None, "asset_name": supported_asset(),
            }
            self._job = job
            threading.Thread(target=self._run, args=(job["id"], self._cancel),
                             daemon=True, name="morphorum-ffmpeg-install").start()
            return dict(job)

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if not self._job or self._job["status"] not in DOWNLOAD_STATES:
                raise ManagedFFmpegError("No active managed FFmpeg installation.")
            self._cancel.set()
            return dict(self._job)

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            if self._job and self._job["id"] == job_id:
                self._job.update(fields)

    def _run(self, job_id: str, cancel: threading.Event) -> None:
        temp = self.root / (".staging-" + job_id)
        backup = self.root / (".previous-" + job_id)
        current = self.root / "current"
        swapped_old = False
        try:
            asset = supported_asset()
            if not asset:
                raise ManagedFFmpegError("Managed FFmpeg is unsupported on this host.")
            _check_cancel(cancel)
            record = release_asset(asset)
            _check_cancel(cancel)
            self.root.mkdir(parents=True, exist_ok=True)
            temp.mkdir(parents=False, exist_ok=False)
            download = temp / record["filename"]
            self._update(job_id, status="downloading", message="Downloading verified FFmpeg package…",
                         total_bytes=record["size_bytes"], progress=0.0)
            def progress(count: int, total: int) -> None:
                self._update(job_id, downloaded_bytes=count, total_bytes=total,
                             progress=round(count / total * 78, 1))
            _download(record, download, cancel, progress)
            self._update(job_id, status="verifying", message="SHA-256 checksum verified.", progress=80.0)
            _check_cancel(cancel)
            stage = temp / "package"
            stage.mkdir()
            self._update(job_id, status="extracting", message="Unpacking verified FFmpeg and FFprobe…", progress=84.0)
            _extract(download, stage, cancel)
            _notice(stage, record)
            # Verify extracted binaries before touching the installed version.
            binary = stage / "bin" / ffmpeg_tools._bin_name("ffmpeg")
            probe = stage / "bin" / ffmpeg_tools._bin_name("ffprobe")
            ff_ver, ff_error = ffmpeg_tools._version(str(binary), "ffmpeg")
            pr_ver, pr_error = ffmpeg_tools._version(str(probe), "ffprobe")
            if not ff_ver or not pr_ver:
                raise ManagedFFmpegError(
                    "Downloaded FFmpeg/FFprobe could not run (" +
                    str(ff_error or pr_error) + "). Previous installation kept."
                )
            _check_cancel(cancel)
            self._update(job_id, status="installing", message="Activating verified local FFmpeg…", progress=96.0)
            # Unlinking an active executable is often blocked on Windows.
            # Rename fails safely before installation changes; rollback if
            # replacing current later fails.
            if current.exists():
                if not self._owned():
                    raise ManagedFFmpegError("Current installation is not Morphorum-managed.")
                current.rename(backup)
                swapped_old = True
            try:
                stage.rename(current)
            except OSError:
                if swapped_old and not current.exists():
                    backup.rename(current)
                    swapped_old = False
                raise
            self._update(job_id, status="installed", message="Managed FFmpeg and FFprobe are ready.",
                         progress=100.0, version=ff_ver, probe_version=pr_ver, error=None)
        except _Cancelled as exc:
            self._update(job_id, status="cancelled", message=str(exc), error=None)
        except Exception as exc:
            # A worker must always settle into a terminal state, even when a
            # malformed release, archive or unforeseen IO condition occurs.
            self._update(job_id, status="failed",
                         message="Managed FFmpeg installation failed.",
                         error=str(exc)[:400])
        finally:
            shutil.rmtree(temp, ignore_errors=True)
            if swapped_old and current.is_dir():
                shutil.rmtree(backup, ignore_errors=True)

    def remove(self) -> dict[str, Any]:
        with self._lock:
            if self._job and self._job["status"] in DOWNLOAD_STATES:
                raise ManagedFFmpegError("Cannot remove FFmpeg while an installation is running.")
            if not self._owned():
                raise ManagedFFmpegError("No Morphorum-managed FFmpeg installation to remove.")
            current = self.root / "current"
            retired = self.root / (".removed-" + uuid.uuid4().hex)
            try:
                current.rename(retired)
            except OSError as exc:
                raise ManagedFFmpegError(
                    "FFmpeg files may be in use. Close active exports and retry."
                ) from exc
            try:
                shutil.rmtree(retired)
            except OSError as exc:
                # Restore if removal failed; never destroy unowned folders.
                if not current.exists() and retired.exists():
                    try:
                        retired.rename(current)
                    except OSError:
                        pass
                raise ManagedFFmpegError("Could not remove managed FFmpeg files.") from exc
            return self.status()


managed_ffmpeg_manager = ManagedFFmpegManager()

"""P4.4.3 managed FFmpeg security, selection and non-destructive install tests."""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.morphorum import ffmpeg_tools
from backend.morphorum import managed_ffmpeg as managed


def _archive_bytes(*, evil: str | None = None, link: bool = False) -> bytes:
    names = ("ffmpeg.exe", "ffprobe.exe") if os.name == "nt" else ("ffmpeg", "ffprobe")
    data = io.BytesIO()
    if os.name == "nt":
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                item = zipfile.ZipInfo("bundle/bin/" + name)
                if link:
                    item.create_system = 3
                    item.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(item, b"safe-test-binary")
            if evil:
                archive.writestr(evil, b"evil")
    else:
        with tarfile.open(fileobj=data, mode="w:xz") as archive:
            for name in names:
                item = tarfile.TarInfo("bundle/bin/" + name)
                if link:
                    item.type = tarfile.SYMTYPE
                    item.linkname = "../../elsewhere"
                else:
                    item.size = len(b"safe-test-binary")
                archive.addfile(item, None if link else io.BytesIO(b"safe-test-binary"))
            if evil:
                item = tarfile.TarInfo(evil)
                item.size = len(b"evil")
                archive.addfile(item, io.BytesIO(b"evil"))
    return data.getvalue()


def _record(data: bytes) -> dict:
    return {
        "filename": managed.supported_asset(),
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/" +
               managed.supported_asset(),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "release": managed.RELEASE_PAGE, "tag": "latest",
    }


def test_platform_catalog_is_explicit():
    assert managed.supported_asset("Windows", "AMD64").endswith(".zip")
    assert managed.supported_asset("Linux", "aarch64").endswith(".tar.xz")
    assert managed.supported_asset("Darwin", "arm64") is None
    assert managed.supported_asset("Linux", "i686") is None
    assert all("-gpl-" in asset for asset in managed.ASSETS.values())


def test_release_requires_published_sha256_https_exact_asset(monkeypatch):
    asset = managed.supported_asset()
    example = {
        "name": asset, "size": 150, "digest": "sha256:" + "a" * 64,
        "browser_download_url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/" + asset,
    }
    monkeypatch.setattr(managed, "_read_release",
                        lambda: {"tag_name": "latest", "assets": [dict(example)]})
    assert managed.release_asset(asset)["sha256"] == "a" * 64
    with pytest.raises(managed.ManagedFFmpegError, match="Unsupported"):
        managed.release_asset("evil.exe")
    for patch in ({"digest": None}, {"size": 10**12}, {"browser_download_url":
                     "https://evil.example/ffmpeg.zip"}):
        monkeypatch.setattr(managed, "_read_release",
                            lambda patch=patch: {"assets": [dict(example, **patch)]})
        with pytest.raises(managed.ManagedFFmpegError, match="SHA-256"):
            managed.release_asset(asset)


def test_extract_only_two_binaries_and_rejects_traversal_links(tmp_path):
    data = _archive_bytes()
    archive = tmp_path / "source.pkg"
    archive.write_bytes(data)
    staging = tmp_path / "staging"
    managed._extract(archive, staging, threading.Event())
    expected = {"ffmpeg.exe", "ffprobe.exe"} if os.name == "nt" else {"ffmpeg", "ffprobe"}
    assert {p.name for p in (staging / "bin").iterdir()} == expected
    if os.name != "nt":
        assert all(os.access(p, os.X_OK) for p in (staging / "bin").iterdir())
    for i, variant in enumerate([
        _archive_bytes(evil="../../ffmpeg"),
        _archive_bytes(link=True),
    ]):
        bad = tmp_path / ("unsafe" + str(i))
        bad.write_bytes(variant)
        with pytest.raises(managed.ManagedFFmpegError, match="unsafe|symlink|Unsafe"):
            managed._extract(bad, tmp_path / ("bad" + str(i)), threading.Event())


def test_rejects_duplicate_executables(tmp_path):
    data = io.BytesIO()
    names = ("ffmpeg.exe", "ffprobe.exe") if os.name == "nt" else ("ffmpeg", "ffprobe")
    if os.name == "nt":
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("one/" + names[0], b"one")
            z.writestr("two/" + names[0], b"two")
            z.writestr("one/" + names[1], b"probe")
    else:
        with tarfile.open(fileobj=data, mode="w:xz") as tar:
            for filename, payload in [("one/" + names[0],b"one"),
                    ("two/" + names[0],b"two"), ("one/" + names[1],b"probe")]:
                item = tarfile.TarInfo(filename); item.size = len(payload)
                tar.addfile(item, io.BytesIO(payload))
    source = tmp_path / "duplicate.pkg"
    source.write_bytes(data.getvalue())
    with pytest.raises(managed.ManagedFFmpegError, match="Duplicate"):
        managed._extract(source, tmp_path / "dest", threading.Event())


def test_download_rejects_wrong_digest_without_extracting(tmp_path, monkeypatch):
    data = b"not the promised archive"
    record = _record(data)
    record["sha256"] = "0" * 64
    class FakeResponse:
        headers = {"Content-Length": str(len(data))}
        def geturl(self):
            return "https://release-assets.githubusercontent.com/test"
        def __enter__(self):
            self.stream = io.BytesIO(data)
            return self
        def __exit__(self, *_args):
            pass
        def read(self, size):
            return self.stream.read(size)
    monkeypatch.setattr(managed.urllib.request, "urlopen", lambda *_a, **_k: FakeResponse())
    with pytest.raises(managed.ManagedFFmpegError, match="SHA-256"):
        managed._download(record, tmp_path / "package", threading.Event(), lambda *_: None)


def test_cancel_does_not_touch_existing_install(tmp_path, monkeypatch):
    root = tmp_path / "tools" / "ffmpeg"
    current = root / "current"
    current.mkdir(parents=True)
    (current / "installation.json").write_text(json.dumps({
        "managed_by": "Morphorum", "provider": managed.PROJECT_URL,
    }))
    keep = current / "untouched.txt"; keep.write_text("original")
    m = managed.ManagedFFmpegManager(root)
    monkeypatch.setattr(managed, "release_asset", lambda *_: _record(_archive_bytes()))
    event = threading.Event(); event.set()
    m._job = {"id":"cancelled", "status":"checking"}
    m._run("cancelled", event)
    assert m.status()["job"]["status"] == "cancelled"
    assert keep.read_text() == "original"


def test_success_installs_after_verified_unpack_and_preserves_ownership(tmp_path, monkeypatch):
    archive = _archive_bytes()
    record = _record(archive)
    monkeypatch.setattr(managed, "release_asset", lambda *_: record)
    def download(_record, output, _cancel, progress):
        output.write_bytes(archive)
        progress(len(archive), len(archive))
    monkeypatch.setattr(managed, "_download", download)
    monkeypatch.setattr(ffmpeg_tools, "_version",
        lambda path, command: (command + " version test", None))
    monkeypatch.setattr(managed, "_validate_encoders",
        lambda _binary: sorted(managed.REQUIRED_ENCODERS))
    m = managed.ManagedFFmpegManager(tmp_path / "tools" / "ffmpeg")
    m._job = {"id": "successful", "status": "checking"}
    m._run("successful", threading.Event())
    result = m.status()
    assert result["installed"]
    assert result["job"]["status"] == "installed", result["job"]
    assert (m.root / "current" / "installation.json").is_file()
    assert "GPL" in (m.root / "current" / "LICENSE-NOTICE.txt").read_text()
    removed = m.remove()
    assert not removed["installed"]
    assert not (m.root / "current").exists()


def test_update_preserves_previous_install_when_job_starts_during_download(tmp_path, monkeypatch):
    archive = _archive_bytes()
    monkeypatch.setattr(managed, "release_asset", lambda *_: _record(archive))
    def download(_record, output, _cancel, progress):
        output.write_bytes(archive)
        progress(len(archive), len(archive))
    monkeypatch.setattr(managed, "_download", download)
    monkeypatch.setattr(ffmpeg_tools, "_version",
                        lambda path, command: (command + " version test", None))
    monkeypatch.setattr(managed, "_validate_encoders",
                        lambda _binary: sorted(managed.REQUIRED_ENCODERS))
    manager = managed.ManagedFFmpegManager(tmp_path / "ffmpeg")
    manager._job = {"id": "initial", "status": "checking"}
    manager._run("initial", threading.Event())
    assert manager.status()["installed"]
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    before = (manager.root / "current" / "bin" / name).read_bytes()
    manager._job = {"id": "blocked", "status": "checking"}
    manager._run("blocked", threading.Event(), lambda: True)
    assert manager.status()["job"]["status"] == "failed"
    assert "video export" in manager.status()["job"]["error"].lower()
    assert manager.status()["installed"]
    assert (manager.root / "current" / "bin" / name).read_bytes() == before


def test_missing_required_encoder_is_a_hard_failure(tmp_path, monkeypatch):
    binary = tmp_path / "ffmpeg"
    binary.write_text("dummy")
    expected = "\n".join(" " + ("V....." if name.startswith("lib") else "A.....") +
                         " " + name + " encoder" for name in
                         ("libx264", "libvpx-vp9", "aac"))
    monkeypatch.setattr(managed.subprocess, "run",
                        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=expected))
    with pytest.raises(managed.ManagedFFmpegError, match="libopus"):
        managed._validate_encoders(binary)
    assert managed.REQUIRED_ENCODERS == frozenset(
        {"libx264", "libvpx-vp9", "aac", "libopus"})


def test_encoder_validation_accepts_the_complete_codec_set(tmp_path, monkeypatch):
    expected = "\n".join(" " + ("A....." if name in ("aac", "libopus") else "V.....") +
                         " " + name + " encoder" for name in
                         sorted(managed.REQUIRED_ENCODERS))
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=expected)
    monkeypatch.setattr(managed.subprocess, "run", run)
    binary = tmp_path / "ffmpeg"
    assert set(managed._validate_encoders(binary)) == managed.REQUIRED_ENCODERS
    assert calls[0][0][1:] == ["-hide_banner", "-encoders"]
    assert calls[0][1]["timeout"] == managed.ENCODER_TIMEOUT
    assert calls[0][1]["stdin"] == managed.subprocess.DEVNULL


def test_crash_recovery_restores_only_an_owned_complete_previous_install(tmp_path):
    manager = managed.ManagedFFmpegManager(tmp_path / "ffmpeg")
    backup = manager.root / (".previous-" + "e" * 32)
    backup.mkdir(parents=True)
    bin_dir = backup / "bin"
    bin_dir.mkdir()
    for tool in ("ffmpeg", "ffprobe"):
        (bin_dir / ffmpeg_tools._bin_name(tool)).write_bytes(b"binary")
    (backup / "installation.json").write_text(json.dumps({
        "managed_by": "Morphorum", "provider": managed.PROJECT_URL,
    }))
    assert manager.status()["installed"]
    assert (manager.root / "current" / "installation.json").exists()
    assert not backup.exists()


def test_crash_recovery_refuses_ambiguous_backup_candidates(tmp_path):
    manager = managed.ManagedFFmpegManager(tmp_path / "ffmpeg")
    for suffix in ("a", "b"):
        backup = manager.root / (".previous-" + suffix * 32)
        backup.mkdir(parents=True)
        (backup / "installation.json").write_text(json.dumps({
            "managed_by": "Morphorum", "provider": managed.PROJECT_URL,
        }))
        (backup / "bin").mkdir()
        for binary in ("ffmpeg", "ffprobe"):
            (backup / "bin" / ffmpeg_tools._bin_name(binary)).write_bytes(b"binary")
    assert not manager.status()["installed"]
    assert not (manager.root / "current").exists()


def test_rejects_unowned_installation_on_start_and_remove(tmp_path):
    m = managed.ManagedFFmpegManager(tmp_path / "ffmpeg")
    (m.root / "current").mkdir(parents=True)
    (m.root / "current" / "personal.txt").write_text("mine")
    with pytest.raises(managed.ManagedFFmpegError, match="Unmanaged"):
        m.start()
    with pytest.raises(managed.ManagedFFmpegError, match="No Morphorum-managed"):
        m.remove()
    assert (m.root / "current" / "personal.txt").read_text() == "mine"

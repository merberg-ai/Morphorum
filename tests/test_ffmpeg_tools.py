"""P4.4.1 FFmpeg selection is deterministic and never silently falls back."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.morphorum import ffmpeg_tools as tools


def config(mode="auto", custom_path=""):
    return {"tools": {"ffmpeg": {"mode": mode, "custom_path": custom_path}}}


def fake_pair(tmp_path):
    root = tmp_path / "tool bin"
    root.mkdir()
    extension = ".exe" if os.name == "nt" else ""
    ffmpeg = root / ("ffmpeg" + extension)
    ffprobe = root / ("ffprobe" + extension)
    ffmpeg.write_text("fake executable")
    ffprobe.write_text("fake probe")
    return ffmpeg, ffprobe


def test_validates_modes_paths_and_rejects_invalid_explicit_saves():
    assert tools.normalize_ffmpeg_settings(None) == {"mode": "auto", "custom_path": ""}
    with pytest.raises(ValueError, match="mode"):
        tools.normalize_ffmpeg_settings({"mode": "unexpected"}, strict=True)
    with pytest.raises(ValueError, match="Select"):
        tools.normalize_ffmpeg_settings({"mode": "custom"}, strict=True)
    with pytest.raises(ValueError, match="invalid"):
        tools.normalize_ffmpeg_settings(
            {"mode": "custom", "custom_path": "invalid\npath"}, strict=True)
    assert tools.normalize_ffmpeg_settings({"mode": "unexpected"})["mode"] == "auto"


def test_auto_preserves_legacy_environment_precedence_without_fallback(monkeypatch):
    calls = []
    monkeypatch.setenv("MORPHORUM_FFMPEG", "/broken/ffmpeg")
    monkeypatch.setattr(tools.shutil, "which",
        lambda arg: calls.append(arg) or ("/path/ffprobe" if arg == "ffprobe" else None))
    choice = tools.select_ffmpeg(config())
    assert choice["source"] == "environment"
    assert choice["ffmpeg_path"] is None
    assert calls == ["/broken/ffmpeg", "ffprobe"]
    monkeypatch.delenv("MORPHORUM_FFMPEG", raising=False)
    assert tools.select_ffmpeg(config())["source"] == "system"
    assert calls[-2:] == ["ffmpeg", "ffprobe"]


def test_custom_validates_absolute_name_permissions_and_paired_ffprobe(tmp_path, monkeypatch):
    ffmpeg, ffprobe = fake_pair(tmp_path)
    monkeypatch.setattr(tools.os, "access", lambda *_args: True)
    monkeypatch.setattr(tools.shutil, "which", lambda *_args: "/system/ffmpeg")
    chosen = tools.select_ffmpeg(config("custom", str(ffmpeg)))
    assert chosen["ffmpeg_path"] == str(ffmpeg.resolve())
    assert chosen["ffprobe_path"] == str(ffprobe)
    assert tools.select_ffmpeg(config("custom", "ffmpeg"))["ffmpeg_path"] is None
    ffprobe.unlink()
    missing = tools.select_ffmpeg(config("custom", str(ffmpeg)))
    assert missing["ffmpeg_path"]
    assert missing["ffprobe_path"] is None  # no system fallback


def test_managed_selection_is_strict_and_does_not_invoke_install(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "MANAGED_BIN", tmp_path / "missing" / "bin")
    monkeypatch.setattr(tools.shutil, "which", lambda *_args: "/system/ffmpeg")
    selection = tools.select_ffmpeg(config("managed"))
    assert selection["ffmpeg_path"] is None
    assert selection["ffprobe_path"] is None
    assert not tools.ffmpeg_status(config("managed"))["available"]


def test_status_probes_versions_without_shell_and_detects_missing_probe(tmp_path, monkeypatch):
    ffmpeg, ffprobe = fake_pair(tmp_path)
    monkeypatch.setattr(tools.os, "access", lambda *_args: True)
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0, stdout=Path(args[0]).stem + " version 9.0 build\n",
            stderr="")
    monkeypatch.setattr(tools.subprocess, "run", run)
    status = tools.ffmpeg_status(config("custom", str(ffmpeg)))
    assert status["available"] and status["probe_available"]
    assert len(calls) == 2
    assert all(command[0][1:] == ["-version"] for command in calls)
    assert all(not options.get("shell", False) for _, options in calls)
    assert all(options["timeout"] == tools.VERSION_TIMEOUT for _, options in calls)
    ffprobe.unlink()
    degraded = tools.ffmpeg_status(config("custom", str(ffmpeg)))
    assert degraded["available"] and not degraded["probe_available"]
    assert "video import" in degraded["message"].lower()


def test_version_probe_rejects_wrong_program_and_timeout(monkeypatch):
    monkeypatch.setattr(tools.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0,
            stdout="not-ffmpeg version 1", stderr=""))
    assert tools._version("/fake/ffmpeg", "ffmpeg")[0] is None
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 5)
    monkeypatch.setattr(tools.subprocess, "run", timeout)
    version, message = tools._version("/fake/ffmpeg", "ffmpeg")
    assert version is None
    assert "TimeoutExpired" in message

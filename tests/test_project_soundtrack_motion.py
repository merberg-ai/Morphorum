"""A saved project soundtrack must feed Motion Studio without another upload."""
from __future__ import annotations

import hashlib
import io
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from morphorum import (
    audio_motion_upload, imported_soundtrack, project_assets,
    project_soundtrack_motion,
)
from morphorum.audio_motion import AudioMotionError
from morphorum.project_assets import ProjectAssetError


def pcm_wav(seconds=.3, rate=8000) -> bytes:
    count = round(rate * seconds)
    samples = [int(14000 * math.sin(2 * math.pi * 100 * n / rate))
               for n in range(count)]
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(struct.pack("<" + "h" * count, *samples))
    return output.getvalue()


@pytest.fixture
def storage(tmp_path, monkeypatch):
    for module in (imported_soundtrack, project_assets, audio_motion_upload):
        monkeypatch.setattr(
            module, "animation_project_directory", lambda project_id: tmp_path)
    return tmp_path


def test_attached_wav_is_reused_and_unchanged(storage, monkeypatch):
    data = pcm_wav()
    record = imported_soundtrack.store_soundtrack(
        "demo", data, filename="original.wav", offset_seconds=.75)
    monkeypatch.setattr(project_soundtrack_motion, "_convert_attached_audio",
                        lambda source: pytest.fail("No FFmpeg for a valid PCM WAV"))
    first = project_soundtrack_motion.analyze_project_soundtrack(
        "demo", fps=24, frames=12)
    assert first["converted_to_pcm"] is False
    assert first["analysis"]["source_sha256"] == record["sha256"]
    assert first["analysis"]["fps"] == 24
    assert first["soundtrack"]["offset_seconds"] == .75
    assert first["soundtrack"]["filename"] == "original.wav"
    assert first["analysis"]["values"] == pytest.approx(
        project_soundtrack_motion.analyze_project_soundtrack(
            "demo", fps=24, frames=12)["analysis"]["values"])
    assert imported_soundtrack.read_soundtrack("demo") == record
    assert (storage / "imported_soundtrack" /
            (record["sha256"] + ".wav")).read_bytes() == data
    managed = storage / "motion_lab_audio" / (record["sha256"] + ".wav")
    assert managed.read_bytes() == data


def test_mp3_uses_host_conversion_without_replacing_original(storage, monkeypatch):
    data = b"ID3" + b"fake-compressed-song" * 10
    original = imported_soundtrack.store_soundtrack(
        "demo", data, filename="music.mp3", offset_seconds=-1.125)
    converted = pcm_wav()
    path_checks = []
    def fake_convert(path):
        path_checks.append(path.read_bytes())
        return converted
    monkeypatch.setattr(project_soundtrack_motion, "_convert_attached_audio",
                        fake_convert)
    result = project_soundtrack_motion.analyze_project_soundtrack(
        "demo", fps=24, frames=12)
    assert path_checks == [data]
    assert result["converted_to_pcm"] is True
    assert result["analysis"]["source_sha256"] == hashlib.sha256(converted).hexdigest()
    assert result["soundtrack"] == {
        "filename": "music.mp3", "format": "mp3",
        "sha256": original["sha256"], "offset_seconds": -1.125,
    }
    assert imported_soundtrack.read_soundtrack("demo") == original
    assert (storage / "imported_soundtrack" /
            (original["sha256"] + ".mp3")).read_bytes() == data


def test_tampered_attachment_is_rejected_before_analysis(storage):
    record = imported_soundtrack.store_soundtrack(
        "demo", pcm_wav(), filename="good.wav", offset_seconds=0)
    path = storage / "imported_soundtrack" / (record["sha256"] + ".wav")
    path.write_bytes(b"RIFF" + b"tampered" * 4)
    with pytest.raises(ProjectAssetError, match="checksum mismatch"):
        project_soundtrack_motion.analyze_project_soundtrack(
            "demo", fps=24, frames=12)
    assert not (storage / "motion_lab_audio").exists()


def test_unattached_soundtrack_is_rejected(storage):
    with pytest.raises(ProjectAssetError, match="no attached soundtrack"):
        project_soundtrack_motion.analyze_project_soundtrack(
            "demo", fps=24, frames=12)


def test_missing_ffmpeg_is_actionable(storage, monkeypatch):
    original = imported_soundtrack.store_soundtrack(
        "demo", b"fLaC" + b"test" * 10,
        filename="music.flac", offset_seconds=0)
    monkeypatch.setattr(project_soundtrack_motion, "ffmpeg_executable", lambda: None)
    with pytest.raises(AudioMotionError, match="Install FFmpeg"):
        project_soundtrack_motion.analyze_project_soundtrack(
            "demo", fps=24, frames=12)
    assert imported_soundtrack.read_soundtrack("demo") == original


def test_host_converter_is_bounded_and_does_not_invoke_shell(storage, monkeypatch):
    source = storage / "song.mp3"
    source.write_bytes(b"ID3audio")
    pcm = pcm_wav()
    calls = []
    monkeypatch.setattr(project_soundtrack_motion, "ffmpeg_executable",
                        lambda: "/fake/ffmpeg")
    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        assert isinstance(args, list)
        assert args[0] == "/fake/ffmpeg"
        assert "-t" in args and args[args.index("-t") + 1] == "181"
        assert kwargs["timeout"] == 120
        Path(args[-1]).write_bytes(pcm)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(project_soundtrack_motion.subprocess, "run", fake_run)
    assert project_soundtrack_motion._convert_attached_audio(source) == pcm
    assert len(calls) == 1
    assert source.read_bytes() == b"ID3audio"

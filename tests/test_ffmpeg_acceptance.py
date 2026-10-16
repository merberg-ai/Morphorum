"""No-GPU FFmpeg acceptance fixture tests (run without FFmpeg installed)."""
from __future__ import annotations

import json
import struct
import wave
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ffmpeg_acceptance as smoke


def test_png_fixture_has_valid_dimensions_pixels_and_crc(tmp_path):
    filename = tmp_path / "frame.png"
    smoke._write_png(filename, 3)
    data = filename.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    length = struct.unpack(">I", data[8:12])[0]
    assert length == 13
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (smoke.SIZE, smoke.SIZE)
    content = data[12:16] + data[16:29]
    assert struct.unpack(">I", data[29:33])[0] == zlib.crc32(content) & 0xFFFFFFFF


def test_soundtrack_fixture_is_real_pcm_wav(tmp_path):
    filename = tmp_path / "sample.wav"
    smoke._write_wave(filename)
    with wave.open(str(filename), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24000
        assert wav.getnframes() == 24000
        assert len(wav.readframes(24000)) == 48000


def test_ffprobe_parser_rejects_invalid_or_empty_streams(monkeypatch, tmp_path):
    target = tmp_path / "output.webm"
    monkeypatch.setattr(smoke, "_command",
                        lambda *_args: SimpleNamespace(stdout='{"streams":[]}'))
    with pytest.raises(smoke.AcceptanceFailure, match="no streams"):
        smoke._probe("ffprobe", target)
    monkeypatch.setattr(smoke, "_command",
                        lambda *_args: SimpleNamespace(stdout='not json'))
    with pytest.raises(smoke.AcceptanceFailure, match="invalid JSON"):
        smoke._probe("ffprobe", target)
    monkeypatch.setattr(smoke, "_command",
                        lambda *_args: SimpleNamespace(stdout=json.dumps({
                            "streams": [{"codec_type": "video"}]
                        })))
    assert len(smoke._probe("ffprobe", target)["streams"]) == 1


def test_missing_ffmpeg_fails_without_creating_media(monkeypatch):
    monkeypatch.setattr(smoke, "ffmpeg_status", lambda *_a: {
        "source": "managed", "ffmpeg_path": None, "ffprobe_path": None,
        "available": False, "probe_available": False,
        "message": "Managed binary is missing.",
    })
    assert smoke.main(["--mode", "managed"]) == 1

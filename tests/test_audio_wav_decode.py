"""Vectorized Motion Lab WAV decoding must match the original per-sample decoder."""
from __future__ import annotations

import asyncio
import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from morphorum import audio_motion_upload
from morphorum.audio_motion import MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS, frame_envelope
from morphorum.audio_motion_upload import analyze_managed_wav


def _wav(width: int, channels: int, *, rate: int = 12000, frames: int = 6000) -> bytes:
    rng = np.random.default_rng(width * 10 + channels)
    raw = rng.integers(0, 256, size=frames * channels * width, dtype=np.uint8).tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(raw)
    return buffer.getvalue()


def _reference_decode(data: bytes) -> tuple[list[float], list[list[float]], int]:
    """The original pure-Python decoder, kept here as the reference behaviour."""
    with wave.open(io.BytesIO(data), "rb") as source:
        channels, width = source.getnchannels(), source.getsampwidth()
        rate, count = source.getframerate(), source.getnframes()
        raw = source.readframes(count)
    stride = channels * width
    mono: list[float] = []
    separate: list[list[float]] = [[] for _ in range(channels)]
    for index in range(count):
        total = 0.0
        for channel in range(channels):
            start = index * stride + channel * width
            segment = raw[start:start + width]
            if width == 1:
                value = (segment[0] - 128) / 128
            else:
                value = int.from_bytes(segment, "little", signed=True) / (2 ** (width * 8 - 1))
            separate[channel].append(value)
            total += value
        mono.append(total / channels)
    return mono, separate, rate


@pytest.mark.parametrize("width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2])
def test_vectorized_decode_matches_reference(width, channels, tmp_path, monkeypatch):
    monkeypatch.setattr(audio_motion_upload, "animation_project_directory", lambda _id: tmp_path)
    data = _wav(width, channels)
    result = analyze_managed_wav("decode", data, fps=12, frames=8)
    mono, separate, rate = _reference_decode(data)
    reference = frame_envelope(mono, sample_rate=rate, fps=12, max_frames=8)

    # Same canonical float32 sample digest: every decoded sample is identical.
    assert result["sha256"] == reference["sha256"]
    assert result["values"] == pytest.approx(reference["values"], rel=1e-12, abs=1e-15)
    assert result["channels"] == channels
    assert result["duration_seconds"] == len(mono) / rate

    bins = result["waveform"]["bins"]
    assert bins == min(1200, len(mono))
    for channel, bounds in zip(separate, result["waveform"]["channels"]):
        count = len(channel)
        expected = []
        for index in range(bins):
            begin = index * count // bins
            end = max(begin + 1, (index + 1) * count // bins)
            window = channel[begin:end]
            expected.append([round(min(window), 5), round(max(window), 5)])
        assert bounds == expected


def test_size_limit_fits_three_minutes_of_common_stereo_audio():
    for rate, width in ((44100, 2), (48000, 2), (48000, 3)):
        assert rate * 2 * width * MAX_AUDIO_SECONDS + 44 <= MAX_AUDIO_BYTES


def test_upload_analysis_runs_off_the_event_loop(monkeypatch):
    """The async upload endpoint must hand CPU-bound analysis to a worker thread."""
    from morphorum import app as app_module

    seen = {}

    def fake_analysis(project_id, data, *, fps, frames):
        try:
            asyncio.get_running_loop()
            seen["on_event_loop"] = True
        except RuntimeError:
            seen["on_event_loop"] = False
        seen["args"] = (project_id, len(data), fps, frames)
        return {"ok": True}

    monkeypatch.setattr(app_module, "analyze_managed_wav", fake_analysis)
    monkeypatch.setattr(app_module, "load_animation_project",
                        lambda _id: {"animation": {"fps": 24, "max_frames": 48}})
    with TestClient(app_module.app) as client:
        response = client.post(
            "/api/animation/projects/demo/motion-lab/audio-analyze", content=b"wav-bytes",
        )
    assert response.status_code == 200
    assert response.json() == {"status": "analyzed", "analysis": {"ok": True}}
    assert seen == {"on_event_loop": False, "args": ("demo", 9, 24.0, 48)}

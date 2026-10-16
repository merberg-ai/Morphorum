"""MS3 custom band analysis against bounded PCM WAV bytes."""
import io
import math
import struct
import wave

import numpy as np
import pytest
from morphorum.audio_channel_bands import analyze_frequency_bands
from morphorum.audio_motion import AudioMotionError


def wav(seconds=.8, rate=8000):
    count = int(seconds * rate)
    data = [int(20000 * math.sin(2 * math.pi * 90 * i / rate)
                + 7000 * math.sin(2 * math.pi * 1200 * i / rate))
            for i in range(count)]
    dest = io.BytesIO()
    with wave.open(dest, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(struct.pack("<" + "h" * count, *data))
    return dest.getvalue()


def test_custom_bands_return_separate_normalized_per_frame_envelopes():
    audio = wav()
    response = analyze_frequency_bands(
        audio, fps=24, frames=24, ranges=[
            {"id": "bass", "low_hz": 35, "high_hz": 200},
            {"id": "snare", "low_hz": 800, "high_hz": 1600},
        ])
    assert response["sample_rate"] == 8000
    assert response["nyquist_hz"] == 4000
    assert len(response["bands"]["bass"]) == 24
    assert all(0 <= v <= 1 for band in response["bands"].values() for v in band)
    assert any(v > .1 for v in response["bands"]["bass"])
    assert any(v > .1 for v in response["bands"]["snare"])
    assert response == analyze_frequency_bands(
        audio, fps=24, frames=24, ranges=[
            {"id": "bass", "low_hz": 35, "high_hz": 200},
            {"id": "snare", "low_hz": 800, "high_hz": 1600},
        ])


@pytest.mark.parametrize("ranges", [
    [{"id": "x", "low_hz": 3000, "high_hz": 6000}],
    [{"id": "x", "low_hz": float("nan"), "high_hz": 250}],
    [{"id": "x", "low_hz": 100, "high_hz": 105}],
    [{"id": "x", "low_hz": 35, "high_hz": 150}] * 2,
    [],
])
def test_bad_frequency_ranges_rejected(ranges):
    with pytest.raises(AudioMotionError):
        analyze_frequency_bands(wav(), fps=24, frames=24, ranges=ranges)


def test_audio_limits_enforced():
    with pytest.raises(AudioMotionError):
        analyze_frequency_bands(b"no-wav", fps=24, frames=24,
                                ranges=[{"id": "a", "low_hz": 35, "high_hz": 150}])
    with pytest.raises(AudioMotionError):
        analyze_frequency_bands(wav(), fps=0, frames=24,
                                ranges=[{"id": "a", "low_hz": 35, "high_hz": 150}])

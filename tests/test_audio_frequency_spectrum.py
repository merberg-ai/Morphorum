"""MS3b frequency visualizer: bounded, verified PCM FFT frequency profile."""
import io
import math
import struct
import wave

import pytest

from morphorum.audio_channel_bands import analyze_frequency_spectrum
from morphorum.audio_motion import AudioMotionError


def pcm_song(rate=8000, seconds=1.0):
    frames = round(rate * seconds)
    samples = [
        int(13000 * math.sin(2 * math.pi * 105 * i / rate) +
            5000 * math.sin(2 * math.pi * 1300 * i / rate))
        for i in range(frames)
    ]
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(struct.pack("<" + "h" * frames, *samples))
    return output.getvalue()


def test_spectrum_has_bounded_log_frequency_and_normalized_values():
    track = pcm_song()
    result = analyze_frequency_spectrum(track)
    assert result["sample_rate"] == 8000
    assert result["nyquist_hz"] == 4000
    assert result["frequency_min_hz"] == 20
    assert result["frequency_max_hz"] == 4000
    assert len(result["spectrum"]) == 96
    hz = [point["hz"] for point in result["spectrum"]]
    power = [point["level"] for point in result["spectrum"]]
    assert all(a < b for a, b in zip(hz, hz[1:]))
    assert all(0 <= v <= 1 for v in power)
    assert max(power) == 1
    assert any(75 <= h <= 150 and p > .5 for h,p in zip(hz,power))
    assert any(1050 <= h <= 1600 and p > .1 for h,p in zip(hz,power))
    assert result == analyze_frequency_spectrum(track)


@pytest.mark.parametrize("bins", [0, 16, 200, True, 32.5])
def test_invalid_resolution_is_rejected(bins):
    with pytest.raises(AudioMotionError):
        analyze_frequency_spectrum(pcm_song(seconds=.1), bins=bins)


def test_valid_short_clip_and_silent_wav_are_supported():
    short = analyze_frequency_spectrum(pcm_song(seconds=.05), bins=32)
    assert len(short["spectrum"]) == 32
    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 800)
    result = analyze_frequency_spectrum(data.getvalue())
    assert all(item["level"] == 0 for item in result["spectrum"])


def test_missing_or_unsafe_audio_is_rejected():
    with pytest.raises(AudioMotionError):
        analyze_frequency_spectrum(b"not-a-wav")
    with pytest.raises(AudioMotionError):
        analyze_frequency_spectrum(b"x" * (20 * 1024 * 1024 + 1))

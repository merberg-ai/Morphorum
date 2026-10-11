"""DA1.1 high-resolution audio onset regression tests."""
import numpy as np
import pytest

from morphorum.audio_events import detect_audio_events, event_frame_index
from morphorum.audio_motion import AudioMotionError


def burst_track(rate=12000, seconds=1.5):
    y = np.zeros(int(rate * seconds), dtype=np.float32)
    for second, hz in [(0.25, 72), (0.55, 900), (0.85, 72), (1.10, 900)]:
        start = round(second * rate)
        samples = np.arange(round(0.065 * rate), dtype=np.float32)
        decay = np.exp(-samples / (0.018 * rate))
        y[start:start + len(samples)] += 0.65 * decay * np.sin(2 * np.pi * hz * samples / rate)
    return y


def test_detects_timestamped_kick_and_snare_candidates_independent_of_video_fps():
    result = detect_audio_events(burst_track(), sample_rate=12000, sensitivity=0.2)
    assert result["analysis_version"] == 2
    assert result["duration_seconds"] == 1.5
    kicks = [e["time_seconds"] for e in result["events"] if e["kind"] == "kick"]
    snares = [e["time_seconds"] for e in result["events"] if e["kind"] == "snare"]
    assert any(abs(t - 0.25) < 0.05 for t in kicks)
    assert any(abs(t - 0.85) < 0.05 for t in kicks)
    assert any(abs(t - 0.55) < 0.05 for t in snares)
    assert any(abs(t - 1.10) < 0.05 for t in snares)
    assert result == detect_audio_events(burst_track(), sample_rate=12000, sensitivity=0.2)


def test_stereo_input_and_silence_are_safe():
    left = burst_track()
    stereo = np.stack([left, left * 0.5], axis=1)
    result = detect_audio_events(stereo, sample_rate=12000)
    assert result["channels"] == 2
    assert result["events"]
    assert detect_audio_events(np.zeros(12000), sample_rate=12000)["events"] == []


def test_event_time_remains_stable_as_fps_changes():
    assert event_frame_index(0.251, fps=12, max_frames=100) == 3
    assert event_frame_index(0.251, fps=30, max_frames=100) == 8
    assert event_frame_index(5.0, fps=30, max_frames=100) is None


@pytest.mark.parametrize("data,rate", [
    ([], 12000), ([float("nan")] * 500, 12000),
    ([1.2] * 500, 12000), ([[0, 0, 0]] * 500, 12000),
    ([0] * 500, 100),
])
def test_bad_audio_is_rejected(data, rate):
    with pytest.raises(AudioMotionError):
        detect_audio_events(data, sample_rate=rate)


def test_invalid_frame_mapping_is_rejected():
    with pytest.raises(AudioMotionError):
        event_frame_index(float("nan"), fps=30, max_frames=100)
    with pytest.raises(AudioMotionError):
        event_frame_index(0.25, fps=0, max_frames=100)

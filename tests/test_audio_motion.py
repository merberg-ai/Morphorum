"""Regression tests for ML3 CPU envelope/pulse foundation."""
import math
import pytest

from morphorum.audio_motion import (
    AudioMotionError, frame_envelope, balanced_pulses,
)


def test_frame_aligned_rms_and_stable_content_digest():
    rate = 12000
    pcm = [0.0] * 3000
    pcm[1000:2000] = [0.5] * 1000
    result = frame_envelope(pcm, sample_rate=rate, fps=12, max_frames=5)
    assert result["kind"] == "fullband-rms"
    assert result["frames"] == 5
    assert result["values"] == pytest.approx([0, 0.5, 0, 0, 0])
    assert result["sha256"] == frame_envelope(pcm, sample_rate=rate, fps=12, max_frames=5)["sha256"]


def test_threshold_edges_and_bounded_balanced_return():
    envelope = [0, 0.9, 0.9, 0, 0, 0.7, 0, 0, 0, 0, 0, 0]
    pulse = balanced_pulses(envelope, threshold=0.5, distance=0.06,
                            attack_frames=2, release_frames=3,
                            cooldown_frames=0)
    assert pulse[0] == 0
    assert pulse[1:6] == pytest.approx([0.03, 0.03, -0.02, -0.02, -0.02])
    assert sum(pulse) == pytest.approx(0, abs=1e-12)
    assert pulse[5] != 0  # second onset overlaps the return, so it is skipped


def test_early_and_trailing_beats_not_partially_committed():
    assert balanced_pulses([0.9, 0, 0, 0, 0], attack_frames=1,
                           release_frames=2) == [0] * 5
    assert balanced_pulses([0, 0, 0, 0.9, 0], attack_frames=1,
                           release_frames=3) == [0] * 5


def test_offset_preserves_frame_alignment_and_zero_sum():
    values = balanced_pulses([0, 0.9] + [0] * 12, offset_frames=3,
                             attack_frames=1, release_frames=2,
                             distance=0.1)
    assert values[4:7] == pytest.approx([0.1, -0.05, -0.05])
    assert sum(values) == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize("samples,rate,fps", [
    ([0, float("nan")], 12000, 12),
    ([2.0], 12000, 12),
    ([0.2], 1, 12),
    ([0.2], 12000, 0),
    ([], 12000, 12),
])
def test_pcm_validation(samples, rate, fps):
    with pytest.raises(AudioMotionError):
        frame_envelope(samples, sample_rate=rate, fps=fps)


@pytest.mark.parametrize("args", [
    {"distance": float("inf")}, {"threshold": -0.1},
    {"attack_frames": 0}, {"release_frames": 0},
    {"offset_frames": 1.5}, {"cooldown_frames": -1},
])
def test_pulse_validation(args):
    with pytest.raises(AudioMotionError):
        balanced_pulses([0, 1, 0], **args)

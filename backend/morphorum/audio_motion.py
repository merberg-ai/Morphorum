"""Deterministic CPU audio envelope and balanced frame-aligned motion pulses.

ML3 foundation only. Callers provide decoded mono PCM samples; no uploaded media,
GPU model, project mutation or audio decoding happens in this module.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Sequence


class AudioMotionError(ValueError):
    """Malformed or unsafe audio-motion configuration."""


def _finite(value: object, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise AudioMotionError(f"{name} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AudioMotionError(f"{name} must be numeric.") from exc
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise AudioMotionError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def frame_envelope(
    samples: Sequence[float], *, sample_rate: int, fps: float,
    max_frames: int = 3000,
) -> dict:
    """Measure mean-square energy on exact project-frame sample boundaries.

    This is a full-band RMS envelope (not yet a bass-band filter). The input is
    already decoded PCM; conversion and upload belong to the later ML3 API slice.
    """
    rate = int(_finite(sample_rate, "Sample rate", 8000, 192000))
    if rate != sample_rate:
        raise AudioMotionError("Sample rate must be an integer.")
    clock = _finite(fps, "Project FPS", 1, 240)
    if not isinstance(max_frames, int) or isinstance(max_frames, bool) or not 1 <= max_frames <= 3000:
        raise AudioMotionError("max_frames must be 1–3000.")
    if not isinstance(samples, (list, tuple)) or not samples:
        raise AudioMotionError("PCM input must be a nonempty list or tuple.")
    if len(samples) > 192000 * 600:
        raise AudioMotionError("PCM input exceeds 10 minutes at 192 kHz.")
    pcm = [_finite(v, "PCM sample", -1, 1) for v in samples]
    # Stable digest on canonical little-endian float32 samples.
    digest = hashlib.sha256()
    for value in pcm:
        digest.update(struct.pack("<f", value))
    envelope = []
    for frame in range(max_frames):
        begin = math.floor(frame * rate / clock)
        end = min(len(pcm), math.floor((frame + 1) * rate / clock))
        if begin >= len(pcm):
            envelope.append(0.0)
        elif end <= begin:
            envelope.append(0.0)
        else:
            energy = sum(v * v for v in pcm[begin:end]) / (end - begin)
            envelope.append(math.sqrt(energy))
    return {
        "analysis_version": 1,
        "kind": "fullband-rms",
        "sha256": digest.hexdigest(),
        "sample_rate": rate,
        "fps": clock,
        "frames": len(envelope),
        "values": envelope,
    }


def balanced_pulses(
    envelope: Sequence[float], *,
    threshold: float = 0.25,
    distance: float = 0.04,
    attack_frames: int = 1,
    release_frames: int = 3,
    cooldown_frames: int = 3,
    offset_frames: int = 0,
    max_frames: int | None = None,
) -> list[float]:
    """Convert onset crossings to travel-neutral native camera velocity pulses.

    For every triggered beat, a positive impulse is followed by a negative
    return with exactly equal total area. Pulse windows never overlap.
    Frame 0 is stationary. Parameters use integer frame counts so results
    are repeatable across preview, Apply and rendering.
    """
    if not isinstance(envelope, (list, tuple)):
        raise AudioMotionError("Envelope must be a list or tuple.")
    limit = len(envelope) if max_frames is None else max_frames
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 3000:
        raise AudioMotionError("Frame count must be 1–3000.")
    levels = [_finite(v, "Envelope level", 0, 1) for v in envelope]
    gate = _finite(threshold, "Threshold", 0, 1)
    amount = _finite(distance, "Pulse distance", 0, 30)
    lengths = []
    for name, value, low, high in (
        ("Attack frames", attack_frames, 1, 120),
        ("Release frames", release_frames, 1, 120),
        ("Cooldown frames", cooldown_frames, 0, 120),
        ("Offset frames", offset_frames, -3000, 3000),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise AudioMotionError(f"{name} must be an integer between {low} and {high}.")
        lengths.append(value)
    attack, release, cooldown, offset = lengths
    output = [0.0] * limit
    available = 1
    was_above = False
    for source_frame, level in enumerate(levels):
        above = level >= gate and level > 0
        trigger = above and not was_above
        was_above = above
        if not trigger:
            continue
        start = source_frame + offset
        if start < available or start < 1 or start + attack + release > limit:
            continue
        # Area positive == area negative. Full pulses or nothing, never a
        # truncated trailing return which would create permanent travel.
        for i in range(start, start + attack):
            output[i] = amount / attack
        for i in range(start + attack, start + attack + release):
            output[i] = -amount / release
        available = start + attack + release + cooldown
    return output

# Bands are intended as practical targeting filters, not source separation.
AUDIO_BANDS = {"kick": (35, 140), "bass": (40, 250),
               "snare": (150, 2400), "highs": (2500, 10000)}


def spectral_band_envelopes(samples: Sequence[float], *, sample_rate: int,
                            fps: float, max_frames: int) -> dict[str, list[float]]:
    """Windowed FFT band power, normalized per-band for UI thresholding."""
    import numpy as np
    rate = int(_finite(sample_rate, "Sample rate", 8000, 192000))
    clock = _finite(fps, "Project FPS", 1, 240)
    if not 1 <= max_frames <= 3000:
        raise AudioMotionError("Invalid analysis frame count.")
    y = np.asarray(samples, dtype=np.float32)
    if not y.size or not np.all(np.isfinite(y)):
        raise AudioMotionError("Invalid audio samples.")
    window_size = 4096 if rate >= 16000 else 2048
    window = np.hanning(window_size).astype(np.float32)
    freqs = np.fft.rfftfreq(window_size, 1 / rate)
    masks = {name: (freqs >= low) & (freqs < high)
             for name, (low, high) in AUDIO_BANDS.items()}
    powers = {name: [] for name in AUDIO_BANDS}
    for frame in range(max_frames):
        center = int((frame + .5) * rate / clock)
        start = center - window_size // 2
        a, b = max(0, start), min(len(y), start + window_size)
        segment = np.zeros(window_size, dtype=np.float32)
        if b > a:
            segment[a - start:a - start + b - a] = y[a:b]
        power = np.abs(np.fft.rfft(segment * window)) ** 2
        for name, mask in masks.items():
            powers[name].append(float(np.sqrt(np.sum(power[mask]))))
    return {name: [round(min(1., v / max(peak, 1e-12)), 7) for v in vals]
            for name, vals in powers.items()
            for peak in [max(vals, default=0.)]}


def onset_strength(envelope: Sequence[float], sensitivity: float = .35) -> list[float]:
    """Positive spectral-energy change, smoothed against very short changes.

    Output is a 0..1 onset signal that can be used by the same deterministic
    threshold/pulse compiler as full-band RMS. Sensitivity is relative to the
    peak positive difference, so the controls scale across recordings.
    """
    level = _finite(sensitivity, "Transient sensitivity", 0, 1)
    vals = [_finite(v, "Envelope", 0, 1) for v in envelope]
    rise = [0.] + [max(0., vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    peak = max(rise, default=0)
    if peak <= 1e-12:
        return [0.] * len(vals)
    return [round(max(0., min(1., v / peak - level * .5)), 7) for v in rise]

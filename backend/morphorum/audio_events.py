"""High-resolution, FPS-independent audio transient analysis (DA1.1).

This is a deterministic CPU signal-processing detector, NOT drum-stem separation.
"kick" and "snare" are spectral attack candidates and may include bass guitar,
vocals or other overlapping instruments. No project is modified by this module.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy.signal import find_peaks, stft

from .audio_motion import AudioMotionError

ANALYSIS_VERSION = 3
# Ordered low to high: spill suppression compares a band against lower ones.
BANDS_HZ = {"kick": (35.0, 150.0), "snare": (180.0, 4000.0),
            "highs": (2500.0, 10000.0)}
# Version 3 spill suppression: an event counts as spill when it lies within
# BLEED_WINDOW_MS of a lower band's event and is at least 30 dB weaker per
# FFT bin. A band's spill is dropped only if it makes up nearly all of it.
BLEED_WINDOW_MS = 25.0
BLEED_RATIO = 10 ** (-30 / 20)
BLEED_SHARE = 0.9
MAX_SECONDS = 180
MAX_EVENTS = 12000


def detect_audio_events(
    samples: Sequence[float] | np.ndarray, *,
    sample_rate: int,
    hop_ms: float = 5.0,
    sensitivity: float = 0.45,
    min_interval_ms: float = 45.0,
    max_seconds: float = MAX_SECONDS,
) -> dict:
    """Detect timestamped low/mid/high spectral attacks independently of video FPS.

    Accepts samples shaped (time,) or (time, 1|2); stereo remains distinguishable
    in metadata but is combined for this first-pass detector. Returns events at
    sample-derived times; frame assignment is intentionally deferred.
    """
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
        raise AudioMotionError("Sample rate must be an integer.")
    if not 8000 <= sample_rate <= 192000:
        raise AudioMotionError("Sample rate must be between 8000 and 192000.")
    for name, value, low, high in (
        ("Hop milliseconds", hop_ms, 2.0, 20.0),
        ("Sensitivity", sensitivity, 0.0, 1.0),
        ("Minimum interval", min_interval_ms, 10.0, 500.0),
        ("Maximum duration", max_seconds, 1.0, MAX_SECONDS),
    ):
        try:
            numeric = float(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise AudioMotionError(f"{name} must be finite and within its bounds.") from exc
        if not math.isfinite(numeric) or not low <= numeric <= high:
            raise AudioMotionError(f"{name} must be between {low:g} and {high:g}.")
    try:
        pcm = np.asarray(samples, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AudioMotionError("Invalid PCM data.") from exc
    if pcm.ndim not in (1, 2) or not pcm.size:
        raise AudioMotionError("PCM input must be nonempty mono or stereo samples.")
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    if channels not in (1, 2):
        raise AudioMotionError("Only mono and stereo PCM are supported.")
    length = pcm.shape[0]
    if length > int(sample_rate * max_seconds):
        raise AudioMotionError("PCM exceeds maximum analysis duration.")
    if not np.all(np.isfinite(pcm)) or np.any(np.abs(pcm) > 1.0):
        raise AudioMotionError("PCM must contain finite normalized samples.")
    mono = pcm if pcm.ndim == 1 else pcm.mean(axis=1)
    hop = max(1, round(sample_rate * float(hop_ms) / 1000))
    fft_size = 4096 if sample_rate >= 32000 else 2048
    fft_size = min(fft_size, max(256, 2 ** int(math.ceil(math.log2(length)))))
    hop = min(hop, max(1, fft_size // 2))
    if length < 256:
        return {"analysis_version": ANALYSIS_VERSION, "hop_ms": 1000 * hop / sample_rate,
                "sample_rate": sample_rate, "channels": channels,
                "duration_seconds": length / sample_rate, "events": []}
    # SciPy reduces nperseg automatically on short tracks but retains the
    # caller's old noverlap, which otherwise raises instead of analyzing a
    # perfectly valid short project WAV. Bound both explicitly.
    fft_size = min(fft_size, length)
    hop = min(hop, max(1, fft_size // 2))
    freqs, times, transform = stft(
        mono, fs=sample_rate, window="hann", nperseg=fft_size,
        noverlap=fft_size - hop, boundary="zeros", padded=True,
    )
    magnitude = np.abs(transform)
    events = []
    gap = max(1, math.ceil(float(min_interval_ms) * sample_rate / (1000 * hop)))
    detected: list[tuple[str, np.ndarray, np.ndarray]] = []
    for name, (low, high) in BANDS_HZ.items():
        band = magnitude[(freqs >= low) & (freqs < min(high, sample_rate / 2))]
        if band.size == 0:
            continue
        # Positive spectral flux emphasizes attacks, not sustained loudness.
        novelty = np.maximum(0.0, np.diff(band, axis=1, prepend=band[:, :1])).sum(axis=0)
        peak = float(novelty.max(initial=0))
        if peak <= 1e-10:
            continue
        normalized = novelty / peak
        # Local prominence rejects broadband background while allowing quieter
        # attacks near loud ones. Sensitivity increases the detection threshold.
        height = 0.08 + 0.62 * float(sensitivity)
        positions, props = find_peaks(
            normalized, height=height, prominence=max(0.035, height * 0.4),
            distance=gap,
        )
        # Mean flux per FFT bin is comparable between bands of different width.
        per_bin = novelty[positions] / band.shape[0]
        keep = np.ones(len(positions), dtype=bool)
        # Each band is normalized to its own loudest attack, so a band with no
        # content of its own would otherwise report the faint spill of a lower
        # band's hit as full-strength events. Treat a band as spill only when
        # nearly all of its events sit on a lower band's event and are far
        # weaker there; a band with independent attacks is never touched.
        if len(positions) and detected:
            window = max(1, round(BLEED_WINDOW_MS * sample_rate / (1000 * hop)))
            lower_positions = np.concatenate([item[1] for item in detected])
            lower_per_bin = np.concatenate([item[2] for item in detected])
            if lower_positions.size:
                order = np.argsort(lower_positions, kind="stable")
                lower_positions, lower_per_bin = lower_positions[order], lower_per_bin[order]
                right = np.clip(np.searchsorted(lower_positions, positions), 0, lower_positions.size - 1)
                left = np.clip(right - 1, 0, lower_positions.size - 1)
                nearest = np.where(
                    np.abs(lower_positions[left] - positions)
                    <= np.abs(lower_positions[right] - positions), left, right,
                )
                spill = (
                    (np.abs(lower_positions[nearest] - positions) <= window)
                    & (per_bin < lower_per_bin[nearest] * BLEED_RATIO)
                )
                if spill.sum() >= BLEED_SHARE * len(positions):
                    keep = ~spill
        detected.append((name, positions[keep], per_bin[keep]))
        for idx, strength in zip(positions[keep], props["peak_heights"][keep]):
            seconds = float(times[int(idx)])
            if seconds >= length / sample_rate:
                continue
            events.append({
                "id": f"{name}-{int(idx):06d}",
                "kind": name,
                "time_seconds": round(seconds, 6),
                "sample_index": min(length - 1, round(seconds * sample_rate)),
                "strength": round(float(strength), 6),
                "source": "spectral_flux",
            })
    events.sort(key=lambda event: (event["time_seconds"], event["kind"]))
    if len(events) > MAX_EVENTS:
        raise AudioMotionError("Too many detected audio events.")
    return {
        "analysis_version": ANALYSIS_VERSION,
        "hop_ms": round(1000 * hop / sample_rate, 6),
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": length / sample_rate,
        "events": events,
    }


def event_frame_index(time_seconds: float, *, fps: float, max_frames: int) -> int | None:
    """Quantize a timestamp to the nearest available project-frame index."""
    if not math.isfinite(time_seconds) or time_seconds < 0:
        raise AudioMotionError("Event timestamp must be nonnegative and finite.")
    if not math.isfinite(fps) or fps <= 0 or fps > 240:
        raise AudioMotionError("Invalid project FPS.")
    if not isinstance(max_frames, int) or isinstance(max_frames, bool) or not 1 <= max_frames <= 3000:
        raise AudioMotionError("Invalid project frame count.")
    frame = math.floor(time_seconds * fps + 0.5)
    return frame if frame < max_frames else None

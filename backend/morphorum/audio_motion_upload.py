"""Project-managed WAV upload and frame-aligned audio analysis for ML3.1.

WAV PCM is decoded with the standard library. Other codecs and bass-band
analysis are deliberately deferred until a controlled FFmpeg integration.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import wave

from .audio_motion import (
    MAX_AUDIO_BYTES, MAX_AUDIO_MEBIBYTES, MAX_AUDIO_SECONDS,
    AudioMotionError, frame_envelope_array, spectral_band_envelopes,
)
from .audio_events import detect_audio_events
from .animation_projects import animation_project_directory

MAX_SECONDS = MAX_AUDIO_SECONDS
MAX_PROJECT_FRAMES = 3000
FPS_CHOICES = (12, 24, 30, 60)


def audio_fps_recommendations(duration_seconds: float, *, current_fps: float) -> dict:
    """Offer safe choices; never mutate a project's FPS or its timeline."""
    import math
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise AudioMotionError("Invalid audio duration.")
    if not math.isfinite(current_fps) or not 1 <= current_fps <= 240:
        raise AudioMotionError("Invalid project FPS.")
    choices = []
    for fps in FPS_CHOICES:
        frames = math.ceil(duration_seconds * fps)
        choices.append({"fps": fps, "max_frames": frames,
                        "supported": frames <= MAX_PROJECT_FRAMES,
                        "frame_ms": round(1000 / fps, 4)})
    current_frames = math.ceil(duration_seconds * current_fps)
    preferred = next((c["fps"] for c in reversed(choices)
                      if c["supported"] and c["fps"] <= 30), None)
    return {"recommended_fps": preferred, "current_fps": current_fps,
            "current_required_frames": current_frames,
            "current_supported": current_frames <= MAX_PROJECT_FRAMES,
            "options": choices,
            "requires_explicit_project_update": True,
            "existing_motion_requires_manual_retiming": True}


def analyze_managed_wav(project_id: str, data: bytes, *, fps: float, frames: int) -> dict:
    import numpy as np
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise AudioMotionError(f"WAV must be nonempty and at most {MAX_AUDIO_MEBIBYTES} MiB.")
    try:
        with wave.open(io.BytesIO(data), "rb") as input_file:
            channels = input_file.getnchannels()
            rate = input_file.getframerate()
            width = input_file.getsampwidth()
            count = input_file.getnframes()
            if channels not in (1, 2) or width not in (1, 2, 3, 4) or not 8000 <= rate <= 192000:
                raise AudioMotionError("Use mono/stereo PCM WAV (8–32 bit, 8–192 kHz).")
            if count > rate * MAX_SECONDS:
                raise AudioMotionError("WAV exceeds three minutes.")
            audio_bytes = input_file.readframes(count)
    except (wave.Error, EOFError, OSError) as exc:
        raise AudioMotionError("Could not decode PCM WAV.") from exc
    stride = channels * width
    if len(audio_bytes) != count * stride:
        raise AudioMotionError("Incomplete WAV audio data.")
    if not count:
        raise AudioMotionError("PCM input must be a nonempty list or tuple.")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not 1 <= fps <= 240:
        raise AudioMotionError("Project FPS must be between 1 and 240.")
    if type(frames) is not int or not 1 <= frames <= MAX_PROJECT_FRAMES:
        raise AudioMotionError("max_frames must be 1–3000.")
    # Vectorized decode in float64 so every sample, and the mono mix, is
    # bit-identical to exact integer/scale division (and to earlier analyses).
    if width == 1:
        integers = np.frombuffer(audio_bytes, dtype=np.uint8).astype(np.int64) - 128
    elif width == 2:
        integers = np.frombuffer(audio_bytes, dtype="<i2").astype(np.int64)
    elif width == 4:
        integers = np.frombuffer(audio_bytes, dtype="<i4").astype(np.int64)
    else:  # signed 24-bit PCM, sign-extended
        packed = np.frombuffer(audio_bytes, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
        integers = packed[:, 0] | (packed[:, 1] << 8) | (packed[:, 2] << 16)
        integers = (integers ^ 0x800000) - 0x800000
    samples = integers.reshape(count, channels).astype(np.float64) / float(2 ** (width * 8 - 1))
    del integers
    stereo_samples = [np.ascontiguousarray(samples[:, channel]) for channel in range(channels)]
    pcm = stereo_samples[0] if channels == 1 else (stereo_samples[0] + stereo_samples[1]) / 2
    del samples
    result = frame_envelope_array(pcm, sample_rate=rate, fps=float(fps), max_frames=frames)
    result["bands"] = spectral_band_envelopes(pcm, sample_rate=rate, fps=fps, max_frames=frames)
    source_sha256 = hashlib.sha256(data).hexdigest()
    folder = animation_project_directory(project_id) / "motion_lab_audio"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (source_sha256 + ".wav")
    if not destination.exists():
        temp = folder / (source_sha256 + ".upload")
        try:
            with temp.open("wb") as out:
                out.write(data)
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)
    result["source_sha256"] = source_sha256
    result["filename"] = destination.name
    result["duration_seconds"] = count / rate
    result["channels"] = channels
    # Display-only waveform overview: bounded min/max bins retain transients,
    # never send raw PCM or use these bins for drum detection.
    bin_count = min(1200, max(1, count))
    # bin_count never exceeds count, so bin starts strictly increase and each
    # bin runs up to the next start: exactly what reduceat computes.
    starts = np.arange(bin_count, dtype=np.int64) * count // bin_count
    waveform = []
    for channel in stereo_samples:
        lows = np.minimum.reduceat(channel, starts)
        highs = np.maximum.reduceat(channel, starts)
        waveform.append([[round(float(low), 5), round(float(high), 5)]
                         for low, high in zip(lows, highs)])
    result["waveform"] = {"version": 1, "channels": waveform,
                          "bins": bin_count, "duration_seconds": count / rate}
    result["events"] = detect_audio_events(pcm, sample_rate=rate)
    result["fps_recommendations"] = audio_fps_recommendations(count / rate, current_fps=fps)
    return result

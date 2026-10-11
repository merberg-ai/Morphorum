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

from .audio_motion import AudioMotionError, frame_envelope, spectral_band_envelopes
from .audio_events import detect_audio_events
from .animation_projects import animation_project_directory

MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_SECONDS = 180
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
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise AudioMotionError("WAV must be nonempty and at most 20 MiB.")
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
    pcm = []
    for index in range(count):
        total = 0.0
        for channel in range(channels):
            i = index * stride + channel * width
            segment = audio_bytes[i:i + width]
            if width == 1:
                value = (segment[0] - 128) / 128
            else:
                value = int.from_bytes(segment, "little", signed=True) / (2 ** (width * 8 - 1))
            total += value
        pcm.append(total / channels)
    result = frame_envelope(pcm, sample_rate=rate, fps=fps, max_frames=frames)
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
    result["events"] = detect_audio_events(pcm, sample_rate=rate)
    result["fps_recommendations"] = audio_fps_recommendations(count / rate, current_fps=fps)
    return result

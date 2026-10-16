"""MS3: independent, bounded frequency-band analysis of verified project WAVs."""
from __future__ import annotations

import io
import math
import re
import wave

from .audio_motion import AudioMotionError
from .audio_motion_channels import MAX_CHANNELS

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_SECONDS = 180


def _decode_pcm(data: bytes):
    import numpy as np
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise AudioMotionError("Stored WAV must be nonempty and at most 20 MiB.")
    try:
        with wave.open(io.BytesIO(data), "rb") as file:
            channels, width, rate, count = (
                file.getnchannels(), file.getsampwidth(),
                file.getframerate(), file.getnframes(),
            )
            if channels not in (1, 2) or width not in (1, 2, 3, 4) or not 8000 <= rate <= 192000:
                raise AudioMotionError("Use mono/stereo PCM WAV (8–32 bit, 8–192 kHz).")
            if not 0 < count <= rate * MAX_SECONDS:
                raise AudioMotionError("Stored WAV exceeds three minutes or is empty.")
            raw = file.readframes(count)
    except (wave.Error, OSError, EOFError) as exc:
        raise AudioMotionError("Could not decode stored PCM WAV.") from exc
    if len(raw) != count * channels * width:
        raise AudioMotionError("Stored WAV has incomplete PCM data.")
    if width == 1:
        pcm = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    elif width == 4:
        pcm = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648
    else:  # signed 24-bit PCM, sign-extended before float normalization
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        signed = packed[:, 0] | (packed[:, 1] << 8) | (packed[:, 2] << 16)
        signed = (signed ^ 0x800000) - 0x800000
        pcm = signed.astype(np.float32) / 8388608
    return pcm.reshape(count, channels).mean(axis=1), rate


def analyze_frequency_bands(data: bytes, *, fps: float, frames: int,
                            ranges: list[dict]) -> dict:
    """One FFT pass for up to eight independently specified, normalized bands."""
    import numpy as np
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 240:
        raise AudioMotionError("Invalid project FPS.")
    if type(frames) is not int or not 1 <= frames <= 3000:
        raise AudioMotionError("Invalid project frame count.")
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= MAX_CHANNELS:
        raise AudioMotionError("Choose between one and eight frequency channels.")
    pcm, rate = _decode_pcm(data)
    nyquist = rate / 2
    bands = []
    used = set()
    for item in ranges:
        if not isinstance(item, dict):
            raise AudioMotionError("Frequency channel must be an object.")
        key = item.get("id")
        if not isinstance(key, str) or not _ID.fullmatch(key) or key in used:
            raise AudioMotionError("Band IDs must be unique and safe.")
        used.add(key)
        low, high = item.get("low_hz"), item.get("high_hz")
        try:
            if isinstance(low, bool) or isinstance(high, bool):
                raise ValueError()
            low, high = float(low), float(high)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AudioMotionError("Frequency limits must be numeric.") from exc
        if not math.isfinite(low) or not math.isfinite(high) or not 20 <= low < high <= min(20000, nyquist):
            raise AudioMotionError("Frequency range must be within 20 Hz and WAV Nyquist.")
        if high - low < 10:
            raise AudioMotionError("Frequency band must span at least 10 Hz.")
        bands.append((key, low, high))
    window_size = 4096 if rate >= 16000 else 2048
    window = np.hanning(window_size).astype(np.float32)
    freqs = np.fft.rfftfreq(window_size, 1 / rate)
    masks = []
    for ident, low, high in bands:
        mask = (freqs >= low) & (freqs < high)
        if not mask.any():
            raise AudioMotionError("Frequency band is narrower than the FFT resolution.")
        masks.append((ident, mask))
    powers = {ident: [] for ident, _, _ in bands}
    for frame in range(frames):
        center = int((frame + .5) * rate / fps)
        start = center - window_size // 2
        left, right = max(0, start), min(len(pcm), start + window_size)
        segment = np.zeros(window_size, dtype=np.float32)
        if right > left:
            segment[left - start:left - start + right - left] = pcm[left:right]
        spectrum = np.abs(np.fft.rfft(segment * window)) ** 2
        for ident, mask in masks:
            powers[ident].append(float(np.sqrt(np.sum(spectrum[mask]))))
    output = {}
    for ident, values in powers.items():
        peak = max(values, default=0.)
        output[ident] = [round(min(1., val / max(peak, 1e-12)), 7) for val in values]
    return {
        "schema_version": 1, "fps": fps, "max_frames": frames,
        "sample_rate": rate, "nyquist_hz": nyquist, "bands": output,
    }


def analyze_frequency_spectrum(data: bytes, *, bins: int = 96) -> dict:
    """Bounded log-frequency spectrum for the interactive Motion Studio editor.

    Sample at most 48 evenly spaced WAV windows, independently of project FPS.
    Values show the whole recording's relative frequency distribution, not a
    time-varying FFT or source-separated instruments. Never touch project state.
    """
    import numpy as np

    if type(bins) is not int or not 32 <= bins <= 128:
        raise AudioMotionError("Spectrum must use 32–128 display bins.")
    pcm, rate = _decode_pcm(data)
    nyquist = rate / 2
    fft_size = 8192 if rate >= 16000 else 4096
    window = np.hanning(fft_size).astype(np.float32)
    freqs = np.fft.rfftfreq(fft_size, 1 / rate)
    upper = min(20000., float(nyquist))
    centers = np.geomspace(20., upper, bins)
    # Using a max over each log-width bucket retains narrow instrument peaks.
    edges = np.geomspace(20., upper, bins + 1)
    bucket = [
        np.where((freqs >= edges[i]) &
                 (freqs < edges[i + 1] if i + 1 < bins else freqs <= edges[i + 1]))[0]
        for i in range(bins)
    ]
    accumulated = np.zeros(bins, dtype=np.float64)
    samples = min(48, max(1, math.ceil(len(pcm) / fft_size)))
    for center in np.linspace(0, len(pcm) - 1, samples, dtype=np.int64):
        start = int(center) - fft_size // 2
        left, right = max(0, start), min(len(pcm), start + fft_size)
        segment = np.zeros(fft_size, dtype=np.float32)
        if right > left:
            segment[left - start:left - start + right - left] = pcm[left:right]
        spectrum = np.abs(np.fft.rfft(segment * window))
        for i, indices in enumerate(bucket):
            if len(indices):
                accumulated[i] += float(spectrum[indices].max())
    highest = max(float(accumulated.max()), 1e-12)
    return {
        "schema_version": 1,
        "sample_rate": rate,
        "nyquist_hz": nyquist,
        "frequency_min_hz": 20.,
        "frequency_max_hz": upper,
        "spectrum": [
            {"hz": round(float(hz), 3),
             "level": round(min(1., float(accumulated[i]) / highest), 6)}
            for i, hz in enumerate(centers)
        ],
        "summary": "Time-averaged spectrum; approximate bands, not isolated audio stems.",
    }

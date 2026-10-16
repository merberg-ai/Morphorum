"""DA1.2 audio event API and FPS proposal regression tests."""
import math
import struct
import wave
from io import BytesIO

import pytest

from morphorum.audio_motion_upload import audio_fps_recommendations, analyze_managed_wav
from morphorum.audio_motion import AudioMotionError


def make_wav():
    rate = 12000
    samples = [0.0] * rate
    for t, freq in ((0.25, 75), (0.7, 900)):
        start = round(t * rate)
        for j in range(700):
            samples[start + j] += 0.65 * math.exp(-j / 220) * math.sin(2 * math.pi * freq * j / rate)
    out = BytesIO()
    with wave.open(out, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"".join(struct.pack("<h", round(max(-1, min(1, v)) * 32767)) for v in samples))
    return out.getvalue()


def test_proposals_respect_3000_frame_cap_and_never_mutate():
    r = audio_fps_recommendations(16.261, current_fps=12)
    assert r["recommended_fps"] == 30
    assert [(o["fps"], o["max_frames"]) for o in r["options"]] == [
        (12, 196), (24, 391), (30, 488), (60, 976)]
    assert r["requires_explicit_project_update"]
    assert not audio_fps_recommendations(180, current_fps=12)["options"][-1]["supported"]
    assert audio_fps_recommendations(180, current_fps=12)["recommended_fps"] == 12


def test_wav_analysis_retains_legacy_envelope_and_adds_events(tmp_path, monkeypatch):
    from morphorum import audio_motion_upload
    monkeypatch.setattr(audio_motion_upload, "animation_project_directory", lambda project_id: tmp_path)
    result = analyze_managed_wav("test", make_wav(), fps=12, frames=12)
    assert len(result["values"]) == 12
    assert set(result["bands"]) == {"kick", "bass", "snare", "highs"}
    assert result["events"]["analysis_version"] == 2
    assert any(e["kind"] == "kick" and abs(e["time_seconds"] - .25) < .05
               for e in result["events"]["events"])
    assert any(e["kind"] == "snare" and abs(e["time_seconds"] - .7) < .05
               for e in result["events"]["events"])
    assert result["fps_recommendations"]["recommended_fps"] == 30
    assert (tmp_path / "motion_lab_audio" / result["filename"]).exists()


@pytest.mark.parametrize("duration,fps", [(0, 12), (float("nan"), 12), (10, 0), (10, float("inf"))])
def test_proposals_reject_invalid_parameters(duration, fps):
    with pytest.raises(AudioMotionError):
        audio_fps_recommendations(duration, current_fps=fps)

def test_stereo_waveform_preserves_channel_identity_and_bounds(tmp_path, monkeypatch):
    from morphorum import audio_motion_upload
    monkeypatch.setattr(audio_motion_upload, "animation_project_directory", lambda _: tmp_path)
    rate = 12000
    out = BytesIO()
    with wave.open(out, "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        pcm = []
        for i in range(rate):
            left = 16000 if i == 2000 else 0
            right = -15000 if i == 7000 else 0
            pcm.append(struct.pack("<hh", left, right))
        audio.writeframes(b"".join(pcm))
    result = analyze_managed_wav("stereo", out.getvalue(), fps=12, frames=12)
    waveform = result["waveform"]
    assert waveform["bins"] <= 1200
    assert len(waveform["channels"]) == 2
    assert max(peak for _, peak in waveform["channels"][0]) > .4
    assert min(low for low, _ in waveform["channels"][1]) < -.4
    assert max(peak for _, peak in waveform["channels"][1]) == 0
    assert min(low for low, _ in waveform["channels"][0]) == 0

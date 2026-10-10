"""ML3.1 WAV import, project ownership, and native six-axis compilation."""
import io
import math
import wave

import pytest

from morphorum.audio_motion import AudioMotionError
from morphorum.audio_motion_upload import analyze_managed_wav
from morphorum.motion_lab import MotionLabError, compile_motion_lab
from morphorum.animation_projects import create_animation_project


def pcm_wav(samples, *, rate=12000):
    buff = io.BytesIO()
    with wave.open(buff, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(int(sample * 32767).to_bytes(2, "little", signed=True)
                              for sample in samples))
    return buff.getvalue()


def test_wav_analysis_project_bound_and_frame_aligned(tmp_path, monkeypatch):
    from morphorum import animation_projects
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)
    project_id = "ml3-audio-test"
    (tmp_path / project_id).mkdir()
    audio = pcm_wav([0] * 1000 + [0.8] * 1000 + [0] * 2000)
    result = analyze_managed_wav(project_id, audio, fps=12, frames=8)
    assert result["frames"] == 8
    assert result["values"][0] == 0
    assert result["values"][1] > 0.7
    assert math.isclose(result["values"][3], 0)
    assert (tmp_path / project_id / "motion_lab_audio" / result["filename"]).read_bytes() == audio
    assert analyze_managed_wav(project_id, audio, fps=12, frames=8)["source_sha256"] == result["source_sha256"]


@pytest.mark.parametrize("content", [b"", b"not a wav", b"x" * (20 * 1024 * 1024 + 1)])
def test_reject_bad_wav(content, tmp_path, monkeypatch):
    from morphorum import animation_projects
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)
    with pytest.raises(AudioMotionError):
        analyze_managed_wav("safe-test", content, fps=12, frames=12)


def test_audio_layer_native_tracks_and_validation():
    project = create_animation_project({"name": "ML3 native test"})
    project["animation"]["mode"] = "3d"
    project["animation"]["max_frames"] = 12
    project["animation"]["fps"] = 12
    envelope = [0, .9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    layer = dict(id="audio-1", type="audio", enabled=True, blend="add",
                 start_frame=0, end_frame=12, axis="translation_z", fps=12,
                 sha256="a" * 64, envelope=envelope,
                 threshold=.5, distance=.06, attack_frames=1,
                 release_frames=3, cooldown_frames=0, offset_frames=0)
    compiled, diag = compile_motion_lab(project, layers=[layer], include_series=True)
    assert diag["series"]["translation_z"][1] == pytest.approx(.06)
    assert diag["series"]["translation_z"][2:5] == pytest.approx([-.02] * 3)
    assert sum(diag["series"]["translation_z"]) == pytest.approx(0, abs=1e-7)
    assert compiled["motion_lab"]["layers"][0]["type"] == "audio"
    assert diag["series"]["rotation_z"] == [0] * 12
    with pytest.raises(MotionLabError, match="FPS"):
        compile_motion_lab(project, layers=[{**layer, "fps": 24}])
    with pytest.raises(MotionLabError, match="envelope"):
        compile_motion_lab(project, layers=[{**layer, "envelope": [0]}])

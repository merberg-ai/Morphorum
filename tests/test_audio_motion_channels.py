"""MS3: independent sound channels compile predictably and never double motion."""
from copy import deepcopy
import math

import pytest
from morphorum.audio_motion import AudioMotionError
from morphorum.audio_motion_channels import (
    compile_channel_tracks, validate_channel_document,
)
from morphorum.motion_lab import compile_motion_lab
from morphorum.animation_projects import normalize_animation_project

SHA = "c" * 64
FPS = 24
N = 120


def envelope():
    values = [0.] * N
    for i in [12, 30, 50, 80]:
        for j in range(i, i + 5):
            values[j] = max(0., 1. - (j-i) / 5)
    return values


def channel(name="bass", mode="hits", axis="translation_z"):
    return {
        "id": name, "name": name.title(), "mode": mode, "axis": axis,
        "enabled": True, "low_hz": 35, "high_hz": 150, "strength": .5,
        "threshold": .15, "sensitivity": .15, "attack_frames": 2,
        "release_frames": 5, "cooldown_frames": 3,
        "offset_frames": 0, "start_frame": 0, "end_frame": N,
        "envelope": envelope(),
    }


def doc(channels=None):
    return {"schema_version": 1, "source_sha256": SHA, "fps": FPS,
            "max_frames": N, "channels": [channel()] if channels is None else channels}


@pytest.mark.parametrize("mode", ["hits", "intensity", "ripple"])
def test_all_response_modes_are_frame_aligned_and_non_drifting(mode):
    velocities = compile_channel_tracks(doc([channel(mode=mode)]), fps=FPS, frames=N)
    assert len(velocities["translation_z"]) == N
    assert all(math.isfinite(v) for track in velocities.values() for v in track)
    assert any(abs(v) > 1e-10 for v in velocities["translation_z"])
    assert abs(sum(velocities["translation_z"])) < 1e-8
    assert not any(velocities["rotation_x"])


def test_independent_channels_combine_and_disabled_channel_is_ignored():
    bass = channel()
    snare = channel("snare", "ripple", "rotation_z")
    channels = doc([bass, snare])
    mix = compile_channel_tracks(channels, fps=FPS, frames=N)
    assert any(mix["translation_z"])
    assert any(mix["rotation_z"])
    snare["enabled"] = False
    reduced = compile_channel_tracks(channels, fps=FPS, frames=N)
    assert reduced["translation_z"] == mix["translation_z"]
    assert not any(reduced["rotation_z"])


def test_two_same_axis_channels_sum_exactly():
    one = channel()
    two = channel("second")
    values = compile_channel_tracks(doc([one]), fps=FPS, frames=N)["translation_z"]
    mixed = compile_channel_tracks(doc([one, two]), fps=FPS, frames=N)["translation_z"]
    assert mixed == pytest.approx([v * 2 for v in values])


@pytest.mark.parametrize("field,value", [
    ("axis", "yaw"), ("low_hz", 100), ("high_hz", 40),
    ("threshold", float("nan")), ("envelope", [0.] * 4),
    ("attack_frames", 0), ("strength", 2), ("enabled", "true"),
    ("mode", "noise"), ("offset_frames", 5000),
])
def test_invalid_channel_input_rejected(field, value):
    obj = doc()
    obj["channels"][0][field] = value
    with pytest.raises(AudioMotionError):
        validate_channel_document(obj, fps=FPS, frames=N)


def test_duplicate_ids_and_audio_mismatch_rejected():
    with pytest.raises(AudioMotionError, match="unique"):
        validate_channel_document(doc([channel(), channel()]), fps=FPS, frames=N)
    with pytest.raises(AudioMotionError, match="FPS"):
        validate_channel_document(doc(), fps=30, frames=N)
    with pytest.raises(AudioMotionError, match="frame count"):
        validate_channel_document(doc(), fps=FPS, frames=N+1)


def test_native_layer_preview_is_deterministic_and_does_not_double_on_reapply():
    project = normalize_animation_project(
        {"name": "MS3 sound channel test",
         "animation": {"mode": "3d", "fps": FPS, "max_frames": N}},
        project_id="ms3-sound-channels",
    )
    untouched = deepcopy(project)
    layer = {"id": "audio-channels-" + SHA[:12], "type": "audio_channels",
             "name": "Sound channels", "sha256": SHA,
             "blend": "add", "enabled": True,
             "start_frame": 0, "end_frame": N,
             "channel_document": doc([channel(), channel("snare", "ripple", "rotation_z")])}
    first, diag = compile_motion_lab(project, layers=[layer], include_series=True)
    assert project == untouched
    assert diag["layer_count"] == 1
    assert any(diag["series"]["translation_z"])
    second, again = compile_motion_lab(first, layers=[layer], include_series=True)
    assert diag["series"] == again["series"]
    assert first["tracks"]["camera_3d"] == second["tracks"]["camera_3d"]


def test_manual_cues_can_coexist_with_channels():
    project = normalize_animation_project(
        {"name": "MS3 coexist",
         "animation": {"mode": "3d", "fps": FPS, "max_frames": N}},
        project_id="ms3-coexist",
    )
    cue = {
        "id": "manual", "type": "audio_cues", "sha256": SHA,
        "blend": "add", "start_frame": 0, "end_frame": N,
        "cue_document": {
            "source_sha256": SHA, "duration_seconds": 5,
            "cues": [{"id": "riff", "preset": "push_zoom_in",
                      "time_seconds": 1, "duration_seconds": .5,
                      "intensity": .5}],
        }
    }
    channels = {"id": "channels", "type": "audio_channels", "sha256": SHA,
                "blend": "add", "start_frame": 0, "end_frame": N,
                "channel_document": doc()}
    _, diag = compile_motion_lab(project, layers=[cue, channels], include_series=True)
    assert diag["layer_count"] == 2
    assert any(diag["series"]["translation_z"])

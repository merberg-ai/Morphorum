"""DA4.5 integration: source-bound cue motion is native, additive and deterministic."""
from copy import deepcopy
import pytest
from morphorum.animation_projects import normalize_animation_project
from morphorum.motion_lab import compile_motion_lab, MotionLabError

SHA = "a"*64

def project():
    return normalize_animation_project({
        "name":"Audio Director native test",
        "animation":{"mode":"3d","fps":24,"max_frames":120},
    }, project_id="director-native-test")

def cue_layer():
    return {
        "id":"director-"+SHA[:24],
        "type":"audio_cues","name":"Audio Motion Director",
        "sha256":SHA,"enabled":True,"blend":"add",
        "start_frame":0,"end_frame":120,
        "cue_document":{"source_sha256":SHA,"duration_seconds":5.,
          "cues":[
            {"id":"riff","time_seconds":.5,"preset":"push_zoom_in",
             "duration_seconds":.5,"intensity":.5},
            {"id":"drum","time_seconds":1.5,"preset":"roll_right_left",
             "duration_seconds":.5,"intensity":.7},
          ]},
    }

def test_cues_compile_to_true_six_axis_series_and_reapply_without_double_counting():
    p=project()
    untouched=deepcopy(p)
    first, diag=compile_motion_lab(p,layers=[cue_layer()],include_series=True)
    assert p==untouched
    assert diag["layer_count"]==1
    z=diag["series"]["translation_z"]
    roll=diag["series"]["rotation_z"]
    assert sum(z)>0
    assert any(abs(v)>0 for v in roll)
    assert abs(sum(roll))<1e-7
    assert len(z)==120
    second, diag2=compile_motion_lab(first,layers=[cue_layer()],include_series=True)
    assert diag2["series"]==diag["series"]
    assert first["tracks"]["camera_3d"]==second["tracks"]["camera_3d"]

def test_multiple_cues_plus_existing_preset_keep_legacy_layers():
    p=project()
    d=cue_layer()
    wave={"id":"wave-1","type":"preset","preset":"wave",
        "blend":"add","start_frame":0,"end_frame":120,
        "strength":.3,"cycle_seconds":3,"fade_seconds":0}
    out,diag=compile_motion_lab(p,layers=[wave,d],include_series=True)
    assert len(out["motion_lab"]["layers"])==2
    assert any(abs(v)>0 for v in diag["series"]["translation_x"])
    assert any(abs(v)>0 for v in diag["series"]["translation_z"])

def test_invalid_source_hash_and_replace_blend_rejected():
    p=project()
    bad=cue_layer()
    bad["sha256"]="b"*64
    with pytest.raises(MotionLabError,match="hash"):
        compile_motion_lab(p,layers=[bad])
    bad=cue_layer()
    bad["blend"]="replace"
    with pytest.raises(MotionLabError,match="additive"):
        compile_motion_lab(p,layers=[bad])

def test_normalized_cue_layer_survives_project_serialization():
    p=project()
    compiled,_=compile_motion_lab(p,layers=[cue_layer()])
    roundtrip=normalize_animation_project(compiled,existing=compiled,
      project_id=compiled["id"],prefer_tracks=True)
    assert roundtrip["motion_lab"]["layers"][0]["type"]=="audio_cues"
    assert roundtrip["motion_lab"]["layers"][0]["cue_document"]["cues"][0]["id"]=="riff"

def test_existing_camera_edit_protection():
    p=project()
    first,_=compile_motion_lab(p,layers=[cue_layer()])
    first["tracks"]["camera_3d"]["translation_z"]["schedule"]="0:(0.02)"
    with pytest.raises(MotionLabError,match="Camera schedules changed"):
        compile_motion_lab(first,layers=[cue_layer()])

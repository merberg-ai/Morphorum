"""DA4.3 deterministic native cue preset properties."""
import math

import pytest
from morphorum.audio_motion_presets import cue_velocity_tracks
from morphorum.audio_motion_cues import validate_cues

HASH="a"*64

def doc(preset, start=.25, length=1., intensity=.5):
    return {"source_sha256":HASH,"duration_seconds":10.,"cues":[{
      "id":"one","preset":preset,"time_seconds":start,
      "duration_seconds":length,"intensity":intensity,"enabled":True
    }]}

@pytest.mark.parametrize("name", [
    "push_zoom_in","push_return","roll_right_left","roll_left_right",
    "dolly_out","shake","ripple","reveal_drift","fly_through"])
def test_preset_tracks_are_finite_and_frame_aligned(name):
    tracks=cue_velocity_tracks(doc(name),24,240)
    assert set(tracks)=={"translation_x","translation_y","translation_z",
                         "rotation_x","rotation_y","rotation_z"}
    assert all(len(v)==240 for v in tracks.values())
    assert all(math.isfinite(v) for values in tracks.values() for v in values)

def test_push_zoom_has_positive_net_travel_and_no_return():
    values=cue_velocity_tracks(doc("push_zoom_in"),24,240)["translation_z"]
    assert sum(values)>0
    assert all(x>=-1e-12 for x in values)

def test_dolly_out_moves_back_without_return():
    assert sum(cue_velocity_tracks(doc("dolly_out"),24,240)["translation_z"])<0

@pytest.mark.parametrize("name,axis",[
    ("push_return","translation_z"),("roll_right_left","rotation_z"),
    ("roll_left_right","rotation_z"),("shake","translation_x"),
    ("ripple","translation_z"),("reveal_drift","translation_x")])
def test_returning_preset_has_near_zero_net_displacement(name,axis):
    values=cue_velocity_tracks(doc(name),30,300)[axis]
    assert abs(sum(values))<1e-8

def test_simultaneous_cues_add_and_are_deterministic():
    both=doc("push_zoom_in")
    both["cues"].append({**both["cues"][0],"id":"second"})
    single=cue_velocity_tracks(doc("push_zoom_in"),24,240)["translation_z"]
    combined=cue_velocity_tracks(both,24,240)["translation_z"]
    assert combined==pytest.approx([x*2 for x in single])
    assert combined==cue_velocity_tracks(both,24,240)["translation_z"]

def test_no_cues_no_motion():
    empty=doc("push_zoom_in")
    empty["cues"]=[]
    assert all(not any(v) for v in cue_velocity_tracks(empty,24,240).values())

def test_disabled_cue_no_motion():
    one=doc("push_zoom_in")
    one["cues"][0]["enabled"]=False
    assert all(not any(v) for v in cue_velocity_tracks(one,24,240).values())

@pytest.mark.parametrize("fps", [12,24,30,60])
def test_fps_independent_source_timing(fps):
    track=cue_velocity_tracks(doc("push_zoom_in",start=1.),fps,2000)["translation_z"]
    assert not any(abs(v)>0 for v in track[:fps])
    assert any(abs(v)>0 for v in track[fps:fps+5])

"""ML4.1: real render resolver and frame-manifest camera contract.

No GPU required: the renderer's actual frame-state serializer is exercised
against the same resolved project passed to the GPU render loop.
"""
from copy import deepcopy
import numpy as np
import pytest

from morphorum.animation_projects import normalize_animation_project
from morphorum.animation_resolution import resolve_project_frame
from morphorum.animation_render import _frame_state_for_frame
from morphorum.motion_lab import AXES, compile_motion_lab


def project():
    return normalize_animation_project({
        "name": "ML4 mixed render contract",
        "animation": {"mode": "3d", "max_frames": 48, "fps": 12},
        "cadence": {"diffusion": "0:(3)"},
        "prompts": {"0": "cold forest", "24": "abandoned factory"},
    }, project_id="ml4-render-contract")


def layers():
    return [
        {"id":"composer", "preset":"wave","blend":"add",
         "start_frame":0,"end_frame":48,"strength":.45,
         "cycle_seconds":2,"fade_seconds":.1},
        {"id":"recorded","type":"recording","name":"Keyboard take",
         "enabled":True,"blend":"add","start_frame":4,"end_frame":10,
         "fps":12,"source":"keyboard","capture_version":1,
         "axes":["translation_x","rotation_y"],
         "samples":[[.01,0,0,0,.02,0]]*6},
        {"id":"kick","type":"audio","enabled":True,"blend":"add",
         "start_frame":0,"end_frame":48,"axis":"translation_z",
         "fps":12,"sha256":"a"*64,
         "envelope":[0,0,.9,.1]+[0]*44,
         "band":"kick","detection":"transient","sensitivity":.2,
         "threshold":.5,"distance":.06,"attack_frames":1,
         "release_frames":2,"cooldown_frames":1,"offset_frames":0},
    ]


@pytest.mark.parametrize("frame", [0,2,3,4,6,9,10,23,24,47])
def test_camera_diagnostics_match_actual_gpu_frame_metadata(frame):
    original=project()
    snapshot=deepcopy(original)
    compiled, info=compile_motion_lab(original, layers=layers(), include_series=True)
    assert original == snapshot
    resolved=resolve_project_frame(compiled, frame)
    actual=_frame_state_for_frame(
        resolved, seed=123, diffusion_mode="img2img",
        motion_applied=frame>0, cumulative_matrix=np.eye(3),
        cadence_state={"diffusion":3,"anchor":frame%3==0},
    )
    assert actual["animation_mode"] == "3d"
    for axis in AXES:
        assert actual["camera_3d"][axis] == pytest.approx(
            info["series"][axis][frame], abs=1e-7)
    assert actual["cadence"]["anchor"] == (frame%3==0)


def test_compiled_native_tracks_are_idempotent_across_rerender():
    first,_=compile_motion_lab(project(),layers=layers())
    second,_=compile_motion_lab(first,layers=layers())
    for axis in AXES:
        assert second["tracks"]["camera_3d"][axis] == first["tracks"]["camera_3d"][axis]
    assert second["generation"] == first["generation"]
    assert second["prompts"] == first["prompts"]

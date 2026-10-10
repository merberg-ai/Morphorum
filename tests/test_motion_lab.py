from __future__ import annotations

from copy import deepcopy

import pytest

from morphorum.animation_projects import normalize_animation_project
from morphorum.animation_resolution import resolve_project_frame
from morphorum.motion_lab import (
    AXES, PRESETS, MotionLabError, compile_motion_lab, normalize_layers,
    normalize_motion_lab,
)


def project(frames=32):
    return normalize_animation_project({
        "name": "ML0 presets",
        "animation": {"mode": "3d", "max_frames": frames, "fps": 12},
    }, project_id="motion-lab-test")


def layer(preset="wave", **overrides):
    return {
        "id": "motion-1", "preset": preset, "blend": "add",
        "start_frame": 0, "end_frame": 32, "strength": 0.7,
        "cycle_seconds": 2, "fade_seconds": 0.2,
        **overrides,
    }


@pytest.mark.parametrize("preset", PRESETS)
def test_all_native_six_axis_presets_compile_and_resolve(preset):
    original = project()
    before = deepcopy(original)
    compiled, diagnostics = compile_motion_lab(original, layers=[layer(preset)])
    assert original == before, "Preview/compile must never edit the passed-in project"
    assert diagnostics["frames"] == 32
    assert compiled["motion_lab"]["schema_version"] == 1
    assert set(compiled["motion_lab"]["last_applied_tracks"]) == set(AXES)
    assert compiled["camera_3d"]["fov"] == original["camera_3d"]["fov"]
    assert compiled["generation"] == original["generation"]
    assert compiled["hybrid"] == original["hybrid"]
    assert compiled["model"] == original["model"]
    for idx in (0, 7, 16, 31):
        resolved = resolve_project_frame(compiled, idx)["camera_3d"]
        assert all(abs(float(resolved[a])) < 5 for a in AXES)


def test_wave_and_spiral_produce_nonzero_shape_not_just_constant_motion():
    p = project()
    wave, _ = compile_motion_lab(p, layers=[layer("wave", fade_seconds=0)])
    spiral, _ = compile_motion_lab(p, layers=[layer("spiral", fade_seconds=0)])
    a = [resolve_project_frame(wave, frame)["camera_3d"]["translation_x"] for frame in range(1, 24)]
    b = [resolve_project_frame(spiral, frame)["camera_3d"]["translation_y"] for frame in range(1, 24)]
    assert len({round(v, 7) for v in a}) > 5
    assert len({round(v, 7) for v in b}) > 5


def test_multiple_additive_layers_never_double_apply_and_other_camera_edits_conflict():
    p = project()
    draft = [
        layer("wave", id="w1", strength=0.4),
        layer("push-in", id="p1", strength=0.2),
    ]
    first, info = compile_motion_lab(p, layers=draft)
    assert info["layer_count"] == 2
    again, _ = compile_motion_lab(first, layers=draft)
    for axis in AXES:
        assert first["camera_3d"][axis] == again["camera_3d"][axis]
    assert resolve_project_frame(first, 10)["camera_3d"]["translation_z"] > 0
    first["camera_3d"]["translation_z"] = "0:(0)"
    # Native track, not legacy field, is the source of truth.
    first["tracks"]["camera_3d"]["translation_z"]["schedule"] = "0:(0)"
    with pytest.raises(MotionLabError, match="changed since"):
        compile_motion_lab(first, layers=draft)


def test_replace_only_changes_preset_axes_and_disabled_layer_does_not_apply():
    p = project()
    p["camera_3d"]["rotation_x"] = "0:(0.05)"
    p["tracks"]["camera_3d"]["rotation_x"]["schedule"] = "0:(0.05)"
    d = layer("push-in", blend="replace", fade_seconds=0)
    result, _ = compile_motion_lab(p, layers=[d])
    assert resolve_project_frame(result, 12)["camera_3d"]["rotation_x"] == pytest.approx(.05)
    assert resolve_project_frame(result, 12)["camera_3d"]["translation_z"] > 0
    disabled, _ = compile_motion_lab(p, layers=[{**d, "enabled": False}])
    assert resolve_project_frame(disabled, 12)["camera_3d"]["translation_z"] == 0


def test_motion_safety_bounds_and_frame_limits():
    p = project()
    with pytest.raises(MotionLabError, match="unsupported preset"):
        normalize_layers([layer("teleport")], p)
    with pytest.raises(MotionLabError, match="between 0 and 1"):
        normalize_layers([layer("wave", strength=3)], p)
    with pytest.raises(MotionLabError, match="unique"):
        normalize_layers([layer("wave"), layer("wave")], p)
    with pytest.raises(MotionLabError, match="require 3D"):
        q = project()
        q["animation"]["mode"] = "2d"
        compile_motion_lab(q, layers=[layer()])
    with pytest.raises(MotionLabError, match="at most 24"):
        normalize_layers([layer("wave", id=str(i)) for i in range(25)], p)
    capped = project()
    capped["motion_lab"]["limits"]["translation_x"] = 0.0001
    generated, diag = compile_motion_lab(capped, layers=[layer("wave", fade_seconds=0)])
    assert diag["limited"].get("translation_x", 0) > 0
    assert abs(resolve_project_frame(generated, 5)["camera_3d"]["translation_x"]) <= 0.000100001


def test_inert_motion_lab_settings_survive_save_normalization():
    p = project()
    p["motion_lab"] = normalize_motion_lab({"layers": [layer()]}, p)
    normalized = normalize_animation_project(p, existing=p, project_id=p["id"], prefer_tracks=True)
    assert normalized["motion_lab"]["layers"][0]["preset"] == "wave"
    assert normalized["camera_3d"]["translation_x"] == "0:(0)"
    applied, _ = compile_motion_lab(normalized)
    saved_like = normalize_animation_project(
        applied, existing=normalized, project_id=p["id"], prefer_tracks=True,
    )
    assert saved_like["motion_lab"]["layers"][0]["preset"] == "wave"
    assert resolve_project_frame(saved_like, 8)["camera_3d"]["translation_x"] != 0



def test_spiral_completes_helix_in_short_two_second_preview():
    """Old eight-second/small-amplitude defaults looked stationary at 24 frames."""
    p = project(frames=24)
    spiral, report = compile_motion_lab(p, layers=[
        layer("spiral", end_frame=24, strength=0.65,
              cycle_seconds=2.0, fade_seconds=0),
    ])
    values = [resolve_project_frame(spiral, frame)["camera_3d"]
              for frame in range(1, 24)]
    x = [float(v["translation_x"]) for v in values]
    y = [float(v["translation_y"]) for v in values]
    z = [float(v["translation_z"]) for v in values]
    roll = [float(v["rotation_z"]) for v in values]
    # Circular X/Y velocity moves through both positive and negative signs.
    assert min(x) < -0.012 and max(x) > 0.012
    assert min(y) < -0.012 and max(y) > 0.012
    # Continuous helical travel and rotation are perceptible throughout.
    assert min(z) > 0.012
    assert max(roll) > 0.3
    assert not report["limited"]


def test_manual_camera_edits_are_safe_in_draft_and_require_apply_confirmation():
    p = project()
    applied, _ = compile_motion_lab(p, layers=[layer("wave")])
    applied["tracks"]["camera_3d"]["translation_z"]["schedule"] = "0:(0.02)"
    applied["camera_3d"]["translation_z"] = "0:(0.02)"
    with pytest.raises(MotionLabError, match="Confirm"):
        compile_motion_lab(applied, layers=[layer("spiral")])
    original = deepcopy(applied)
    preview, diag = compile_motion_lab(
        applied, layers=[layer("spiral")], conflict_policy="use-current",
    )
    assert applied == original
    assert diag["camera_changed"] is True
    assert diag["rebased"] is True
    assert preview["motion_lab"]["base_tracks"]["translation_z"]["schedule"] == "0:(0.02)"
    repeated, repeated_diag = compile_motion_lab(preview, layers=[layer("spiral")])
    assert repeated_diag["camera_changed"] is False
    assert repeated["camera_3d"] == preview["camera_3d"]

"""ML1b sparse keyframe authoring compiles into native camera schedules."""
from __future__ import annotations

from copy import deepcopy

import pytest

from morphorum.animation_projects import normalize_animation_project
from morphorum.animation_resolution import resolve_project_frame
from morphorum.motion_lab import MotionLabError, compile_motion_lab, normalize_layers


def project(frames=24):
    return normalize_animation_project({
        "name": "ML1b curves",
        "animation": {"mode": "3d", "max_frames": frames, "fps": 12},
    }, project_id="keyframe-test")


def curve(axis="translation_x", **overrides):
    return {
        "id": "curve-tx", "type": "keyframes", "axis": axis,
        "start_frame": 0, "end_frame": 24, "blend": "add",
        "enabled": True, "interpolation": "linear",
        "keys": [{"frame": 0, "value": 0}, {"frame": 12, "value": 0.08},
                 {"frame": 20, "value": -0.04}],
        **overrides,
    }


def resolved(p, frame, axis="translation_x"):
    return float(resolve_project_frame(p, frame)["camera_3d"][axis])


def test_linear_curve_interpolation_is_native_and_zero_on_first_frame():
    original = project()
    snapshot = deepcopy(original)
    p, d = compile_motion_lab(original, layers=[curve()], include_series=True)
    assert original == snapshot
    assert resolved(p, 0) == 0
    assert resolved(p, 6) == pytest.approx(.04)
    assert resolved(p, 12) == pytest.approx(.08)
    assert resolved(p, 16) == pytest.approx(.02)
    assert resolved(p, 20) == pytest.approx(-.04)
    assert resolved(p, 23) == pytest.approx(-.04)
    assert d["series"]["translation_x"][16] == pytest.approx(.02)
    assert p["motion_lab"]["layers"][0]["type"] == "keyframes"
    assert len(p["tracks"]["camera_3d"]["translation_x"]["schedule"].split(",")) == 24


def test_hold_curve_and_offset_start_and_end():
    p, _ = compile_motion_lab(project(), layers=[curve(
        interpolation="hold", start_frame=4, end_frame=18,
        keys=[{"frame": 8, "value": .08}, {"frame": 14, "value": -.04}],
    )])
    assert resolved(p, 4) == 0
    assert resolved(p, 7) == 0
    assert resolved(p, 8) == pytest.approx(.08)
    assert resolved(p, 13) == pytest.approx(.08)
    assert resolved(p, 14) == pytest.approx(-.04)
    assert resolved(p, 17) == pytest.approx(-.04)
    assert resolved(p, 18) == 0


def test_curve_layer_order_add_replace_and_existing_preset_compatibility():
    preset = {
        "id": "p", "type": "preset", "preset": "push-in", "strength": 1,
        "start_frame": 0, "end_frame": 24, "fade_seconds": 0,
    }
    override = curve("translation_z", id="cz", blend="replace",
                     keys=[{"frame": 0, "value": 0}, {"frame": 12, "value": -.08}])
    p, _ = compile_motion_lab(project(), layers=[preset, override])
    assert resolved(p, 12, "translation_z") == pytest.approx(-.08)
    q, _ = compile_motion_lab(project(), layers=[override, preset])
    assert resolved(q, 12, "translation_z") == pytest.approx(-.055)
    # Inverting the layer order changes composition; no rewrite of other axes.
    assert resolved(p, 12, "rotation_z") == 0


def test_curve_preview_does_not_mutate_draft_or_double_apply():
    start = project()
    p, diagnostics = compile_motion_lab(start, layers=[curve()], include_series=True)
    assert diagnostics["frames"] == 24
    replay, _ = compile_motion_lab(p, layers=[curve()])
    assert replay["camera_3d"] == p["camera_3d"]
    persisted = normalize_animation_project(
        p, existing=p, project_id=p["id"], prefer_tracks=True,
    )
    assert persisted["motion_lab"]["layers"][0]["keys"][1]["value"] == pytest.approx(.08)
    assert resolved(persisted, 12) == pytest.approx(.08)


@pytest.mark.parametrize("bad,match", [
    (curve(axis="depth"), "six camera axes"),
    (curve(keys=[]), "1–128 keyframes"),
    (curve(keys=[{"frame": 0, "value": .02}]), "Frame 0"),
    (curve(keys=[{"frame": 1, "value": .05}, {"frame": 1, "value": .06}]), "Duplicate"),
    (curve(keys=[{"frame": 24, "value": .05}]), "Keyframe position"),
    (curve(keys=[{"frame": 4, "value": float("nan")}]), "Keyframe value"),
    (curve(keys=[{"frame": 4, "value": float("inf")}]), "Keyframe value"),
    (curve(interpolation="bezier-random"), "smoothstep, smootherstep or cubic"),
    (curve(keys=[{"frame": f, "value": 0} for f in range(129)]), "1–128 keyframes"),
])
def test_invalid_keyframe_layers_fail_before_gpu_work(bad, match):
    with pytest.raises(MotionLabError, match=match):
        normalize_layers([bad], project(frames=180))


def test_manual_curve_preserves_editor_conflict_confirmation():
    p, _ = compile_motion_lab(project(), layers=[curve()])
    p["camera_3d"]["translation_x"] = "0:(0.01)"
    p["tracks"]["camera_3d"]["translation_x"]["schedule"] = "0:(0.01)"
    with pytest.raises(MotionLabError, match="Confirm"):
        compile_motion_lab(p, layers=[curve()])
    draft, report = compile_motion_lab(
        p, layers=[curve()], conflict_policy="use-current",
    )
    assert report["rebased"] is True
    assert draft["motion_lab"]["base_tracks"]["translation_x"]["schedule"] == "0:(0.01)"



@pytest.mark.parametrize("mode,quarter", [
    ("linear", 0.02),
    ("smoothstep", 0.0125),
    ("smootherstep", 0.00828125),
])
def test_ml1b_easing_smooths_keyframe_segments(mode, quarter):
    layer = curve(interpolation=mode)
    p, meta = compile_motion_lab(project(), layers=[layer], include_series=True)
    assert resolved(p, 0) == 0
    assert resolved(p, 3) == pytest.approx(quarter, abs=1e-8)
    assert resolved(p, 12) == pytest.approx(.08)
    assert resolved(p, 20) == pytest.approx(-.04)
    assert meta["series"]["translation_x"][3] == pytest.approx(quarter, abs=1e-8)
    # Recompiled native tracks never use a separate per-frame GPU expression.
    assert p["tracks"]["camera_3d"]["translation_x"]["interpolation"] == "linear"


def test_ml1b_monotone_cubic_is_curved_continuous_and_does_not_overshoot():
    keys = [
        {"frame": 0, "value": 0},
        {"frame": 10, "value": 0.06},
        {"frame": 19, "value": 0.09},
        {"frame": 26, "value": -0.03},
        {"frame": 38, "value": -0.015},
        {"frame": 47, "value": 0.02},
    ]
    p = project(frames=48)
    curved = curve(interpolation="cubic", end_frame=48, keys=keys)
    compiled, info = compile_motion_lab(p, layers=[curved], include_series=True)
    values = info["series"]["translation_x"]
    assert len(values) == 48
    for first, last in zip(keys, keys[1:]):
        lo, hi = sorted((first["value"], last["value"]))
        for f in range(first["frame"], last["frame"] + 1):
            assert lo - 1e-8 <= values[f] <= hi + 1e-8
    # The monotone cubic interpolator is not a straight line at interior points.
    assert values[4] != pytest.approx(keys[1]["value"] * 4 / 10, abs=1e-6)
    # Exact keyframe values and zero frame remain intact after save/reopen.
    for key in keys:
        assert resolved(compiled, key["frame"]) == pytest.approx(key["value"])
    saved = normalize_animation_project(
        compiled, existing=compiled, project_id=compiled["id"], prefer_tracks=True,
    )
    assert saved["motion_lab"]["layers"][0]["interpolation"] == "cubic"
    assert resolve_project_frame(saved, 16)["camera_3d"]["translation_x"] == pytest.approx(values[16])


@pytest.mark.parametrize("mode", ["smoothstep", "smootherstep", "cubic"])
def test_ml1b_smooth_interpolation_with_offset_start_and_one_keyframe(mode):
    solo = curve(
        start_frame=4, end_frame=24, interpolation=mode,
        keys=[{"frame": 16, "value": 0.08}],
    )
    output, diag = compile_motion_lab(
        project(), layers=[solo], include_series=True,
    )
    assert diag["series"]["translation_x"][0] == 0
    assert resolved(output, 4) == pytest.approx(0)
    assert 0 < resolved(output, 10) < 0.08
    assert resolved(output, 16) == pytest.approx(0.08)
    assert resolved(output, 22) == pytest.approx(0.08)


@pytest.mark.parametrize("mode", ["linear", "hold", "smoothstep", "smootherstep", "cubic"])
def test_ml1b_interpolations_are_idempotent_on_apply(mode):
    layers = [curve(interpolation=mode)]
    once, _ = compile_motion_lab(project(), layers=layers)
    repeated, _ = compile_motion_lab(once, layers=layers)
    assert repeated["camera_3d"] == once["camera_3d"]
    assert repeated["motion_lab"]["layers"][0]["interpolation"] == mode

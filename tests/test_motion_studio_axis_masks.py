"""MS4.2: axis-aware Replace/Add are confined to chosen frames and axes."""
from copy import deepcopy

import pytest

from morphorum.animation_projects import normalize_animation_project
from morphorum.motion_lab import (
    AXES, MotionLabError, compile_motion_lab, normalize_layers,
)


def project():
    data = normalize_animation_project({
        "name": "MS4.2 axis-mask regression",
        "animation": {"mode": "3d", "max_frames": 48, "fps": 24},
    }, project_id="ms42-axes")
    for axis, value in [
        ("translation_x", .015),
        ("translation_y", .025),
        ("translation_z", .035),
        ("rotation_x", .08),
        ("rotation_y", .09),
        ("rotation_z", .12),
    ]:
        data["camera_3d"][axis] = f"0:({value})"
        data["tracks"]["camera_3d"][axis]["schedule"] = f"0:({value})"
    return data


def layer(preset="spiral", **overrides):
    return {
        "id": "ms4-region", "type": "preset", "preset": preset,
        "start_frame": 10, "end_frame": 26,
        "strength": .7, "cycle_seconds": 2, "fade_seconds": 0,
        "enabled": True, "blend": "replace",
        "axes": ["translation_z", "rotation_z"],
        **overrides,
    }


def series(p, layers):
    result, diagnostic = compile_motion_lab(p, layers=layers, include_series=True)
    return result, diagnostic["series"]


def test_selected_axis_replace_changes_only_selected_axes_within_range():
    p = project()
    before = deepcopy(p)
    updated, values = series(p, [layer()])
    assert p == before
    for axis in AXES:
        original = {"translation_x":.015,"translation_y":.025,
                    "translation_z":.035,"rotation_x":.08,
                    "rotation_y":.09,"rotation_z":.12}[axis]
        assert values[axis][9] == pytest.approx(original)
        assert values[axis][26] == pytest.approx(original)
        if axis not in ("translation_z", "rotation_z"):
            assert all(v == pytest.approx(original) for v in values[axis])
        else:
            assert any(v != pytest.approx(original) for v in values[axis][11:25])
    assert updated["motion_lab"]["layers"][0]["axes"] == ["translation_z", "rotation_z"]
    again, same = series(updated, [layer()])
    assert values == same


def test_add_preserves_original_motion_and_only_targets_selected_axis():
    p = project()
    _, base = series(p, [layer("still", axes=["rotation_y"])])
    _, motion = series(p, [layer(preset="wave", blend="add",
                                 axes=["translation_x"])])
    for axis in AXES:
        if axis == "translation_x":
            assert any(v != pytest.approx(.015) for v in motion[axis][11:25])
        else:
            fixed = {"translation_x":.015, "translation_y":.025,
                     "translation_z":.035,"rotation_x":.08,
                     "rotation_y":.09,"rotation_z":.12}[axis]
            assert all(v == pytest.approx(fixed) for v in motion[axis])
    assert all(v == pytest.approx(0) for v in base["rotation_y"][10:26])
    assert base["translation_z"][14] == pytest.approx(.035)


def test_legacy_preset_without_axis_mask_keeps_original_semantics():
    p = project()
    original = layer()
    original.pop("axes")
    new = normalize_layers([original],p)[0]
    assert "axes" not in new
    _, masked = series(p,[layer()])
    _, legacy = series(p,[original])
    assert legacy["translation_x"][15] != pytest.approx(masked["translation_x"][15])


@pytest.mark.parametrize("axes",[
    [], ["invalid"], ["translation_z","translation_z"],
    ["rotation_x"], "translation_z", [None],
])
def test_invalid_or_unsupported_axis_mask_is_rejected(axes):
    with pytest.raises(MotionLabError, match="axes"):
        normalize_layers([layer(axes=axes)],project())


def test_disabled_replace_never_affects_camera():
    _, d = series(project(), [layer(enabled=False)])
    assert d["translation_z"][12] == pytest.approx(.035)
    assert d["rotation_z"][12] == pytest.approx(.12)

"""ML2 deterministic frame-aligned Motion Lab recording layers."""
from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

import morphorum.animation_projects as projects
from morphorum.animation_projects import normalize_animation_project
from morphorum.animation_resolution import resolve_project_frame
from morphorum.app import app
from morphorum.motion_lab import AXES, MotionLabError, compile_motion_lab, normalize_layers


def project(frames=48, fps=12):
    return normalize_animation_project({
        "name": "ML2 recording",
        "animation": {"mode": "3d", "max_frames": frames, "fps": fps},
    }, project_id="recording-test")


def take(**overrides):
    samples = [
        [0.01, 0, 0, 0, 0.10, 0],
        [0.02, 0, 0, 0, 0.20, 0],
        [0.03, 0, 0, 0, 0.30, 0],
        [0.02, 0, 0, 0, 0.20, 0],
        [0.01, 0, 0, 0, 0.10, 0],
        [0.00, 0, 0, 0, 0.00, 0],
    ]
    return {
        "id": "take-001",
        "type": "recording",
        "name": "Keyboard take",
        "enabled": True,
        "blend": "add",
        "start_frame": 4,
        "end_frame": 10,
        "fps": 12,
        "source": "keyboard",
        "capture_version": 1,
        "axes": ["translation_x", "rotation_y"],
        "samples": samples,
        **overrides,
    }


def resolved(p, frame, axis):
    return float(resolve_project_frame(p, frame)["camera_3d"][axis])


def test_recording_layer_is_frame_aligned_native_motion_and_round_trips():
    original = project()
    snapshot = deepcopy(original)
    compiled, diagnostics = compile_motion_lab(
        original, layers=[take()], include_series=True,
    )
    assert original == snapshot
    assert diagnostics["frames"] == 48
    assert diagnostics["series"]["translation_x"][3] == 0
    assert diagnostics["series"]["translation_x"][4] == pytest.approx(.01)
    assert diagnostics["series"]["translation_x"][6] == pytest.approx(.03)
    assert diagnostics["series"]["rotation_y"][6] == pytest.approx(.30)
    assert diagnostics["series"]["translation_x"][10] == 0
    assert resolved(compiled, 6, "translation_x") == pytest.approx(.03)
    assert resolved(compiled, 6, "rotation_y") == pytest.approx(.30)

    saved = normalize_animation_project(
        compiled, existing=compiled, project_id=compiled["id"], prefer_tracks=True,
    )
    layer = saved["motion_lab"]["layers"][0]
    assert layer["type"] == "recording"
    assert layer["fps"] == 12
    assert layer["capture_version"] == 1
    assert layer["axes"] == ["translation_x", "rotation_y"]
    assert layer["samples"][2] == pytest.approx([.03, 0, 0, 0, .30, 0])


def test_recording_add_replace_order_with_preset_and_cubic_keyframes():
    preset = {
        "id": "push", "type": "preset", "preset": "push-in",
        "enabled": True, "blend": "add", "strength": .5,
        "start_frame": 0, "end_frame": 48,
        "cycle_seconds": 2, "fade_seconds": 0,
    }
    curve = {
        "id": "curve", "type": "keyframes", "axis": "translation_x",
        "enabled": True, "blend": "add", "interpolation": "cubic",
        "start_frame": 0, "end_frame": 48,
        "keys": [{"frame": 0, "value": 0}, {"frame": 12, "value": .04}],
    }
    recording = take(
        blend="replace",
        axes=["rotation_y"],
        samples=[
            [0, 0, 0, 0, .10, 0],
            [0, 0, 0, 0, .20, 0],
            [0, 0, 0, 0, .30, 0],
            [0, 0, 0, 0, .20, 0],
            [0, 0, 0, 0, .10, 0],
            [0, 0, 0, 0, 0, 0],
        ],
    )
    compiled, _ = compile_motion_lab(
        project(), layers=[preset, curve, recording],
    )
    # Replace applies only to armed recording axes; unrelated preset/keyframe
    # motion remains intact.
    assert resolved(compiled, 6, "rotation_y") == pytest.approx(.30)
    assert resolved(compiled, 6, "translation_x") > 0
    assert resolved(compiled, 6, "translation_z") > 0


def test_disabled_recording_layer_is_inert_and_preserved():
    disabled = take(enabled=False)
    compiled, diagnostics = compile_motion_lab(
        project(), layers=[disabled], include_series=True,
    )
    assert compiled["motion_lab"]["layers"][0]["enabled"] is False
    for axis in AXES:
        assert all(value == pytest.approx(0) for value in diagnostics["series"][axis])


def test_recording_reapply_is_idempotent():
    once, _ = compile_motion_lab(project(), layers=[take()])
    twice, _ = compile_motion_lab(once, layers=[take()])
    assert twice["camera_3d"] == once["camera_3d"]
    assert twice["motion_lab"]["layers"] == once["motion_lab"]["layers"]


@pytest.mark.parametrize("bad,match", [
    (take(samples="nope"), "sample rows"),
    (take(samples=[[0, 0, 0, 0, 0, 0]]), "exactly one sample"),
    (take(samples=[[0, 0, 0]] * 6), "six numeric values"),
    (take(samples=[[float("nan"), 0, 0, 0, 0, 0]] * 6), "Recording sample"),
    (take(samples=[[float("inf"), 0, 0, 0, 0, 0]] * 6), "Recording sample"),
    (take(axes=["translation_x", "translation_x"]), "unique"),
    (take(axes=["warp_speed"]), "six camera axes"),
    (take(axes=[]), "at least one axis"),
    (take(fps=24), "does not match project FPS"),
    (take(capture_version=2), "capture version"),
    (take(source="telepathy"), "source"),
    (take(
        axes=["translation_x"],
        samples=[[0, .01, 0, 0, 0, 0]] * 6,
    ), "unarmed axis"),
])
def test_invalid_recording_layers_fail_before_rendering(bad, match):
    with pytest.raises(MotionLabError, match=match):
        normalize_layers([bad], project())


def test_frame_zero_recording_must_be_stationary():
    bad = take(
        start_frame=0,
        end_frame=2,
        axes=["translation_x"],
        samples=[[.01, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]],
    )
    with pytest.raises(MotionLabError, match="Frame 0"):
        normalize_layers([bad], project())


def test_recording_preview_apply_api_persists_exact_take(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        made = client.post("/api/animation/projects", json={"name": "ML2 API"})
        assert made.status_code == 201
        source = made.json()["project"]
        source["animation"].update(mode="3d", max_frames=48, fps=12)
        project_id = source["id"]
        saved = client.put(f"/api/animation/projects/{project_id}", json=source)
        assert saved.status_code == 200, saved.text

        endpoint = f"/api/animation/projects/{project_id}/motion-lab"
        preview = client.post(endpoint + "/preview", json={"layers": [take()]})
        assert preview.status_code == 200, preview.text
        assert preview.json()["diagnostics"]["series"]["translation_x"][6] == pytest.approx(.03)
        untouched = client.get(f"/api/animation/projects/{project_id}").json()["project"]
        assert untouched["motion_lab"]["layers"] == []

        applied = client.post(endpoint + "/apply", json={"layers": [take()]})
        assert applied.status_code == 200, applied.text
        loaded = client.get(f"/api/animation/projects/{project_id}").json()["project"]
        assert loaded["motion_lab"]["layers"][0]["type"] == "recording"
        assert loaded["motion_lab"]["layers"][0]["samples"][2][0] == pytest.approx(.03)
        assert loaded["camera_3d"]["translation_x"] != "0:(0)"

        repeated = client.post(endpoint + "/apply", json={"layers": [take()]})
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["project"]["camera_3d"]["translation_x"] == loaded["camera_3d"]["translation_x"]


def test_recording_api_rejects_project_fps_change(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        made = client.post("/api/animation/projects", json={"name": "ML2 FPS"})
        source = made.json()["project"]
        source["animation"].update(mode="3d", max_frames=48, fps=24)
        project_id = source["id"]
        assert client.put(f"/api/animation/projects/{project_id}", json=source).status_code == 200
        response = client.post(
            f"/api/animation/projects/{project_id}/motion-lab/preview",
            json={"layers": [take()]},
        )
        assert response.status_code == 400
        assert "does not match project FPS" in response.json()["detail"]

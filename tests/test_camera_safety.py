from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest
from PIL import Image

from morphorum.animation_3d import Camera3DError, render_depth_warp
from morphorum.animation_projects import normalize_animation_project
from morphorum.camera_safety import camera_motion_advisories
from morphorum.animation_render import _format_camera_warp_failure
from morphorum.animation_preflight import check_animation_render_preflight
import morphorum.animation_preflight as preflight


def project(frames=80):
    p = {
        "id": "camera-safety", "name": "Camera Safety",
        "animation": {"mode": "3d", "max_frames": frames, "fps": 24,
                      "width": 1024, "height": 1024, "start_mode": "prompt"},
        "model": {"model_id": "missing-model", "family": "sdxl"},
        "prompts": {"0": "An abandoned computer lab"},
        "camera_3d": {"translation_z": "0:(0.06)", "rotation_y": "0:(0.8)",
                      "fov": "0:(40)"},
        "generation": {"sampler": "euler", "guidance": "0:(6)"},
    }
    return normalize_animation_project(p, existing=p, project_id=p["id"])


def test_camera_schedule_risks_are_advisory_and_do_not_mutate():
    p = project()
    snapshot = deepcopy(p)
    result = camera_motion_advisories(p)
    assert result["sampled_frames"] == 80
    assert any("accumulates" in i["message"] for i in result["issues"])
    assert all(i["severity"] == "warning" for i in result["issues"])
    assert p == snapshot


def test_zero_motion_or_2d_has_no_camera_risk():
    p = project(frames=10)
    p["camera_3d"]["translation_z"] = "0:(0)"
    p["camera_3d"]["rotation_y"] = "0:(0)"
    p = normalize_animation_project(p, existing=p, project_id=p["id"])
    assert camera_motion_advisories(p)["issues"] == []
    p["animation"]["mode"] = "2d"
    assert camera_motion_advisories(p)["basis"] == "not-applicable"


def test_large_single_frame_move_and_narrow_fov():
    p = project(frames=12)
    p["camera_3d"]["translation_z"] = "0:(0.6)"
    p["camera_3d"]["fov"] = "0:(14)"
    p = normalize_animation_project(p, existing=p, project_id=p["id"])
    report = camera_motion_advisories(p)
    assert any("Large per-frame" in i["message"] for i in report["issues"])
    assert any(i["field"] == "camera_3d.fov" for i in report["issues"])


def test_preflight_reports_camera_warnings_even_with_missing_model(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "get_model", lambda _id: None)
    result = check_animation_render_preflight(project(), tmp_path / "missing.png")
    assert not result["valid"]
    assert result["camera_safety"]["sampled_frames"] == 80
    assert any(i["severity"] == "warning" and
               i["field"].startswith("camera_3d.") for i in result["issues"])


def test_empty_projection_error_includes_measured_in_front_count_and_axis():
    img = Image.new("RGB", (16, 16), (80, 120, 150))
    depth = np.full((16, 16), 0.5, dtype=np.float32)
    with pytest.raises(Camera3DError) as error:
        render_depth_warp(img, depth, translation_z=20.0)
    message = str(error.value)
    assert "no visible pixels" in message
    assert "behind camera" in message
    assert "0/256" in message
    assert "+20" in message


def test_warp_failure_reports_last_successful_coverage():
    msg = _format_camera_warp_failure(
        50, Camera3DError("empty projection"),
        {"translation_z": 0.8, "rotation_y": 1.5, "fov": 35},
        (49, 0.123),
    )
    assert "frame 50" in msg
    assert "frame 49" in msg
    assert "12.3%" in msg
    assert "rotation_y=+1.5" in msg
    assert "field of view" in msg
    msg = _format_camera_warp_failure(
        50, Camera3DError("empty projection"), {"fov": 35}, None,
    )
    assert "No prior 3D coverage available" in msg

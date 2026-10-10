from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageSequence

from morphorum.animation_motion import (
    MotionPreviewError,
    _frame_transform_matrix,
    capture_frames,
    prepare_preview_source,
    render_affine,
    render_motion_preview,
    validate_source_image_bytes,
)


def sample_project(max_frames: int = 6) -> dict:
    return {
        "schema_version": 1,
        "id": "motion-test",
        "name": "Motion Test",
        "animation": {
            "max_frames": max_frames,
            "fps": 12.0,
            "width": 64,
            "height": 64,
            "prompt_transition": "blend",
            "source_image": "assets/source.png",
            "source_image_name": "source.png",
        },
        "model": {"model_id": "", "family": "", "variant": ""},
        "prompts": {"0": "test"},
        "negative_prompts": {"0": ""},
        "motion": {
            "angle": "0:(0), 5:(5)",
            "zoom": "0:(1.0), 5:(1.02)",
            "translation_x": "0:(0), 5:(2)",
            "translation_y": "0:(0)",
            "border_mode": "replicate",
        },
        "generation": {
            "strength": "0:(0.65)",
            "noise": "0:(0.02)",
            "steps": "0:(9)",
            "guidance": "0:(0)",
            "sampler": "flowmatch_euler",
            "seed": 123,
            "seed_behavior": "fixed",
            "seed_increment": 1,
        },
        "notes": "",
    }


def marker_image(width: int = 5, height: int = 5) -> Image.Image:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[height // 2, width // 2] = [255, 0, 0]
    return Image.fromarray(image, mode="RGB")


def test_identity_transform_preserves_pixels() -> None:
    source = marker_image()
    matrix = _frame_transform_matrix(
        width=source.width,
        height=source.height,
        angle=0,
        zoom=1,
        translation_x=0,
        translation_y=0,
    )
    rendered = render_affine(source, matrix, border_mode="replicate")
    np.testing.assert_array_equal(np.asarray(rendered), np.asarray(source))


def test_positive_translation_moves_content_right() -> None:
    source = marker_image()
    matrix = _frame_transform_matrix(
        width=source.width,
        height=source.height,
        angle=0,
        zoom=1,
        translation_x=1,
        translation_y=0,
    )
    rendered = np.asarray(render_affine(source, matrix, border_mode="replicate"))
    red = rendered[..., 0]
    y, x = np.unravel_index(np.argmax(red), red.shape)
    assert (y, x) == (2, 3)


def test_wrap_and_replicate_have_distinct_edge_behavior() -> None:
    array = np.zeros((4, 4, 3), dtype=np.uint8)
    array[:, 0] = [255, 0, 0]
    array[:, -1] = [0, 0, 255]
    source = Image.fromarray(array, mode="RGB")

    matrix = _frame_transform_matrix(
        width=4,
        height=4,
        angle=0,
        zoom=1,
        translation_x=1,
        translation_y=0,
    )

    replicate = np.asarray(render_affine(source, matrix, border_mode="replicate"))
    wrapped = np.asarray(render_affine(source, matrix, border_mode="wrap"))

    assert replicate[1, 0, 0] > replicate[1, 0, 2]
    assert wrapped[1, 0, 2] > wrapped[1, 0, 0]


def test_invalid_border_mode_is_rejected() -> None:
    source = marker_image()
    matrix = np.eye(3)
    with pytest.raises(MotionPreviewError, match="Unsupported 2D border mode"):
        render_affine(source, matrix, border_mode="teleport")


def test_capture_frames_keeps_first_and_last() -> None:
    frames = capture_frames(1000, maximum=20)
    assert frames[0] == 0
    assert frames[-1] == 999
    assert len(frames) <= 20


def test_prepare_preview_source_matches_project_aspect() -> None:
    source = Image.new("RGB", (200, 100), "white")
    prepared = prepare_preview_source(
        source,
        width=100,
        height=200,
        max_dimension=100,
    )
    assert prepared.size == (50, 100)


def test_source_image_validation_accepts_png_and_rejects_garbage() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 12), "orange").save(buffer, format="PNG")

    image = validate_source_image_bytes(buffer.getvalue())
    assert image.size == (16, 12)
    assert image.mode == "RGB"

    with pytest.raises(MotionPreviewError, match="Could not decode source image"):
        validate_source_image_bytes(b"definitely not an image")


def test_render_motion_preview_writes_animated_gif(tmp_path: Path) -> None:
    project = sample_project(max_frames=6)
    source = Image.new("RGB", (64, 64), "black")
    source_array = np.asarray(source).copy()
    source_array[20:44, 20:44] = [255, 128, 0]
    source = Image.fromarray(source_array, mode="RGB")

    output = tmp_path / "preview.gif"
    progress: list[tuple[int, int]] = []
    result = render_motion_preview(
        project,
        source,
        output,
        max_dimension=64,
        max_capture_frames=6,
        progress_callback=lambda frame, last: progress.append((frame, last)),
    )

    assert output.is_file()
    assert result["preview_width"] == 64
    assert result["preview_height"] == 64
    assert result["source_frames"] == 6
    assert result["captured_frames"] == 6
    assert result["border_mode"] == "replicate"
    assert progress[-1] == (5, 5)

    with Image.open(output) as gif:
        assert getattr(gif, "is_animated", False) is True
        frames = list(ImageSequence.Iterator(gif))
        assert len(frames) == 6


def test_zoom_must_be_positive() -> None:
    with pytest.raises(MotionPreviewError, match="Zoom must be greater than zero"):
        _frame_transform_matrix(
            width=64,
            height=64,
            angle=0,
            zoom=0,
            translation_x=0,
            translation_y=0,
        )



def test_zoom_out_factor_below_one_is_valid() -> None:
    matrix = _frame_transform_matrix(
        width=64,
        height=64,
        angle=0,
        zoom=0.995,
        translation_x=0,
        translation_y=0,
    )
    assert np.isfinite(matrix).all()
    assert np.linalg.det(matrix) > 0


def test_b53_camera_preview_simulates_cpu_depth_and_tracks_coverage(
    tmp_path: Path, monkeypatch,
) -> None:
    import morphorum.animation_motion as motion

    project = sample_project(max_frames=5)
    project["animation"]["mode"] = "3d"
    project["camera_3d"] = {
        "translation_x": "0:(0.2)", "translation_y": "0:(0)",
        "translation_z": "0:(0)", "rotation_x": "0:(0)",
        "rotation_y": "0:(0)", "rotation_z": "0:(0)",
        "fov": "0:(40)", "projection_mode": "splat",
        "hole_fill": "nearest", "depth_resolution": "auto",
    }
    image = Image.fromarray(
        np.tile(np.arange(64, dtype=np.uint8)[None, :, None], (64, 1, 3)) * 4,
        mode="RGB",
    )
    calls: list[str] = []

    def fake_estimate(frame: Image.Image, **kwargs):
        calls.append(str(kwargs.get("device")))
        return {"cache_key": "constant", "cache_hit": False}

    monkeypatch.setattr(motion.depth_manager, "estimate", fake_estimate)
    monkeypatch.setattr(
        motion.depth_manager,
        "load_cached_array",
        lambda _key: np.full((64, 64), 0.5, dtype=np.float32),
    )
    monkeypatch.setattr(motion.depth_manager, "unload", lambda: calls.append("unload"))
    progress = []
    plain = motion.render_motion_preview(
        project, image, tmp_path / "plain.gif",
        max_dimension=64, max_capture_frames=5,
        progress_callback=lambda frame, maximum: progress.append((frame, maximum)),
    )
    overlay = motion.render_motion_preview(
        project, image, tmp_path / "overlay.gif",
        max_dimension=64, max_capture_frames=5, highlight_holes=True,
    )
    assert plain["mode"] == "3d"
    assert plain["depth_device"] == "cpu"
    assert plain["source_frames"] == plain["captured_frames"] == 5
    assert len(plain["per_frame_coverage"]) == 5
    assert plain["minimum_coverage"] < 1.0
    assert plain["worst_coverage_frame"] >= 1
    assert overlay["highlight_holes"] is True
    assert all(0 <= frame["filled_fraction"] <= 1 for frame in plain["per_frame_coverage"])
    assert progress[-1] == (4, 4)
    assert calls.count("cpu") == 8
    assert calls.count("unload") == 2
    with Image.open(tmp_path / "plain.gif") as gif:
        plain_last = np.asarray(list(ImageSequence.Iterator(gif))[-1].convert("RGB"))
    with Image.open(tmp_path / "overlay.gif") as gif:
        red_last = np.asarray(list(ImageSequence.Iterator(gif))[-1].convert("RGB"))
    assert not np.array_equal(plain_last, red_last)


def test_b53_camera_preview_rejects_unbounded_frame_counts(
    tmp_path: Path,
) -> None:
    project = sample_project(max_frames=3001)
    project["animation"]["mode"] = "3d"
    with pytest.raises(MotionPreviewError, match="up to 3000"):
        render_motion_preview(
            project, Image.new("RGB", (32, 32), "red"), tmp_path / "too-long.gif",
        )


def test_b53_legacy_2d_preview_result_unchanged(
    tmp_path: Path,
) -> None:
    result = render_motion_preview(
        sample_project(max_frames=4),
        Image.new("RGB", (64, 64), "orange"),
        tmp_path / "legacy2d.gif",
        highlight_holes=True,
    )
    assert result["border_mode"] == "replicate"
    assert result["source_frames"] == 4
    assert "average_coverage" not in result


def test_motion_lab_calibration_grid_is_visible_and_bounded() -> None:
    from morphorum.animation_motion import create_motion_reference_grid
    grid = create_motion_reference_grid(1024, 1536)
    assert grid.size == (213, 320)
    assert grid.mode == "RGB"
    colors = grid.getcolors(maxcolors=100_000)
    assert colors is not None and len(colors) >= 4


def test_motion_lab_preview_without_uploaded_source_uses_grid(
    tmp_path: Path, monkeypatch,
) -> None:
    import time
    import morphorum.animation_motion as motion
    from morphorum.animation_motion import MotionPreviewManager

    monkeypatch.setattr(motion, "OUTPUTS_DIR", tmp_path)
    manager = MotionPreviewManager()
    project = sample_project(max_frames=6)
    project["animation"]["mode"] = "2d"
    started = manager.start(project=project, source_path=None)
    job = manager.get(started["id"])
    for _ in range(150):
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(.02)
        job = manager.get(started["id"])
    assert job["status"] == "completed", job
    assert job["result"]["source_kind"] == "calibration-grid"
    assert job["result"]["source_frames"] == 6
    assert manager.result_path(started["id"]).is_file()
    with Image.open(manager.result_path(started["id"])) as preview:
        assert getattr(preview, "is_animated", False)


def test_long_3d_preview_is_accepted_without_running_heavy_depth_work(tmp_path, monkeypatch):
    import morphorum.animation_motion as motion

    monkeypatch.setattr(motion, "OUTPUTS_DIR", tmp_path)
    spawned = []
    class NoStartThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)
        def start(self):
            pass
    monkeypatch.setattr(motion.threading, "Thread", NoStartThread)
    manager = motion.MotionPreviewManager()
    project = sample_project(max_frames=196)
    project["animation"]["mode"] = "3d"
    accepted = manager.start(project=project, source_path=None)
    assert accepted["id"]
    assert spawned
    project["animation"]["max_frames"] = motion.PREVIEW_MAX_3D_SOURCE_FRAMES
    assert manager.start(project=project, source_path=None)["id"]
    project["animation"]["max_frames"] = motion.PREVIEW_MAX_3D_SOURCE_FRAMES + 1
    with pytest.raises(MotionPreviewError, match="3000 frames"):
        manager.start(project=project, source_path=None)


def test_long_preview_capture_is_bounded_but_includes_endpoints():
    positions = capture_frames(196, 72)
    assert len(positions) <= 72
    assert positions[0] == 0
    assert positions[-1] == 195

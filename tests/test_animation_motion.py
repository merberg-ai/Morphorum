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

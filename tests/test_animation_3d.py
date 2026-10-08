from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from morphorum.animation_3d import Camera3DError, render_depth_warp


def test_identity_depth_warp_preserves_image() -> None:
    image = Image.new("RGB", (32, 24), "black")
    for x in range(8, 24):
        for y in range(6, 18):
            image.putpixel((x, y), (220, 80, 20))
    depth = np.linspace(0.0, 1.0, 32 * 24, dtype=np.float32).reshape(24, 32)

    result = render_depth_warp(image, depth, fov=40.0)

    assert np.array_equal(np.asarray(result.image), np.asarray(image))
    assert result.telemetry["projected_coverage"] == pytest.approx(1.0)
    assert result.telemetry["filled_fraction"] == pytest.approx(0.0)


def test_translation_z_produces_depth_aware_projection() -> None:
    image = Image.new("RGB", (48, 32), "black")
    for x in range(10, 20):
        for y in range(10, 22):
            image.putpixel((x, y), (255, 0, 0))
    for x in range(30, 40):
        for y in range(10, 22):
            image.putpixel((x, y), (0, 0, 255))

    depth = np.full((32, 48), 0.15, dtype=np.float32)
    depth[10:22, 10:20] = 0.95
    depth[10:22, 30:40] = 0.25

    result = render_depth_warp(
        image,
        depth,
        translation_z=0.08,
        fov=40.0,
    )

    rendered = np.asarray(result.image)
    assert not np.array_equal(rendered, np.asarray(image))
    assert 0.0 < result.telemetry["projected_coverage"] <= 1.0
    assert result.telemetry["translation_z"] == pytest.approx(0.08)
    assert result.telemetry["warp"] == "depth-forward-zbuffer-nearest-fill"


def test_rotation_y_changes_projection_and_records_camera_state() -> None:
    image = Image.new("RGB", (40, 40), "gray")
    depth = np.tile(np.linspace(0.0, 1.0, 40, dtype=np.float32), (40, 1))

    result = render_depth_warp(
        image,
        depth,
        rotation_y=1.0,
        fov=55.0,
    )

    assert result.telemetry["rotation_y"] == pytest.approx(1.0)
    assert result.telemetry["fov"] == pytest.approx(55.0)
    assert result.telemetry["filled_fraction"] >= 0.0


def test_depth_warp_rejects_shape_and_projection_errors() -> None:
    image = Image.new("RGB", (16, 16), "black")

    with pytest.raises(Camera3DError, match="does not match image"):
        render_depth_warp(image, np.zeros((8, 8), dtype=np.float32))

    with pytest.raises(Camera3DError, match="field of view"):
        render_depth_warp(
            image,
            np.zeros((16, 16), dtype=np.float32),
            fov=180.0,
        )



def test_fov_change_uses_previous_frame_intrinsics() -> None:
    image = Image.new("RGB", (40, 30), "black")
    for x in range(12, 28):
        for y in range(8, 22):
            image.putpixel((x, y), (40, 220, 80))
    depth = np.full((30, 40), 0.5, dtype=np.float32)

    result = render_depth_warp(
        image,
        depth,
        source_fov=40.0,
        fov=60.0,
    )

    assert not np.array_equal(np.asarray(result.image), np.asarray(image))
    assert result.telemetry["source_fov"] == pytest.approx(40.0)
    assert result.telemetry["fov"] == pytest.approx(60.0)

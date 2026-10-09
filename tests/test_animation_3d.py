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


def test_b51_splat_identity_and_binary_mask_preserve_source() -> None:
    image = Image.new("RGB", (32, 24), "black")
    for y in range(6, 18):
        for x in range(8, 24):
            image.putpixel((x, y), (220, 80, 20))
    depth = np.full((24, 32), 0.5, dtype=np.float32)

    legacy = render_depth_warp(image, depth, projection_mode="legacy")
    improved = render_depth_warp(
        image, depth, projection_mode="splat", fill_mode="background",
    )
    assert np.array_equal(np.asarray(legacy.image), np.asarray(image))
    assert np.array_equal(np.asarray(improved.image), np.asarray(image))
    assert improved.hole_mask is not None
    assert improved.hole_mask.mode == "L"
    assert improved.hole_mask.size == image.size
    assert not np.asarray(improved.hole_mask).any()
    assert improved.telemetry["disoccluded_pixels"] == 0
    assert improved.telemetry["projected_coverage"] == pytest.approx(1.0)
    assert improved.telemetry["warp"] == "depth-bilinear-zbuffer-background-fill"


def test_b51_splat_mask_matches_coverage_and_tracks_motion() -> None:
    image = Image.new("RGB", (48, 32), (75, 100, 125))
    depth = np.full((32, 48), 0.15, dtype=np.float32)
    depth[8:24, 16:32] = 0.95
    for y in range(8, 24):
        for x in range(16, 32):
            image.putpixel((x, y), (250, 0, 0))

    warped = render_depth_warp(
        image, depth, translation_x=0.20,
        projection_mode="splat", fill_mode="background",
    )
    mask = np.asarray(warped.hole_mask)
    assert mask.dtype == np.uint8
    assert set(np.unique(mask)).issubset({0, 255})
    assert np.any(mask == 255)
    count = int(np.count_nonzero(mask))
    assert warped.telemetry["disoccluded_pixels"] == count
    assert warped.telemetry["visible_pixels"] + count == 48 * 32
    assert warped.telemetry["filled_fraction"] == pytest.approx(count / (48 * 32))
    assert warped.telemetry["projected_coverage"] == pytest.approx(1 - count / (48 * 32))
    assert warped.telemetry["fill_mode"] == "background"
    assert np.asarray(warped.image).shape == (32, 48, 3)


def test_b51_splat_depth_test_prevents_background_bleed() -> None:
    # A nearer red plane occludes a farther blue plane where they overlap.
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]  # nearest
    rgb[0, 1] = [0, 0, 255]  # farthest
    from morphorum.animation_3d import _render_splat

    px = np.array([0.25, 0.25, 100.0, 100.0], dtype=np.float32)
    py = np.array([0.25, 0.25, 100.0, 100.0], dtype=np.float32)
    z = np.array([1.0, 3.0, 3.0, 3.0], dtype=np.float32)
    visible = np.array([True, True, False, False])
    output, valid, zbuffer = _render_splat(rgb, px, py, z, visible)
    assert valid[0, 0]
    assert output[0, 0].tolist() == [255, 0, 0]
    assert zbuffer[0, 0] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("projection_mode", "fill_mode"),
    [("unknown", "nearest"), ("splat", "bad-fill")],
)
def test_b51_rejects_unknown_projection_config(projection_mode, fill_mode) -> None:
    with pytest.raises(Camera3DError, match="Unsupported 3D"):
        render_depth_warp(
            Image.new("RGB", (16, 16)),
            np.ones((16, 16), dtype=np.float32),
            projection_mode=projection_mode,
            fill_mode=fill_mode,
        )


def test_b51_legacy_default_is_exact_match_with_explicit_mode() -> None:
    image = Image.new("RGB", (36, 27), (10, 20, 30))
    depth = np.tile(np.linspace(0, 1, 36, dtype=np.float32), (27, 1))
    opts = dict(translation_x=0.07, rotation_y=0.5, source_fov=45, fov=50)
    implicit = render_depth_warp(image, depth, **opts)
    explicit = render_depth_warp(
        image, depth, projection_mode="legacy", fill_mode="nearest", **opts,
    )
    assert np.array_equal(np.asarray(implicit.image), np.asarray(explicit.image))
    assert implicit.telemetry["warp"] == "depth-forward-zbuffer-nearest-fill"
    assert implicit.telemetry["projection_mode"] == "legacy"
    assert implicit.telemetry["fill_mode"] == "nearest"


def test_b52_reverse_camera_chain_inverse_matches_forward_math() -> None:
    from morphorum.animation_3d import _rotation_matrix, reverse_camera_chain

    steps = [
        {"translation_x": 0.02, "translation_y": -0.01,
         "translation_z": 0.005, "rotation_x": 0.3,
         "rotation_y": -0.5, "rotation_z": 0.8},
        {"translation_x": -0.03, "translation_y": 0.02,
         "translation_z": 0.004, "rotation_x": -0.4,
         "rotation_y": 0.6, "rotation_z": -0.1},
    ]
    point = np.array([[0.03, -0.08, 2.4]], dtype=np.float64)
    changed = point.copy()
    for step in steps:
        r = _rotation_matrix(
            step["rotation_x"], step["rotation_y"], step["rotation_z"],
        ).astype(np.float64)
        t = np.array([
            step["translation_x"], step["translation_y"],
            step["translation_z"],
        ])
        changed = (changed - t) @ r

    matrix, offset = reverse_camera_chain(steps)
    original = changed @ matrix + offset
    np.testing.assert_allclose(original, point, atol=1e-6)


def test_b52_reprojection_identity_matrix_does_not_shift_frame() -> None:
    image = Image.new("RGB", (24, 24), "teal")
    depth = np.full((24, 24), 0.4, dtype=np.float32)
    from morphorum.animation_3d import reverse_camera_chain
    matrix, offset = reverse_camera_chain([])
    warped = render_depth_warp(
        image, depth, projection_mode="splat",
        transform_matrix=matrix, transform_offset=offset,
    )
    assert np.array_equal(np.asarray(warped.image), np.asarray(image))
    assert warped.telemetry["projected_coverage"] == pytest.approx(1.0)


def test_b52_reprojection_rejects_bad_matrices() -> None:
    image = Image.new("RGB", (16, 16), "black")
    depth = np.full((16, 16), 0.5, dtype=np.float32)
    with pytest.raises(Camera3DError, match="both matrix and offset"):
        render_depth_warp(image, depth, transform_matrix=np.eye(3))
    with pytest.raises(Camera3DError, match="finite 3x3"):
        render_depth_warp(
            image, depth,
            transform_matrix=np.full((3, 3), np.nan),
            transform_offset=np.zeros(3),
        )

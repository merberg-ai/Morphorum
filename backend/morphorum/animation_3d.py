from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage


class Camera3DError(RuntimeError):
    pass


@dataclass(frozen=True)
class Camera3DWarpResult:
    image: Image.Image
    telemetry: dict[str, Any]


def _rotation_matrix(
    rotation_x: float,
    rotation_y: float,
    rotation_z: float,
) -> np.ndarray:
    rx = math.radians(float(rotation_x))
    ry = math.radians(float(rotation_y))
    rz = math.radians(float(rotation_z))

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    mx = np.array(
        [[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]],
        dtype=np.float32,
    )
    my = np.array(
        [[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]],
        dtype=np.float32,
    )
    mz = np.array(
        [[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )
    return mz @ my @ mx


def _fill_holes_nearest(image: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if valid.all():
        return image
    if not valid.any():
        raise Camera3DError("3D camera projection moved the entire scene outside the image.")

    missing = ~valid
    _, indices = ndimage.distance_transform_edt(
        missing,
        return_distances=True,
        return_indices=True,
    )
    filled = image.copy()
    filled[missing] = image[indices[0][missing], indices[1][missing]]
    return filled


def render_depth_warp(
    image: Image.Image,
    depth: np.ndarray,
    *,
    translation_x: float = 0.0,
    translation_y: float = 0.0,
    translation_z: float = 0.0,
    rotation_x: float = 0.0,
    rotation_y: float = 0.0,
    rotation_z: float = 0.0,
    fov: float = 40.0,
    source_fov: float | None = None,
    near_depth: float = 1.0,
    far_depth: float = 4.0,
) -> Camera3DWarpResult:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]

    depth_map = np.asarray(depth, dtype=np.float32)
    if depth_map.shape != (height, width):
        raise Camera3DError(
            f"Depth map shape {depth_map.shape!r} does not match image "
            f"{width}x{height}."
        )
    if not np.isfinite(depth_map).all():
        raise Camera3DError("Depth map contains non-finite values.")

    fov_value = float(fov)
    source_fov_value = float(source_fov if source_fov is not None else fov_value)
    if not 1.0 < fov_value < 179.0:
        raise Camera3DError("3D field of view must be between 1 and 179 degrees.")
    if not 1.0 < source_fov_value < 179.0:
        raise Camera3DError("3D source field of view must be between 1 and 179 degrees.")
    if not 0.0 < near_depth < far_depth:
        raise Camera3DError("3D pseudo-depth range must satisfy 0 < near < far.")

    normalized = np.clip(depth_map, 0.0, 1.0).astype(np.float32, copy=False)
    z = near_depth + (1.0 - normalized) * (far_depth - near_depth)

    source_focal = (width * 0.5) / math.tan(math.radians(source_fov_value) * 0.5)
    target_focal = (width * 0.5) / math.tan(math.radians(fov_value) * 0.5)
    cx = (width - 1.0) * 0.5
    cy = (height - 1.0) * 0.5

    yy, xx = np.indices((height, width), dtype=np.float32)
    x = (xx - cx) * z / source_focal
    y = (yy - cy) * z / source_focal

    points = np.stack((x, y, z), axis=-1).reshape(-1, 3)
    camera_translation = np.array(
        [float(translation_x), float(translation_y), float(translation_z)],
        dtype=np.float32,
    )

    # Camera motion is the inverse transform of the scene in camera coordinates.
    rotation = _rotation_matrix(rotation_x, rotation_y, rotation_z)
    transformed = (points - camera_translation) @ rotation

    z2 = transformed[:, 2]
    visible = z2 > 1e-4
    x2 = transformed[:, 0]
    y2 = transformed[:, 1]

    projected_x = np.rint(
        (target_focal * x2 / np.maximum(z2, 1e-6)) + cx
    ).astype(np.int64)
    projected_y = np.rint(
        (target_focal * y2 / np.maximum(z2, 1e-6)) + cy
    ).astype(np.int64)

    visible &= projected_x >= 0
    visible &= projected_x < width
    visible &= projected_y >= 0
    visible &= projected_y < height

    source_indices = np.nonzero(visible)[0]
    if source_indices.size == 0:
        raise Camera3DError("3D camera projection produced no visible pixels.")

    destination_indices = (
        projected_y[source_indices] * width + projected_x[source_indices]
    )
    source_depths = z2[source_indices]

    # Nearest projected sample wins each destination pixel.
    order = np.argsort(source_depths, kind="stable")
    destination_sorted = destination_indices[order]
    source_sorted = source_indices[order]
    _, first = np.unique(destination_sorted, return_index=True)
    selected_source = source_sorted[first]
    selected_destination = destination_sorted[first]

    output = np.zeros_like(rgb)
    valid_mask = np.zeros((height, width), dtype=bool)
    flat_output = output.reshape(-1, 3)
    flat_valid = valid_mask.reshape(-1)
    flat_source = rgb.reshape(-1, 3)
    flat_output[selected_destination] = flat_source[selected_source]
    flat_valid[selected_destination] = True

    projected_coverage = float(valid_mask.mean())
    filled = _fill_holes_nearest(output, valid_mask)

    telemetry = {
        "translation_x": float(translation_x),
        "translation_y": float(translation_y),
        "translation_z": float(translation_z),
        "rotation_x": float(rotation_x),
        "rotation_y": float(rotation_y),
        "rotation_z": float(rotation_z),
        "source_fov": source_fov_value,
        "fov": fov_value,
        "pseudo_depth_near": float(near_depth),
        "pseudo_depth_far": float(far_depth),
        "projected_coverage": projected_coverage,
        "filled_fraction": float(1.0 - projected_coverage),
        "visible_source_fraction": float(source_indices.size / (width * height)),
        "warp": "depth-forward-zbuffer-nearest-fill",
    }
    return Camera3DWarpResult(
        image=Image.fromarray(filled, mode="RGB"),
        telemetry=telemetry,
    )

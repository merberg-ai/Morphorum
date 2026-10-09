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
    hole_mask: Image.Image | None = None


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


def _fill_holes_background(
    image: np.ndarray,
    valid: np.ndarray,
    zbuffer: np.ndarray,
) -> np.ndarray:
    """Fill disocclusions preferentially from the farthest projected layer.

    A depth quantile is an approximation, not an inpainting model. Preserve
    the original visibility mask so downstream repair can target these pixels.
    """
    if valid.all():
        return image
    if not valid.any():
        raise Camera3DError("3D camera projection produced no visible pixels.")
    depths = zbuffer[valid]
    far_layer = valid & (zbuffer >= float(np.quantile(depths, 0.65)))
    if not far_layer.any():
        return _fill_holes_nearest(image, valid)
    missing = ~valid
    _, indices = ndimage.distance_transform_edt(
        ~far_layer, return_distances=True, return_indices=True,
    )
    output = image.copy()
    output[missing] = image[indices[0][missing], indices[1][missing]]
    return output


def _render_splat(
    rgb: np.ndarray,
    px: np.ndarray,
    py: np.ndarray,
    z2: np.ndarray,
    visible: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Subpixel bilinear splat, depth-tested before accumulating colors.

    A destination receives weighted contributions from up to four nearby
    source pixels, but only if their depth matches its nearest depth layer.
    This prevents back-layer colors bleeding through foreground objects.
    """
    height, width = rgb.shape[:2]
    source_indices = np.flatnonzero(visible)
    if source_indices.size == 0:
        raise Camera3DError("3D camera projection produced no visible pixels.")
    x = px[source_indices]
    y = py[source_indices]
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = x - x0
    fy = y - y0

    destinations = []
    sources = []
    weights = []
    for dx, dy, w in (
        (0, 0, (1.0 - fx) * (1.0 - fy)),
        (1, 0, fx * (1.0 - fy)),
        (0, 1, (1.0 - fx) * fy),
        (1, 1, fx * fy),
    ):
        cx = x0 + dx
        cy = y0 + dy
        active = (
            (w > 1e-6)
            & (cx >= 0) & (cx < width)
            & (cy >= 0) & (cy < height)
        )
        if not np.any(active):
            continue
        destinations.append(cy[active] * width + cx[active])
        sources.append(source_indices[active])
        weights.append(w[active])

    if not destinations:
        raise Camera3DError("3D camera projection produced no visible pixels.")

    dest = np.concatenate(destinations)
    src = np.concatenate(sources)
    weight = np.concatenate(weights).astype(np.float64)
    source_depth = z2[src]
    flat_z = np.full(height * width, np.inf, dtype=np.float32)
    np.minimum.at(flat_z, dest, source_depth)

    # A tight depth shell prevents far surfaces appearing through foreground
    # pixels while permitting smoothly varying surfaces to share a splat.
    front = source_depth <= flat_z[dest] + 0.02
    dest = dest[front]
    src = src[front]
    weight = weight[front]

    total_weight = np.bincount(
        dest, weights=weight, minlength=height * width,
    )
    valid_mask = total_weight.reshape(height, width) > 1e-8
    if not valid_mask.any():
        raise Camera3DError("3D camera projection produced no visible pixels.")

    flat_src = rgb.reshape(-1, 3)
    result = np.zeros((height * width, 3), dtype=np.uint8)
    for channel in range(3):
        weighted_color = np.bincount(
            dest,
            weights=weight * flat_src[src, channel],
            minlength=height * width,
        )
        active = total_weight > 1e-8
        result[active, channel] = np.clip(
            np.rint(weighted_color[active] / total_weight[active]),
            0, 255,
        ).astype(np.uint8)
    return result.reshape(height, width, 3), valid_mask, flat_z.reshape(height, width)


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
    projection_mode: str = "legacy",
    fill_mode: str = "nearest",
    transform_matrix: np.ndarray | None = None,
    transform_offset: np.ndarray | None = None,
) -> Camera3DWarpResult:
    if projection_mode not in {"legacy", "splat"}:
        raise Camera3DError(f"Unsupported 3D projection mode: {projection_mode}.")
    if fill_mode not in {"nearest", "background"}:
        raise Camera3DError(f"Unsupported 3D hole fill mode: {fill_mode}.")
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

    # B5.2 supplies a composed inverse camera transform to align a future
    # diffusion anchor with an earlier cadence frame, without re-estimating
    # depth at each intermediate frame. Default forward motion stays unchanged.
    if transform_matrix is None and transform_offset is None:
        rotation = _rotation_matrix(rotation_x, rotation_y, rotation_z)
        transformed = (points - camera_translation) @ rotation
    else:
        if transform_matrix is None or transform_offset is None:
            raise Camera3DError("3D camera reprojection needs both matrix and offset.")
        matrix = np.asarray(transform_matrix, dtype=np.float32)
        offset = np.asarray(transform_offset, dtype=np.float32)
        if (matrix.shape != (3, 3) or offset.shape != (3,)
                or not np.isfinite(matrix).all() or not np.isfinite(offset).all()):
            raise Camera3DError("3D camera reprojection transform must be finite 3x3/3.")
        transformed = points @ matrix + offset

    z2 = transformed[:, 2]
    visible = z2 > 1e-4
    x2 = transformed[:, 0]
    y2 = transformed[:, 1]

    projected_x_float = (target_focal * x2 / np.maximum(z2, 1e-6)) + cx
    projected_y_float = (target_focal * y2 / np.maximum(z2, 1e-6)) + cy

    if projection_mode == "legacy":
        # Keep the original exact nearest-sample Z-buffer implementation for
        # existing projects and A/B image comparisons.
        projected_x = np.rint(projected_x_float).astype(np.int64)
        projected_y = np.rint(projected_y_float).astype(np.int64)
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
        filled = _fill_holes_nearest(output, valid_mask)
        effective_fill = "nearest"
    else:
        # Include source samples whose subpixel footprints touch the canvas.
        visible &= projected_x_float > -1.0
        visible &= projected_x_float < width
        visible &= projected_y_float > -1.0
        visible &= projected_y_float < height
        source_indices = np.flatnonzero(visible)
        output, valid_mask, zbuffer = _render_splat(
            rgb, projected_x_float, projected_y_float, z2, visible,
        )
        if fill_mode == "background":
            filled = _fill_holes_background(output, valid_mask, zbuffer)
        else:
            filled = _fill_holes_nearest(output, valid_mask)
        effective_fill = fill_mode

    projected_coverage = float(valid_mask.mean())
    # White marks pixels not explained by the projection. The filled preview
    # remains RGB for img2img compatibility; this independent mask preserves
    # real disocclusions for future inpainting and quality diagnostics.
    mask = Image.fromarray((~valid_mask).astype(np.uint8) * 255, mode="L")

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
        "warp": (
            "depth-forward-zbuffer-nearest-fill" if projection_mode == "legacy"
            else f"depth-bilinear-zbuffer-{effective_fill}-fill"
        ),
        "projection_mode": projection_mode,
        "fill_mode": effective_fill,
        "disoccluded_pixels": int(np.count_nonzero(~valid_mask)),
        "visible_pixels": int(np.count_nonzero(valid_mask)),
    }
    return Camera3DWarpResult(
        image=Image.fromarray(filled, mode="RGB"),
        telemetry=telemetry,
        hole_mask=mask,
    )


def reverse_camera_chain(
    steps: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    """Map points in a future anchor's camera frame back into a past frame.

    Each recorded forward step is `(p - translation) @ rotation`.
    Its reverse is `p @ rotation.T + translation`; row-vector transforms
    accumulate in reverse frame order. Source/target focal lengths are handled
    separately by render_depth_warp rather than folded into this transform.
    """
    orientation = np.eye(3, dtype=np.float64)
    offset = np.zeros(3, dtype=np.float64)
    for camera in reversed(steps):
        rotation = _rotation_matrix(
            float(camera.get("rotation_x", 0.0)),
            float(camera.get("rotation_y", 0.0)),
            float(camera.get("rotation_z", 0.0)),
        ).astype(np.float64)
        reverse_rotation = rotation.T
        translation = np.asarray([
            float(camera.get("translation_x", 0.0)),
            float(camera.get("translation_y", 0.0)),
            float(camera.get("translation_z", 0.0)),
        ], dtype=np.float64)
        if not np.isfinite(translation).all():
            raise Camera3DError("3D camera reverse transform contains non-finite motion.")
        offset = offset @ reverse_rotation + translation
        orientation = orientation @ reverse_rotation
    return orientation.astype(np.float32), offset.astype(np.float32)

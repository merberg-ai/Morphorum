from __future__ import annotations

import io
import math
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from scipy.ndimage import map_coordinates

from .animation_resolution import resolve_project_frame
from .animation_3d import Camera3DError, render_depth_warp
from .animation_depth import DepthError, depth_manager
from .console import emit_console
from .paths import OUTPUTS_DIR

PREVIEW_MAX_DIMENSION = 512
PREVIEW_MAX_CAPTURE_FRAMES = 72
SOURCE_MAX_BYTES = 32 * 1024 * 1024
SUPPORTED_BORDER_MODES = {"replicate", "wrap"}


class MotionPreviewError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_border_mode(value: Any) -> str:
    mode = str(value or "replicate").strip().lower()
    if mode not in SUPPORTED_BORDER_MODES:
        raise MotionPreviewError(
            f"Unsupported 2D border mode '{mode}'. Use replicate or wrap."
        )
    return mode


def validate_source_image_bytes(data: bytes) -> Image.Image:
    if not data:
        raise MotionPreviewError("The uploaded source image is empty.")
    if len(data) > SOURCE_MAX_BYTES:
        raise MotionPreviewError(
            f"Source image exceeds the {SOURCE_MAX_BYTES // (1024 * 1024)} MiB upload limit."
        )

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            return ImageOps.exif_transpose(image).convert("RGB").copy()
    except Exception as exc:
        raise MotionPreviewError(f"Could not decode source image: {exc}") from exc


def save_source_image(data: bytes, destination: Path) -> dict[str, Any]:
    image = validate_source_image_bytes(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    image.save(temp, format="PNG", optimize=True)
    temp.replace(destination)
    return {
        "path": str(destination),
        "width": image.width,
        "height": image.height,
        "bytes": destination.stat().st_size,
    }


def _preview_dimensions(
    width: int,
    height: int,
    max_dimension: int = PREVIEW_MAX_DIMENSION,
) -> tuple[int, int]:
    width = max(1, int(width))
    height = max(1, int(height))
    maximum = max(width, height)
    if maximum <= max_dimension:
        return width, height
    scale = max_dimension / maximum
    preview_width = max(2, int(round(width * scale)))
    preview_height = max(2, int(round(height * scale)))
    return preview_width, preview_height


def prepare_preview_source(
    source: Image.Image,
    *,
    width: int,
    height: int,
    max_dimension: int = PREVIEW_MAX_DIMENSION,
) -> Image.Image:
    preview_width, preview_height = _preview_dimensions(width, height, max_dimension)
    return ImageOps.fit(
        source.convert("RGB"),
        (preview_width, preview_height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def _frame_transform_matrix(
    *,
    width: int,
    height: int,
    angle: float,
    zoom: float,
    translation_x: float,
    translation_y: float,
) -> np.ndarray:
    zoom = float(zoom)
    if not math.isfinite(zoom) or zoom <= 0:
        raise MotionPreviewError(f"Zoom must be greater than zero; got {zoom!r}.")

    angle = float(angle)
    translation_x = float(translation_x)
    translation_y = float(translation_y)
    if not all(math.isfinite(value) for value in (angle, translation_x, translation_y)):
        raise MotionPreviewError("2D motion values must be finite numbers.")

    radians = math.radians(angle)
    cosine = math.cos(radians) * zoom
    sine = math.sin(radians) * zoom
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0

    translate_to_origin = np.array(
        [[1.0, 0.0, -center_x], [0.0, 1.0, -center_y], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    rotate_scale = np.array(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    translate_back = np.array(
        [
            [1.0, 0.0, center_x + translation_x],
            [0.0, 1.0, center_y + translation_y],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    return translate_back @ rotate_scale @ translate_to_origin


def render_affine(
    source: Image.Image,
    matrix: np.ndarray,
    *,
    border_mode: str,
) -> Image.Image:
    border_mode = _validate_border_mode(border_mode)
    image = np.asarray(source.convert("RGB"), dtype=np.float32)
    height, width, _channels = image.shape

    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise MotionPreviewError("2D transform matrix is not invertible.") from exc

    yy, xx = np.indices((height, width), dtype=np.float64)
    homogeneous = np.stack(
        [xx.ravel(), yy.ravel(), np.ones(width * height, dtype=np.float64)],
        axis=0,
    )
    mapped = inverse @ homogeneous
    source_x = mapped[0].reshape(height, width)
    source_y = mapped[1].reshape(height, width)

    scipy_mode = "nearest" if border_mode == "replicate" else "grid-wrap"
    rendered = np.empty_like(image)
    coordinates = np.stack([source_y, source_x], axis=0)
    for channel in range(3):
        rendered[..., channel] = map_coordinates(
            image[..., channel],
            coordinates,
            order=1,
            mode=scipy_mode,
            prefilter=False,
        )

    return Image.fromarray(np.clip(rendered, 0, 255).astype(np.uint8), mode="RGB")


def capture_frames(max_frames: int, maximum: int = PREVIEW_MAX_CAPTURE_FRAMES) -> list[int]:
    max_frames = max(1, int(max_frames))
    maximum = max(2, int(maximum))
    if max_frames <= maximum:
        return list(range(max_frames))

    last = max_frames - 1
    frames = {
        int(round(index * last / (maximum - 1)))
        for index in range(maximum)
    }
    frames.add(0)
    frames.add(last)
    return sorted(frames)


def _render_3d_motion_preview(
    project: dict[str, Any],
    source: Image.Image,
    destination: Path,
    *,
    max_dimension: int,
    max_capture_frames: int,
    progress_callback=None,
    highlight_holes: bool = False,
) -> dict[str, Any]:
    """B5.3: simulate the actual sequential depth camera path without diffusion.

    Depth inference runs entirely on CPU, with cached 320px (or smaller)
    input frames; there is no diffusion or GPU model allocation.
    """
    animation = project.get("animation", {})
    max_frames = max(1, int(animation.get("max_frames", 120)))
    if max_frames > 180:
        raise MotionPreviewError(
            "3D camera preview supports up to 180 frames. "
            "Reduce the frame count to preview the camera movement."
        )
    fps = max(1.0, float(animation.get("fps", 24.0)))
    base = prepare_preview_source(
        source,
        width=int(animation.get("width", source.width)),
        height=int(animation.get("height", source.height)),
        max_dimension=max_dimension,
    )
    current = base
    wanted = set(capture_frames(max_frames, max_capture_frames))
    captured: list[tuple[int, Image.Image]] = [(0, base.copy())]
    coverage: list[dict[str, Any]] = [
        {"frame": 0, "projected_coverage": 1.0, "filled_fraction": 0.0},
    ]
    previous_fov = float(
        resolve_project_frame(project, 0)["camera_3d"]["fov"]
    )
    try:
        for frame in range(1, max_frames):
            camera = resolve_project_frame(project, frame)["camera_3d"]
            estimation = depth_manager.estimate(
                current,
                device="cpu",
                release_after=False,
            )
            depth = depth_manager.load_cached_array(str(estimation["cache_key"]))
            if depth.shape != (current.height, current.width):
                resized = Image.fromarray(np.asarray(depth, dtype=np.float32), mode="F")
                depth = np.asarray(
                    resized.resize(current.size, Image.Resampling.BILINEAR),
                    dtype=np.float32,
                )
            warped = render_depth_warp(
                current,
                depth,
                translation_x=float(camera["translation_x"]),
                translation_y=float(camera["translation_y"]),
                translation_z=float(camera["translation_z"]),
                rotation_x=float(camera["rotation_x"]),
                rotation_y=float(camera["rotation_y"]),
                rotation_z=float(camera["rotation_z"]),
                source_fov=previous_fov,
                fov=float(camera["fov"]),
                projection_mode=str(camera.get("projection_mode") or "legacy"),
                fill_mode=str(camera.get("hole_fill") or "nearest"),
            )
            previous_fov = float(camera["fov"])
            # The preview's next step must use the true RGB projection,
            # never the optional red mask overlay.
            current = warped.image
            coverage.append({
                "frame": frame,
                "projected_coverage": warped.telemetry["projected_coverage"],
                "filled_fraction": warped.telemetry["filled_fraction"],
            })
            if frame in wanted:
                preview_frame = current.copy()
                if highlight_holes and warped.hole_mask is not None:
                    rgb = np.asarray(preview_frame, dtype=np.float32).copy()
                    holes = np.asarray(warped.hole_mask, dtype=np.uint8) > 0
                    rgb[holes] = rgb[holes] * 0.35 + np.array(
                        [255.0, 32.0, 52.0], dtype=np.float32,
                    ) * 0.65
                    preview_frame = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
                captured.append((frame, preview_frame))
            if progress_callback is not None:
                progress_callback(frame, max_frames - 1)
    except (DepthError, Camera3DError) as exc:
        raise MotionPreviewError(f"3D camera preview failed at frame {frame}: {exc}") from exc
    finally:
        depth_manager.unload()

    _save_motion_preview_gif(captured, destination, fps)
    counts = [float(item["projected_coverage"]) for item in coverage]
    worst = min(coverage, key=lambda item: item["projected_coverage"])
    return {
        "mode": "3d",
        "depth_device": "cpu",
        "preview_width": base.width,
        "preview_height": base.height,
        "source_frames": max_frames,
        "captured_frames": len(captured),
        "captured_frame_numbers": [frame for frame, _ in captured],
        "fps": fps,
        "duration_seconds": max_frames / fps,
        "bytes": destination.stat().st_size,
        "highlight_holes": bool(highlight_holes),
        "average_coverage": sum(counts) / len(counts),
        "minimum_coverage": float(worst["projected_coverage"]),
        "worst_coverage_frame": int(worst["frame"]),
        "last_coverage": counts[-1],
        "per_frame_coverage": coverage,
    }


def _save_motion_preview_gif(
    captured: list[tuple[int, Image.Image]],
    destination: Path,
    fps: float,
) -> None:
    durations: list[int] = []
    for index, (frame, _image) in enumerate(captured):
        if index + 1 < len(captured):
            delta = max(1, captured[index + 1][0] - frame)
        elif index:
            delta = max(1, frame - captured[index - 1][0])
        else:
            delta = 1
        durations.append(max(20, int(round(1000.0 * delta / fps))))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    captured[0][1].save(
        temp,
        format="GIF",
        save_all=True,
        append_images=[image for _frame, image in captured[1:]],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=2,
    )
    temp.replace(destination)


def render_motion_preview(
    project: dict[str, Any],
    source: Image.Image,
    destination: Path,
    *,
    max_dimension: int | None = None,
    max_capture_frames: int | None = None,
    progress_callback=None,
    highlight_holes: bool = False,
) -> dict[str, Any]:
    if max_dimension is None:
        max_dimension = PREVIEW_MAX_DIMENSION
    if max_capture_frames is None:
        max_capture_frames = PREVIEW_MAX_CAPTURE_FRAMES

    animation = project.get("animation", {})
    motion = project.get("motion", {})
    max_frames = max(1, int(animation.get("max_frames", 120)))
    fps = max(1.0, float(animation.get("fps", 24.0)))
    project_width = max(1, int(animation.get("width", source.width)))
    project_height = max(1, int(animation.get("height", source.height)))
    border_mode = _validate_border_mode(motion.get("border_mode", "replicate"))

    base = prepare_preview_source(
        source,
        width=project_width,
        height=project_height,
        max_dimension=max_dimension,
    )
    preview_width, preview_height = base.size
    if str(animation.get("mode") or "2d").strip().lower() == "3d":
        return _render_3d_motion_preview(
            project, source, destination,
            max_dimension=min(int(max_dimension), 320),
            max_capture_frames=int(max_capture_frames),
            progress_callback=progress_callback,
            highlight_holes=highlight_holes,
        )
    scale_x = preview_width / project_width
    scale_y = preview_height / project_height

    wanted = capture_frames(max_frames, max_capture_frames)
    wanted_set = set(wanted)
    captured: list[tuple[int, Image.Image]] = []
    cumulative = np.eye(3, dtype=np.float64)

    if 0 in wanted_set:
        captured.append((0, base.copy()))

    for frame in range(1, max_frames):
        resolved = resolve_project_frame(project, frame)
        frame_motion = resolved["motion"]
        step = _frame_transform_matrix(
            width=preview_width,
            height=preview_height,
            angle=float(frame_motion["angle"]),
            zoom=float(frame_motion["zoom"]),
            translation_x=float(frame_motion["translation_x"]) * scale_x,
            translation_y=float(frame_motion["translation_y"]) * scale_y,
        )
        cumulative = step @ cumulative

        if frame in wanted_set:
            rendered = render_affine(base, cumulative, border_mode=border_mode)
            captured.append((frame, rendered))

        if progress_callback is not None:
            progress_callback(frame, max_frames - 1)

    if not captured:
        captured.append((0, base.copy()))

    durations: list[int] = []
    for index, (frame, _image) in enumerate(captured):
        if index + 1 < len(captured):
            next_frame = captured[index + 1][0]
            delta = max(1, next_frame - frame)
        elif index > 0:
            delta = max(1, frame - captured[index - 1][0])
        else:
            delta = 1
        durations.append(max(20, int(round(1000.0 * delta / fps))))

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    frames = [image for _frame, image in captured]
    frames[0].save(
        temp,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=2,
    )
    temp.replace(destination)

    return {
        "preview_width": preview_width,
        "preview_height": preview_height,
        "source_frames": max_frames,
        "captured_frames": len(captured),
        "captured_frame_numbers": [frame for frame, _image in captured],
        "fps": fps,
        "border_mode": border_mode,
        "duration_seconds": max_frames / fps,
        "bytes": destination.stat().st_size,
    }


@dataclass
class MotionPreviewJob:
    id: str
    project_id: str
    created_at: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued motion preview"
    error: str | None = None
    result: dict[str, Any] | None = None
    completed_at: str | None = None

    def public(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "result": deepcopy(self.result),
            "completed_at": self.completed_at,
        }
        if self.status == "completed":
            payload["url"] = f"/api/animation/motion-preview/{self.id}/image"
        return payload


class MotionPreviewManager:
    def __init__(self) -> None:
        self._jobs: dict[str, MotionPreviewJob] = {}
        self._lock = threading.RLock()
        self._render_lock = threading.Lock()

    def start(
        self,
        *,
        project: dict[str, Any],
        source_path: Path,
        highlight_holes: bool = False,
    ) -> dict[str, Any]:
        project_id = str(project.get("id") or "").strip()
        if not project_id:
            raise MotionPreviewError("Animation project id is required.")
        if not source_path.is_file():
            raise MotionPreviewError("Upload a source image before creating a motion preview.")
        if (
            str(project.get("animation", {}).get("mode") or "2d").strip().lower() == "3d"
            and int(project.get("animation", {}).get("max_frames", 120)) > 180
        ):
            raise MotionPreviewError(
                "3D camera previews support up to 180 frames. "
                "Shorten the project for this diagnostic preview."
            )

        job = MotionPreviewJob(
            id=f"motion-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            created_at=_utc_now(),
        )
        with self._lock:
            self._jobs[job.id] = job

        thread = threading.Thread(
            target=self._run,
            args=(job.id, deepcopy(project), source_path, highlight_holes),
            daemon=True,
            name=f"Morphorum-{job.id}",
        )
        thread.start()
        emit_console("info", "animation", f"Queued motion preview {job.id} for {project_id}.")
        return job.public()

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise MotionPreviewError("Motion preview job not found.")
            return job.public()

    def result_path(self, job_id: str) -> Path:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise MotionPreviewError("Motion preview job not found.")
            if job.status != "completed":
                raise MotionPreviewError("Motion preview is not complete.")
        return OUTPUTS_DIR / "motion-previews" / job_id / "preview.gif"

    def _run(
        self,
        job_id: str,
        project: dict[str, Any],
        source_path: Path,
        highlight_holes: bool = False,
    ) -> None:
        with self._render_lock:
            self._run_serialized(job_id, project, source_path, highlight_holes)

    def _run_serialized(
        self,
        job_id: str,
        project: dict[str, Any],
        source_path: Path,
        highlight_holes: bool = False,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "rendering"
            job.message = "Preparing source image"

        try:
            with Image.open(source_path) as opened:
                source = ImageOps.exif_transpose(opened).convert("RGB").copy()

            output = OUTPUTS_DIR / "motion-previews" / job_id / "preview.gif"

            is3d = str(project.get("animation", {}).get("mode") or "2d") == "3d"

            def progress(frame: int, last_frame: int) -> None:
                with self._lock:
                    active = self._jobs[job_id]
                    active.progress = min(0.98, frame / max(1, last_frame))
                    active.message = (
                        f"Resolving {'3D camera' if is3d else '2D motion'} "
                        f"frame {frame} of {last_frame}"
                    )

            result = render_motion_preview(
                project,
                source,
                output,
                progress_callback=progress,
                highlight_holes=highlight_holes,
            )
            with self._lock:
                job = self._jobs[job_id]
                job.status = "completed"
                job.progress = 1.0
                job.message = "Motion preview complete"
                job.result = result
                job.completed_at = _utc_now()
            emit_console(
                "info",
                "animation",
                f"Motion preview {job_id} complete: "
                f"{result['captured_frames']} preview frames from {result['source_frames']} project frames.",
            )
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.progress = 1.0
                job.message = "Motion preview failed"
                job.error = str(exc)
                job.completed_at = _utc_now()
            emit_console("error", "animation", f"Motion preview {job_id} failed: {exc}")


motion_preview_manager = MotionPreviewManager()

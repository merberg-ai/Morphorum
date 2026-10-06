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


def render_motion_preview(
    project: dict[str, Any],
    source: Image.Image,
    destination: Path,
    *,
    max_dimension: int | None = None,
    max_capture_frames: int | None = None,
    progress_callback=None,
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
    ) -> dict[str, Any]:
        project_id = str(project.get("id") or "").strip()
        if not project_id:
            raise MotionPreviewError("Animation project id is required.")
        if not source_path.is_file():
            raise MotionPreviewError("Upload a source image before creating a motion preview.")

        job = MotionPreviewJob(
            id=f"motion-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            created_at=_utc_now(),
        )
        with self._lock:
            self._jobs[job.id] = job

        thread = threading.Thread(
            target=self._run,
            args=(job.id, deepcopy(project), source_path),
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
    ) -> None:
        with self._render_lock:
            self._run_serialized(job_id, project, source_path)

    def _run_serialized(
        self,
        job_id: str,
        project: dict[str, Any],
        source_path: Path,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "rendering"
            job.message = "Preparing source image"

        try:
            with Image.open(source_path) as opened:
                source = ImageOps.exif_transpose(opened).convert("RGB").copy()

            output = OUTPUTS_DIR / "motion-previews" / job_id / "preview.gif"

            def progress(frame: int, last_frame: int) -> None:
                with self._lock:
                    active = self._jobs[job_id]
                    active.progress = min(0.98, frame / max(1, last_frame))
                    active.message = f"Resolving 2D motion frame {frame} of {last_frame}"

            result = render_motion_preview(
                project,
                source,
                output,
                progress_callback=progress,
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

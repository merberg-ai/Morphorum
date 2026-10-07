from __future__ import annotations

import gc
import json
import random
import shutil
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from PIL.PngImagePlugin import PngInfo

from .animation_motion import (
    _frame_transform_matrix,
    capture_frames,
    render_affine,
)
from .animation_resolution import resolve_project_frame, validate_project_schedules
from .console import emit_console
from .generation import GenerationError, GenerationRequest, generation_manager
from .model_index import get_model
from .paths import OUTPUTS_DIR

ANIMATION_RENDER_SCHEMA = 1
MAX_RENDER_FRAMES = 10_000
PREVIEW_MAX_DIMENSION = 512
PREVIEW_MAX_FRAMES = 72


class AnimationRenderError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _project_output_dir(project_id: str) -> Path:
    return OUTPUTS_DIR / "animations" / project_id


def _render_dir(project_id: str, render_id: str) -> Path:
    return _project_output_dir(project_id) / render_id


def _manifest_path(project_id: str, render_id: str) -> Path:
    return _render_dir(project_id, render_id) / "render-manifest.json"


def _frame_path(project_id: str, render_id: str, frame: int) -> Path:
    return _render_dir(project_id, render_id) / "frames" / f"frame_{frame:06d}.png"


def _safe_prompt_text(transition: dict[str, Any]) -> str:
    return str(transition.get("from_text") or transition.get("to_text") or "").strip()


def _blend_value(first: Any, second: Any, second_weight: float):
    if first is None:
        return second
    if second is None:
        return first

    weight = float(second_weight)
    if weight <= 0:
        return first
    if weight >= 1:
        return second

    try:
        import torch
    except Exception:
        torch = None

    if (
        torch is not None
        and isinstance(first, torch.Tensor)
        and isinstance(second, torch.Tensor)
    ):
        left = first
        right = second

        if left.shape != right.shape:
            if (
                left.ndim == 2
                and right.ndim == 2
                and left.shape[1] == right.shape[1]
            ):
                target = max(left.shape[0], right.shape[0])
                if left.shape[0] < target:
                    padded = left.new_zeros((target, left.shape[1]))
                    padded[: left.shape[0]] = left
                    left = padded
                if right.shape[0] < target:
                    padded = right.new_zeros((target, right.shape[1]))
                    padded[: right.shape[0]] = right
                    right = padded
            else:
                raise AnimationRenderError(
                    "Cannot blend prompt conditioning tensors with incompatible "
                    f"shapes {tuple(left.shape)} and {tuple(right.shape)}."
                )

        return left * (1.0 - weight) + right * weight

    if isinstance(first, list) and isinstance(second, list):
        if len(first) != len(second):
            raise AnimationRenderError("Prompt embedding lists have incompatible lengths.")
        return [
            _blend_value(left, right, weight)
            for left, right in zip(first, second)
        ]
    if isinstance(first, tuple) and isinstance(second, tuple):
        if len(first) != len(second):
            raise AnimationRenderError("Prompt embedding tuples have incompatible lengths.")
        return tuple(
            _blend_value(left, right, weight)
            for left, right in zip(first, second)
        )

    raise AnimationRenderError(
        f"Cannot blend prompt conditioning values of type "
        f"{type(first).__name__} and {type(second).__name__}."
    )


def _prompt_conditioning_kwargs(
    pipe: Any,
    family: str,
    positive: dict[str, Any],
    negative: dict[str, Any],
    *,
    guidance_scale: float,
    max_sequence_length: int = 512,
) -> dict[str, Any]:
    positive_to_weight = float(positive.get("to_weight") or 0.0)
    same_positive = (
        positive.get("from_frame") == positive.get("to_frame")
        or positive.get("from_text") == positive.get("to_text")
        or positive_to_weight <= 0.0
    )

    negative_to_weight = float(negative.get("to_weight") or 0.0)
    same_negative = (
        negative.get("from_frame") == negative.get("to_frame")
        or negative.get("from_text") == negative.get("to_text")
        or negative_to_weight <= 0.0
    )

    from_prompt = str(positive.get("from_text") or "")
    to_prompt = str(positive.get("to_text") or from_prompt)
    from_negative = str(negative.get("from_text") or "")
    to_negative = str(negative.get("to_text") or from_negative)

    if same_positive and (family != "sdxl" or same_negative):
        result: dict[str, Any] = {"prompt": from_prompt}
        if family == "sdxl":
            result["negative_prompt"] = from_negative or None
        return result

    try:
        if family == "sdxl":
            do_cfg = float(guidance_scale) > 1.0
            first = pipe.encode_prompt(
                prompt=from_prompt,
                negative_prompt=from_negative or None,
                num_images_per_prompt=1,
                do_classifier_free_guidance=do_cfg,
            )
            second = pipe.encode_prompt(
                prompt=to_prompt,
                negative_prompt=to_negative or None,
                num_images_per_prompt=1,
                do_classifier_free_guidance=do_cfg,
            )
            result = {
                "prompt": None,
                "negative_prompt": None,
                "prompt_embeds": _blend_value(
                    first[0], second[0], positive_to_weight
                ),
                "pooled_prompt_embeds": _blend_value(
                    first[2], second[2], positive_to_weight
                ),
            }
            if first[1] is not None or second[1] is not None:
                result["negative_prompt_embeds"] = _blend_value(
                    first[1], second[1], negative_to_weight
                )
            if first[3] is not None or second[3] is not None:
                result["negative_pooled_prompt_embeds"] = _blend_value(
                    first[3], second[3], negative_to_weight
                )
            return result

        if family == "flux":
            first = pipe.encode_prompt(
                prompt=from_prompt,
                num_images_per_prompt=1,
                max_sequence_length=max_sequence_length,
            )
            second = pipe.encode_prompt(
                prompt=to_prompt,
                num_images_per_prompt=1,
                max_sequence_length=max_sequence_length,
            )
            return {
                "prompt": None,
                "prompt_embeds": _blend_value(
                    first[0], second[0], positive_to_weight
                ),
                "pooled_prompt_embeds": _blend_value(
                    first[1], second[1], positive_to_weight
                ),
            }

        if family == "zimage":
            first = pipe.encode_prompt(
                prompt=from_prompt,
                do_classifier_free_guidance=False,
                max_sequence_length=max_sequence_length,
            )
            second = pipe.encode_prompt(
                prompt=to_prompt,
                do_classifier_free_guidance=False,
                max_sequence_length=max_sequence_length,
            )
            return {
                "prompt": None,
                "prompt_embeds": _blend_value(
                    first[0], second[0], positive_to_weight
                ),
            }
    except AnimationRenderError:
        raise
    except Exception as exc:
        raise AnimationRenderError(
            f"Could not build blended {family} prompt conditioning: {exc}"
        ) from exc

    raise AnimationRenderError(
        f"Prompt blending is not implemented for model family '{family}'."
    )


def _add_uniform_noise(
    image: Image.Image,
    *,
    amount: float,
    seed: int,
) -> Image.Image:
    amount = float(amount)
    if not 0.0 <= amount <= 1.0:
        raise AnimationRenderError(
            f"Noise amount must be between 0 and 1; got {amount:g}."
        )
    if amount <= 0:
        return image

    pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    rng = np.random.default_rng((int(seed) ^ 0xA5A5A5A5) % (2**32))
    noise = rng.uniform(
        low=-amount * 255.0,
        high=amount * 255.0,
        size=pixels.shape,
    ).astype(np.float32)
    return Image.fromarray(
        np.clip(pixels + noise, 0, 255).astype(np.uint8),
        mode="RGB",
    )


def _prepare_source(source: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(
        ImageOps.exif_transpose(source).convert("RGB"),
        (width, height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def _save_frame(
    image: Image.Image,
    path: Path,
    *,
    metadata: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pnginfo = PngInfo()
    pnginfo.add_text("Morphorum", json.dumps(metadata, ensure_ascii=False))
    temp = path.with_name(path.name + ".tmp")
    image.save(temp, format="PNG", pnginfo=pnginfo)
    temp.replace(path)


def _build_render_preview(
    project_id: str,
    render_id: str,
    *,
    total_frames: int,
    fps: float,
) -> dict[str, Any]:
    wanted = capture_frames(total_frames, PREVIEW_MAX_FRAMES)
    images: list[tuple[int, Image.Image]] = []

    for frame in wanted:
        path = _frame_path(project_id, render_id, frame)
        if not path.is_file():
            continue
        with Image.open(path) as opened:
            image = opened.convert("RGB").copy()
        maximum = max(image.size)
        if maximum > PREVIEW_MAX_DIMENSION:
            scale = PREVIEW_MAX_DIMENSION / maximum
            image = image.resize(
                (
                    max(2, int(round(image.width * scale))),
                    max(2, int(round(image.height * scale))),
                ),
                Image.Resampling.LANCZOS,
            )
        images.append((frame, image))

    if not images:
        raise AnimationRenderError("No rendered frames are available for preview.")

    durations: list[int] = []
    for index, (frame, _image) in enumerate(images):
        if index + 1 < len(images):
            delta = max(1, images[index + 1][0] - frame)
        elif index > 0:
            delta = max(1, frame - images[index - 1][0])
        else:
            delta = 1
        durations.append(max(20, int(round(1000.0 * delta / fps))))

    path = _render_dir(project_id, render_id) / "preview.gif"
    temp = path.with_name(path.name + ".tmp")
    first = images[0][1]
    first.save(
        temp,
        format="GIF",
        save_all=True,
        append_images=[image for _, image in images[1:]],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=2,
    )
    temp.replace(path)
    return {
        "path": str(path),
        "frames": len(images),
        "width": first.width,
        "height": first.height,
    }


@dataclass
class AnimationRenderJob:
    id: str
    project_id: str
    project: dict[str, Any]
    seed_plan: list[int]
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    status: str = "queued"
    message: str = "Queued animation render"
    current_frame: int = 0
    current_step: int = 0
    total_frames: int = 0
    progress: float = 0.0
    eta_seconds: float | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False
    model_load_seconds: float | None = None
    frame_seconds: float | None = None
    average_frame_seconds: float | None = None
    preview: dict[str, Any] | None = None
    resumed: bool = False
    _frame_times: list[float] = field(default_factory=list, repr=False)

    def public(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("_frame_times", None)
        payload.pop("project", None)
        payload.pop("seed_plan", None)
        latest_frame = (
            max(int(item.get("frame", -1)) for item in self.results)
            if self.results
            else None
        )
        payload["latest_completed_frame"] = latest_frame
        payload["latest_frame_url"] = (
            f"/api/animation/renders/{self.project_id}/{self.id}/frames/"
            f"{latest_frame}"
            if latest_frame is not None and latest_frame >= 0
            else None
        )
        payload["preview_url"] = (
            f"/api/animation/renders/{self.project_id}/{self.id}/preview"
            if self.preview
            else None
        )
        payload["resumable"] = self.status in {"failed", "cancelled", "interrupted"}
        return payload

    def manifest(self) -> dict[str, Any]:
        payload = self.public()
        payload["schema_version"] = ANIMATION_RENDER_SCHEMA
        payload["project"] = deepcopy(self.project)
        payload["seed_plan"] = list(self.seed_plan)
        return payload


class AnimationRenderManager:
    def __init__(self) -> None:
        self._jobs: dict[str, AnimationRenderJob] = {}
        self._lock = threading.RLock()
        self._queue: Queue[str] = Queue()
        self._worker: threading.Thread | None = None

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="morphorum-animation-render",
                daemon=True,
            )
            self._worker.start()

    def _resolve_seed_plan(self, project: dict[str, Any]) -> list[int]:
        total = int(project.get("animation", {}).get("max_frames", 0))
        seeds: list[int] = []
        rng = random.SystemRandom()
        for frame in range(total):
            resolved = resolve_project_frame(project, frame)
            seed = resolved.get("generation", {}).get("seed", {})
            value = seed.get("resolved")
            if value is None:
                value = rng.randint(0, 2**32 - 1)
            seeds.append(int(value) % (2**32))
        return seeds

    def _validate_project(
        self,
        project: dict[str, Any],
        source_path: Path,
    ) -> dict[str, Any]:
        total_frames = int(project.get("animation", {}).get("max_frames", 0))
        if not 1 <= total_frames <= MAX_RENDER_FRAMES:
            raise AnimationRenderError(
                f"Animation renders support 1 to {MAX_RENDER_FRAMES} frames."
            )
        start_mode = str(
            project.get("animation", {}).get("start_mode", "prompt")
            or "prompt"
        ).strip().lower()
        if start_mode not in {"prompt", "source"}:
            raise AnimationRenderError(
                f"Unknown animation start mode '{start_mode}'."
            )
        if start_mode == "source" and not source_path.is_file():
            raise AnimationRenderError(
                "Start Mode is 'Use starting image', but no starting image is uploaded."
            )

        validation = validate_project_schedules(project)
        if not validation["valid"]:
            first = next(
                issue for issue in validation["issues"]
                if issue["severity"] == "error"
            )
            raise AnimationRenderError(
                f"Invalid schedule {first['field']}: {first['message']}"
            )

        model_id = str(project.get("model", {}).get("model_id") or "").strip()
        model = get_model(model_id)
        if not model:
            raise AnimationRenderError(
                "The animation model is missing from the model index."
            )
        return model

    def submit(
        self,
        *,
        project: dict[str, Any],
        source_path: Path,
    ) -> dict[str, Any]:
        model = self._validate_project(project, source_path)
        render_id = (
            f"anim-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:6]}"
        )
        project_id = str(project["id"])
        output_dir = _render_dir(project_id, render_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        copied_source = output_dir / "source.png"
        if source_path.is_file():
            shutil.copy2(source_path, copied_source)

        seed_plan = self._resolve_seed_plan(project)
        job = AnimationRenderJob(
            id=render_id,
            project_id=project_id,
            project=deepcopy(project),
            seed_plan=seed_plan,
            total_frames=int(project["animation"]["max_frames"]),
        )
        job.project.setdefault("_render_model_snapshot", deepcopy(model))
        with self._lock:
            self._jobs[render_id] = job
        self._write_manifest(job)
        self._queue.put(render_id)
        self._ensure_worker()
        emit_console(
            "info",
            "animation",
            f"Queued animation render {render_id}: "
            f"{job.total_frames} frame(s) with {model['name']}.",
        )
        return job.public()

    def get(self, render_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(render_id)
            if job is not None:
                return job.public()

        manifest = self._find_manifest(render_id)
        if manifest is None:
            raise AnimationRenderError("Animation render not found.")
        return self._public_from_manifest(manifest)

    def cancel(self, render_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(render_id)
            if job is None:
                raise AnimationRenderError("Animation render is not active.")
            if job.status not in {"queued", "loading_model", "rendering", "finalizing"}:
                return job.public()
            job.cancel_requested = True
            job.message = "Cancellation requested"
            return job.public()

    def resume(self, project_id: str, render_id: str) -> dict[str, Any]:
        with self._lock:
            active = self._jobs.get(render_id)
            if active and active.status in {
                "queued",
                "loading_model",
                "rendering",
                "finalizing",
            }:
                raise AnimationRenderError("Animation render is already active.")

        manifest_path = _manifest_path(project_id, render_id)
        if not manifest_path.is_file():
            raise AnimationRenderError("Animation render manifest not found.")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AnimationRenderError(
                f"Could not read animation render manifest: {exc}"
            ) from exc

        status = str(payload.get("status") or "")
        if status == "completed":
            raise AnimationRenderError("Completed animation renders do not need resume.")

        project = payload.get("project")
        seed_plan = payload.get("seed_plan")
        if not isinstance(project, dict) or not isinstance(seed_plan, list):
            raise AnimationRenderError(
                "Animation render manifest is missing its project snapshot or seed plan."
            )

        results = [
            item for item in payload.get("results", [])
            if isinstance(item, dict)
            and _frame_path(
                project_id,
                render_id,
                int(item.get("frame", -1)),
            ).is_file()
        ]
        results.sort(key=lambda item: int(item.get("frame", -1)))

        job = AnimationRenderJob(
            id=render_id,
            project_id=project_id,
            project=project,
            seed_plan=[int(value) for value in seed_plan],
            created_at=str(payload.get("created_at") or _utc_now()),
            status="queued",
            message="Queued animation render resume",
            current_frame=int(results[-1]["frame"]) if results else 0,
            total_frames=int(payload.get("total_frames") or project["animation"]["max_frames"]),
            progress=(len(results) / max(1, int(payload.get("total_frames") or 1))),
            results=results,
            resumed=True,
        )
        with self._lock:
            self._jobs[render_id] = job
        self._write_manifest(job)
        self._queue.put(render_id)
        self._ensure_worker()
        emit_console(
            "info",
            "animation",
            f"Queued resume for animation render {render_id} at frame "
            f"{job.current_frame + 1 if results else 0}.",
        )
        return job.public()

    def frame_path(
        self,
        project_id: str,
        render_id: str,
        frame: int,
    ) -> Path:
        path = _frame_path(project_id, render_id, frame)
        if not path.is_file():
            raise AnimationRenderError("Rendered animation frame not found.")
        return path

    def preview_path(self, project_id: str, render_id: str) -> Path:
        path = _render_dir(project_id, render_id) / "preview.gif"
        if not path.is_file():
            raise AnimationRenderError("Animation preview is not available.")
        return path

    def list_project(self, project_id: str) -> list[dict[str, Any]]:
        root = _project_output_dir(project_id)
        if not root.is_dir():
            return []
        renders: list[dict[str, Any]] = []
        for directory in root.iterdir():
            with self._lock:
                active = self._jobs.get(directory.name)
            if active is not None:
                renders.append(active.public())
                continue

            path = directory / "render-manifest.json"
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            renders.append(self._public_from_manifest(payload))
        renders.sort(
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )
        return renders

    def _find_manifest(self, render_id: str) -> dict[str, Any] | None:
        root = OUTPUTS_DIR / "animations"
        if not root.is_dir():
            return None
        for project_dir in root.iterdir():
            path = project_dir / render_id / "render-manifest.json"
            if not path.is_file():
                continue
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    @staticmethod
    def _public_from_manifest(payload: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: deepcopy(value)
            for key, value in payload.items()
            if key not in {"project", "seed_plan", "schema_version"}
        }
        results = [
            item for item in public.get("results", [])
            if isinstance(item, dict)
        ]
        latest_frame = (
            max(int(item.get("frame", -1)) for item in results)
            if results
            else None
        )
        public["latest_completed_frame"] = latest_frame
        project_id = str(public.get("project_id") or "")
        render_id = str(public.get("id") or "")
        public["latest_frame_url"] = (
            f"/api/animation/renders/{project_id}/{render_id}/frames/{latest_frame}"
            if latest_frame is not None
            and latest_frame >= 0
            and project_id
            and render_id
            else None
        )

        status = str(public.get("status") or "")
        if status in {"queued", "loading_model", "rendering", "finalizing"}:
            public["status"] = "interrupted"
            public["message"] = "Render interrupted; resume available"
            public["resumable"] = True
        else:
            public.setdefault(
                "resumable",
                status in {"failed", "cancelled", "interrupted"},
            )
        return public

    def _write_manifest(self, job: AnimationRenderJob) -> None:
        _atomic_json(
            _manifest_path(job.project_id, job.id),
            job.manifest(),
        )

    def _worker_loop(self) -> None:
        while True:
            render_id = self._queue.get()
            try:
                with self._lock:
                    job = self._jobs.get(render_id)
                if job is None:
                    continue
                with generation_manager.inference_lock:
                    try:
                        self._run(job)
                    except Exception as exc:
                        self._fail(job, exc)
            finally:
                self._queue.task_done()

    def _starting_frame(self, job: AnimationRenderJob) -> int:
        completed = {
            int(item.get("frame", -1))
            for item in job.results
            if isinstance(item, dict)
        }
        frame = 0
        while frame in completed and _frame_path(
            job.project_id, job.id, frame
        ).is_file():
            frame += 1
        return frame

    def _run(self, job: AnimationRenderJob) -> None:
        job.started_at = job.started_at or _utc_now()
        job.status = "loading_model"
        job.error = None
        job.message = "Preparing animation render"
        self._write_manifest(job)

        project = job.project
        animation = project["animation"]
        width = int(animation["width"])
        height = int(animation["height"])
        fps = float(animation["fps"])
        total = int(animation["max_frames"])
        border_mode = str(project["motion"].get("border_mode", "replicate"))

        start_frame = self._starting_frame(job)
        if start_frame >= total:
            self._complete(job, fps)
            return

        model_id = str(project["model"]["model_id"])
        model = get_model(model_id)
        if not model:
            raise AnimationRenderError(
                "The render model is no longer available in the model index."
            )
        family = str(model["family"])
        capability = generation_manager._effective_capability(model)
        start_mode = str(animation.get("start_mode", "prompt") or "prompt").lower()

        load_started = time.monotonic()
        pipe = None
        generator_device = "cpu"
        render_dir = _render_dir(job.project_id, job.id)
        copied_source = render_dir / "source.png"

        if start_frame == 0:
            resolved = resolve_project_frame(project, 0)
            seed = int(job.seed_plan[0])

            if start_mode == "source":
                with Image.open(copied_source) as opened:
                    frame_image = _prepare_source(opened, width, height)
                start_metadata = {
                    "source_frame": True,
                    "generated_start": False,
                }
                job.message = f"Prepared starting image frame 1 of {total}"
            else:
                generation = resolved["generation"]
                positive = resolved["prompts"]["positive"]
                negative = resolved["prompts"]["negative"]
                steps = int(generation["steps"])
                guidance = float(generation["guidance"])
                sampler = str(generation["sampler"])
                request = GenerationRequest(
                    model_id=model_id,
                    prompt=_safe_prompt_text(positive),
                    negative_prompt=str(negative.get("from_text") or ""),
                    width=width,
                    height=height,
                    steps=steps,
                    guidance_scale=guidance,
                    sampler=sampler,
                    seed=seed,
                    seed_mode="fixed",
                    images=1,
                )

                with self._lock:
                    job.status = "rendering"
                    job.current_frame = 0
                    job.current_step = 0
                    job.message = f"Generating starting frame 1 of {total}"

                pipe, generator_device, validated_model = (
                    generation_manager.prepare_txt2img(request)
                )
                job.model_load_seconds = max(
                    0.0,
                    time.monotonic() - load_started,
                )
                emit_console(
                    "info",
                    "animation",
                    f"{job.id}: txt2img starting-frame pipeline ready in "
                    f"{job.model_load_seconds:.1f}s.",
                )

                import torch

                generator = torch.Generator(
                    device=generator_device
                ).manual_seed(seed)

                def on_start_step_end(
                    pipeline,
                    step: int,
                    timestep,
                    callback_kwargs,
                ):
                    with self._lock:
                        job.current_step = step + 1
                        within = min(1.0, (step + 1) / max(1, steps))
                        job.progress = min(0.999, within / total)
                        cancelled = job.cancel_requested
                    if cancelled:
                        pipeline._interrupt = True
                    return callback_kwargs

                call_args = generation_manager.build_txt2img_call_args(
                    request,
                    validated_model,
                    generator=generator,
                    on_step_end=on_start_step_end,
                )
                conditioning = _prompt_conditioning_kwargs(
                    pipe,
                    family,
                    positive,
                    negative,
                    guidance_scale=guidance,
                    max_sequence_length=int(
                        capability.get("max_sequence_length", 512)
                    ),
                )
                call_args.update(conditioning)

                with torch.inference_mode():
                    result = pipe(**call_args)
                if job.cancel_requested:
                    self._cancel(job)
                    return
                if not result.images:
                    raise AnimationRenderError(
                        "Txt2img returned no image for the starting frame."
                    )
                frame_image = result.images[0].convert("RGB")
                start_metadata = {
                    "source_frame": False,
                    "generated_start": True,
                    "model": model["name"],
                    "family": family,
                    "variant": generation_manager._model_variant(model),
                    "seed": seed,
                }

            path = _frame_path(job.project_id, job.id, 0)
            _save_frame(
                frame_image,
                path,
                metadata={
                    "app": "Morphorum",
                    "render_id": job.id,
                    "project_id": job.project_id,
                    "frame": 0,
                    "start_mode": start_mode,
                    **start_metadata,
                    "resolved": resolved,
                },
            )
            job.results = [
                {
                    "frame": 0,
                    "seed": seed,
                    "filename": path.name,
                    "path": str(path),
                }
            ]
            job.current_frame = 0
            job.current_step = int(resolved["generation"]["steps"]) if start_mode == "prompt" else 0
            job.progress = 1 / total
            job.message = f"Starting frame 1 of {total} complete"
            self._write_manifest(job)
            emit_console(
                "info",
                "animation",
                f"{job.id}: starting frame 0 complete using {start_mode} mode.",
            )
            start_frame = 1
        else:
            previous_path = _frame_path(
                job.project_id,
                job.id,
                start_frame - 1,
            )
            with Image.open(previous_path) as opened:
                frame_image = opened.convert("RGB").copy()

        for frame in range(start_frame, total):
            if job.cancel_requested:
                self._cancel(job)
                return

            frame_started = time.monotonic()
            resolved = resolve_project_frame(project, frame)
            motion = resolved["motion"]
            step_matrix = _frame_transform_matrix(
                width=width,
                height=height,
                angle=float(motion["angle"]),
                zoom=float(motion["zoom"]),
                translation_x=float(motion["translation_x"]),
                translation_y=float(motion["translation_y"]),
            )
            transformed = render_affine(
                frame_image,
                step_matrix,
                border_mode=border_mode,
            )

            generation = resolved["generation"]
            retention_strength = float(generation["strength"])
            if not 0.0 <= retention_strength <= 1.0:
                raise AnimationRenderError(
                    f"Frame {frame} strength resolved to {retention_strength:g}; "
                    "Deforum-style strength must be between 0 and 1."
                )
            denoise_strength = 1.0 - retention_strength

            positive = resolved["prompts"]["positive"]
            negative = resolved["prompts"]["negative"]
            seed = int(job.seed_plan[frame])
            steps = int(generation["steps"])
            guidance = float(generation["guidance"])
            sampler = str(generation["sampler"])
            noise_amount = float(generation["noise"])
            transformed = _add_uniform_noise(
                transformed,
                amount=noise_amount,
                seed=seed,
            )

            with self._lock:
                job.status = "rendering"
                job.current_frame = frame
                job.current_step = 0
                job.message = f"Rendering frame {frame + 1} of {total}"

            if denoise_strength <= 0:
                image = transformed
            else:
                request = GenerationRequest(
                    model_id=model_id,
                    prompt=_safe_prompt_text(positive),
                    negative_prompt=str(negative.get("from_text") or ""),
                    width=width,
                    height=height,
                    steps=steps,
                    guidance_scale=guidance,
                    sampler=sampler,
                    seed=seed,
                    seed_mode="fixed",
                    images=1,
                )

                pipe, generator_device, validated_model = (
                    generation_manager.prepare_img2img(request)
                )
                if job.model_load_seconds is None:
                    job.model_load_seconds = max(
                        0.0,
                        time.monotonic() - load_started,
                    )
                    emit_console(
                        "info",
                        "animation",
                        f"{job.id}: img2img pipeline ready in "
                        f"{job.model_load_seconds:.1f}s.",
                    )

                import torch

                generator = torch.Generator(
                    device=generator_device
                ).manual_seed(seed)

                effective_steps = max(1, int(round(steps * denoise_strength)))

                def on_step_end(
                    pipeline,
                    step: int,
                    timestep,
                    callback_kwargs,
                ):
                    with self._lock:
                        job.current_step = step + 1
                        within = min(
                            1.0,
                            (step + 1) / effective_steps,
                        )
                        job.progress = min(
                            0.999,
                            (frame + within) / total,
                        )
                        cancelled = job.cancel_requested
                    if cancelled:
                        pipeline._interrupt = True
                    return callback_kwargs

                call_args = generation_manager.build_img2img_call_args(
                    request,
                    validated_model,
                    image=transformed,
                    strength=denoise_strength,
                    generator=generator,
                    on_step_end=on_step_end,
                )

                conditioning = _prompt_conditioning_kwargs(
                    pipe,
                    family,
                    positive,
                    negative,
                    guidance_scale=guidance,
                    max_sequence_length=int(
                        capability.get("max_sequence_length", 512)
                    ),
                )
                call_args.update(conditioning)

                with torch.inference_mode():
                    result = pipe(**call_args)
                if job.cancel_requested:
                    self._cancel(job)
                    return
                if not result.images:
                    raise AnimationRenderError(
                        f"Img2img returned no image for frame {frame}."
                    )
                image = result.images[0].convert("RGB")

            path = _frame_path(job.project_id, job.id, frame)
            _save_frame(
                image,
                path,
                metadata={
                    "app": "Morphorum",
                    "render_id": job.id,
                    "project_id": job.project_id,
                    "frame": frame,
                    "seed": seed,
                    "model": model["name"],
                    "family": family,
                    "variant": generation_manager._model_variant(model),
                    "resolved": resolved,
                },
            )

            job.results = [
                item
                for item in job.results
                if int(item.get("frame", -1)) != frame
            ]
            job.results.append(
                {
                    "frame": frame,
                    "seed": seed,
                    "filename": path.name,
                    "path": str(path),
                }
            )
            job.results.sort(key=lambda item: int(item["frame"]))

            frame_seconds = max(0.0, time.monotonic() - frame_started)
            job._frame_times.append(frame_seconds)
            recent = job._frame_times[-8:]
            job.frame_seconds = frame_seconds
            job.average_frame_seconds = sum(recent) / len(recent)
            remaining = max(0, total - frame - 1)
            job.eta_seconds = job.average_frame_seconds * remaining
            job.current_frame = frame
            job.current_step = steps
            job.progress = (frame + 1) / total
            job.message = f"Rendered frame {frame + 1} of {total}"
            self._write_manifest(job)
            frame_image = image

            emit_console(
                "info",
                "animation",
                f"{job.id}: frame {frame}/{total - 1} complete "
                f"in {frame_seconds:.1f}s, seed {seed}, "
                f"strength {retention_strength:g} "
                f"(denoise {denoise_strength:g}), noise {noise_amount:g}.",
            )

        if generation_manager.unload_after_job_enabled():
            job.status = "finalizing"
            job.message = "Unloading model after animation render"
            self._write_manifest(job)
            generation_manager.reset_inference_pipeline()
            gc.collect()

        self._complete(job, fps)

    def _complete(
        self,
        job: AnimationRenderJob,
        fps: float,
    ) -> None:
        job.status = "finalizing"
        job.message = "Building animation preview"
        self._write_manifest(job)
        job.preview = _build_render_preview(
            job.project_id,
            job.id,
            total_frames=job.total_frames,
            fps=fps,
        )
        job.status = "completed"
        job.message = f"Rendered {len(job.results)} frame(s)"
        job.progress = 1.0
        job.eta_seconds = 0.0
        job.completed_at = _utc_now()
        self._write_manifest(job)
        emit_console(
            "info",
            "animation",
            f"Animation render {job.id} complete: "
            f"{len(job.results)} frame(s).",
        )

    def _cancel(self, job: AnimationRenderJob) -> None:
        job.status = "cancelled"
        job.message = "Animation render cancelled"
        job.completed_at = _utc_now()
        job.eta_seconds = None
        self._write_manifest(job)
        emit_console(
            "warning",
            "animation",
            f"Animation render {job.id} cancelled after frame "
            f"{job.current_frame}.",
        )

    def _fail(self, job: AnimationRenderJob, exc: BaseException) -> None:
        generation_manager.reset_inference_pipeline()
        error = (
            generation_manager._friendly_error(
                exc,
                action=f"rendering animation frame {job.current_frame}",
            )
            if isinstance(exc, (GenerationError, RuntimeError))
            else exc
        )
        job.status = "failed"
        job.message = "Animation render failed"
        job.error = str(error)
        job.completed_at = _utc_now()
        job.eta_seconds = None
        self._write_manifest(job)
        emit_console(
            "error",
            "animation",
            f"Animation render {job.id} failed: {error}",
        )


animation_render_manager = AnimationRenderManager()

from __future__ import annotations

import gc
import json
import math
import random
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any

from PIL.PngImagePlugin import PngInfo

from .console import emit_console
from .model_index import get_model
from .paths import CACHE_DIR, OUTPUTS_DIR, ensure_runtime_dirs

SUPPORTED_FAMILIES = {"sdxl"}
FIRST_IMAGE_EXTENSIONS = {".safetensors", ".ckpt"}
LORA_TAG = re.compile(r"<lora:([^:>]+):([+-]?(?:\d+(?:\.\d*)?|\.\d+))>", re.IGNORECASE)

CAPABILITIES: dict[str, dict[str, Any]] = {
    "sdxl": {
        "supported": True,
        "label": "SDXL",
        "steps": {"default": 25, "min": 1, "max": 100},
        "guidance": {"key": "cfg_scale", "label": "CFG", "default": 6.0, "min": 1.0, "max": 30.0},
        "negative_prompt": True,
        "resolutions": [
            {"label": "Square 1:1", "width": 1024, "height": 1024},
            {"label": "Portrait 2:3", "width": 832, "height": 1216},
            {"label": "Landscape 3:2", "width": 1216, "height": 832},
            {"label": "Portrait 7:9", "width": 896, "height": 1152},
            {"label": "Landscape 9:7", "width": 1152, "height": 896},
        ],
    },
    "flux": {
        "supported": False,
        "label": "Flux",
        "reason": "Flux is an enabled Morphorum model family, but its generation adapter has not landed yet.",
    },
    "zimage": {
        "supported": False,
        "label": "Z-Image",
        "reason": "Z-Image is an enabled Morphorum model family, but its generation adapter has not landed yet.",
    },
}


class GenerationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class GenerationRequest:
    model_id: str
    prompt: str
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    steps: int = 25
    guidance_scale: float = 7.0
    seed: int = -1
    seed_mode: str = "fixed"
    seed_increment: int = 1
    images: int = 1

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GenerationRequest":
        return cls(
            model_id=str(payload.get("model_id", "")).strip(),
            prompt=str(payload.get("prompt", "")).strip(),
            negative_prompt=str(payload.get("negative_prompt", "")).strip(),
            width=_safe_int(payload.get("width"), 512),
            height=_safe_int(payload.get("height"), 512),
            steps=_safe_int(payload.get("steps"), 25),
            guidance_scale=_safe_float(payload.get("guidance_scale"), 7.0),
            seed=_safe_int(payload.get("seed"), -1),
            seed_mode=str(payload.get("seed_mode", "fixed")).strip().lower(),
            seed_increment=_safe_int(payload.get("seed_increment"), 1),
            images=_safe_int(payload.get("images"), 1),
        )


@dataclass
class GenerationJob:
    id: str
    request: GenerationRequest
    model: dict[str, Any]
    status: str = "queued"
    message: str = "Queued"
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    current_image: int = 0
    current_step: int = 0
    total_steps: int = 0
    progress: float = 0.0
    eta_seconds: float | None = None
    seeds: list[int] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False
    _started_monotonic: float | None = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("_started_monotonic", None)
        data["request"] = asdict(self.request)
        return data


class GenerationManager:
    def __init__(self) -> None:
        self._jobs: dict[str, GenerationJob] = {}
        self._lock = threading.RLock()
        self._queue: Queue[str] = Queue()
        self._worker: threading.Thread | None = None
        self._pipeline: Any = None
        self._pipeline_model_id: str | None = None
        self._pipeline_device: str | None = None

    def capabilities(self) -> dict[str, dict[str, Any]]:
        return CAPABILITIES

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._worker_loop, name="morphorum-generation", daemon=True)
            self._worker.start()

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = GenerationRequest.from_payload(payload)
        model = self._validate_request(request)
        job_id = f"img-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        seeds = self._resolve_seeds(request)
        job = GenerationJob(
            id=job_id,
            request=request,
            model=model,
            total_steps=request.steps,
            seeds=seeds,
        )
        with self._lock:
            self._jobs[job_id] = job
        self._queue.put(job_id)
        self._ensure_worker()
        emit_console("info", "generation", f"Queued image job {job_id}: {model['name']} × {request.images}.")
        return job.public()

    def _validate_request(self, request: GenerationRequest) -> dict[str, Any]:
        if not request.model_id:
            raise GenerationError("Select a model before generating.")
        model = get_model(request.model_id)
        if not model:
            raise GenerationError("The selected model is no longer in the model index. Rescan Models.")
        if model.get("kind") != "checkpoints":
            raise GenerationError("Image generation requires a checkpoint/model entry, not a LoRA.")
        family = str(model.get("family", ""))
        if family not in SUPPORTED_FAMILIES:
            capability = CAPABILITIES.get(family, {})
            raise GenerationError(capability.get("reason") or f"Model family '{family}' is not supported yet.")
        model_path = Path(model["path"])
        if not model_path.is_file():
            raise GenerationError("The selected checkpoint file no longer exists. Rescan Models.")
        if model_path.suffix.lower() not in FIRST_IMAGE_EXTENSIONS:
            supported = ", ".join(sorted(FIRST_IMAGE_EXTENSIONS))
            raise GenerationError(
                f"The current SDXL adapter only supports {supported} checkpoint files. "
                f"'{model_path.suffix or '[no extension]'}' is indexed for future adapters but cannot be generated yet."
            )
        if not request.prompt:
            raise GenerationError("Prompt cannot be empty.")
        if LORA_TAG.search(request.prompt) or LORA_TAG.search(request.negative_prompt):
            raise GenerationError(
                "LoRA tags are recognized, but LoRA loading is the next adapter step. Remove the <lora:…> tag for this first image test."
            )
        if request.width < 64 or request.height < 64 or request.width > 4096 or request.height > 4096:
            raise GenerationError("Width and height must be between 64 and 4096 pixels.")
        if request.width % 8 or request.height % 8:
            raise GenerationError("Width and height must be divisible by 8.")
        if not 1 <= request.steps <= 150:
            raise GenerationError("Steps must be between 1 and 150.")
        if not 0.0 <= request.guidance_scale <= 30.0:
            raise GenerationError("CFG/guidance must be between 0 and 30.")
        if request.seed_mode not in {"fixed", "increment", "random"}:
            raise GenerationError("Seed mode must be fixed, increment, or random.")
        if not 1 <= request.images <= 32:
            raise GenerationError("Images must be between 1 and 32.")
        return model

    def _resolve_seeds(self, request: GenerationRequest) -> list[int]:
        maximum = 2**32 - 1
        base = request.seed if request.seed >= 0 else random.SystemRandom().randint(0, maximum)
        base %= maximum + 1
        if request.seed_mode == "random":
            rng = random.SystemRandom()
            return [rng.randint(0, maximum) for _ in range(request.images)]
        if request.seed_mode == "increment":
            return [(base + index * request.seed_increment) % (maximum + 1) for index in range(request.images)]
        return [base for _ in range(request.images)]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.public() if job else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())[-max(1, min(limit, 200)):]
            return [job.public() for job in reversed(jobs)]

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job.status in {"completed", "failed", "cancelled"}:
                return job.public()
            job.cancel_requested = True
            job.message = "Cancellation requested"
            if job.status == "queued":
                job.status = "cancelled"
                job.completed_at = _utc_now()
            emit_console("warning", "generation", f"Cancellation requested for {job_id}.")
            return job.public()

    def result_path(self, job_id: str, filename: str) -> Path | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for result in job.results:
                if result.get("filename") == filename:
                    path = Path(result["path"])
                    return path if path.is_file() else None
        return None

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if not job or job.status == "cancelled":
                        continue
                self._run_job(job)
            except Exception as exc:
                with self._lock:
                    job = self._jobs.get(job_id)
                if job:
                    self._fail_job(job, exc)
                else:
                    self._unload_pipeline()
                    emit_console("error", "generation", f"Generation worker failed before job lookup: {exc}")
            finally:
                self._queue.task_done()

    def _set_status(self, job: GenerationJob, status: str, message: str) -> None:
        with self._lock:
            job.status = status
            job.message = message

    @staticmethod
    def _is_cuda_oom(exc: BaseException) -> bool:
        message = str(exc).lower()
        if "cuda out of memory" in message or "cuda error: out of memory" in message:
            return True
        try:
            import torch

            oom_type = getattr(torch.cuda, "OutOfMemoryError", None)
            return bool(oom_type and isinstance(exc, oom_type))
        except Exception:
            return False

    def _friendly_error(self, exc: BaseException, *, action: str = "generating the image") -> GenerationError:
        if isinstance(exc, GenerationError) and not self._is_cuda_oom(exc):
            return exc
        if self._is_cuda_oom(exc):
            return GenerationError(
                f"GPU memory exhausted while {action}. Morphorum will unload the failed pipeline and clear "
                "the CUDA cache. Try a lower resolution, close other GPU-heavy applications, generate fewer "
                "images at once, or use a lower-memory model."
            )
        if isinstance(exc, GenerationError):
            return exc
        return GenerationError(str(exc) or exc.__class__.__name__)

    def _fail_job(self, job: GenerationJob, exc: BaseException) -> None:
        error = self._friendly_error(exc)
        self._unload_pipeline()
        with self._lock:
            job.status = "failed"
            job.error = str(error)
            job.message = "Generation failed"
            job.completed_at = _utc_now()
            job.eta_seconds = None
        emit_console("error", "generation", f"Job {job.id} failed: {error}")
        try:
            self._write_manifest(job)
        except Exception as manifest_exc:
            emit_console(
                "warning",
                "generation",
                f"Could not write failure manifest for {job.id}: {manifest_exc}",
            )

    def _load_pipeline(self, job: GenerationJob):
        model = job.model
        model_id = model["id"]
        if self._pipeline is not None and self._pipeline_model_id == model_id:
            emit_console("info", "generation", f"Reusing loaded model: {model['name']}.")
            return self._pipeline, self._pipeline_device

        self._unload_pipeline()
        self._set_status(job, "loading_model", f"Loading {model['name']}")
        emit_console("info", "generation", f"Loading {model['family']} checkpoint: {model['path']}")

        try:
            import torch
            from diffusers import StableDiffusionXLPipeline
        except Exception as exc:
            raise GenerationError(f"Inference runtime is not installed correctly: {exc}") from exc

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        pipeline_class = StableDiffusionXLPipeline
        cache_dir = CACHE_DIR / "huggingface"
        cache_dir.mkdir(parents=True, exist_ok=True)

        kwargs: dict[str, Any] = {
            "torch_dtype": dtype,
            "cache_dir": str(cache_dir),
        }
        try:
            pipe = pipeline_class.from_single_file(model["path"], **kwargs)
            pipe.set_progress_bar_config(disable=True)
            pipe.to(device)
        except Exception as exc:
            if self._is_cuda_oom(exc):
                raise self._friendly_error(exc, action=f"loading checkpoint '{model['name']}'") from exc
            raise GenerationError(
                f"Could not load checkpoint '{model['name']}'. Diffusers may need its matching pipeline config on first load. {exc}"
            ) from exc

        self._pipeline = pipe
        self._pipeline_model_id = model_id
        self._pipeline_device = device
        emit_console("info", "generation", f"Model ready on {device}: {model['name']}.")
        return pipe, device

    def _unload_pipeline(self) -> None:
        had_pipeline = self._pipeline is not None
        if had_pipeline:
            emit_console("info", "generation", "Unloading diffusion pipeline.")
        self._pipeline = None
        self._pipeline_model_id = None
        self._pipeline_device = None

        # Always collect here, even if model loading failed before the pipeline
        # could be registered on the manager.
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                ipc_collect = getattr(torch.cuda, "ipc_collect", None)
                if callable(ipc_collect):
                    try:
                        ipc_collect()
                    except Exception:
                        pass
        except Exception:
            pass

    def _run_job(self, job: GenerationJob) -> None:
        if job.cancel_requested:
            return
        job.started_at = _utc_now()
        job._started_monotonic = time.monotonic()
        pipe, device = self._load_pipeline(job)
        if job.cancel_requested:
            self._finish_cancelled(job)
            return

        import torch

        output_dir = OUTPUTS_DIR / "images" / datetime.now().strftime("%Y-%m-%d") / job.id
        output_dir.mkdir(parents=True, exist_ok=True)
        total_images = len(job.seeds)

        for image_index, seed in enumerate(job.seeds):
            if job.cancel_requested:
                self._finish_cancelled(job)
                self._write_manifest(job, output_dir)
                return

            with self._lock:
                job.status = "generating"
                job.current_image = image_index + 1
                job.current_step = 0
                job.message = f"Generating image {image_index + 1} of {total_images}"
            emit_console("info", "generation", f"{job.id}: image {image_index + 1}/{total_images}, seed {seed}.")

            generator = torch.Generator(device=device).manual_seed(seed)

            def on_step_end(pipeline, step: int, timestep, callback_kwargs):
                with self._lock:
                    job.current_step = step + 1
                    image_fraction = min(1.0, (step + 1) / max(1, job.request.steps))
                    job.progress = min(0.999, (image_index + image_fraction) / total_images)
                    elapsed = time.monotonic() - (job._started_monotonic or time.monotonic())
                    if job.progress > 0.01:
                        job.eta_seconds = max(0.0, elapsed * (1.0 - job.progress) / job.progress)
                    cancelled = job.cancel_requested
                if cancelled:
                    pipeline._interrupt = True
                return callback_kwargs

            call_args = {
                "prompt": job.request.prompt,
                "negative_prompt": job.request.negative_prompt or None,
                "width": job.request.width,
                "height": job.request.height,
                "num_inference_steps": job.request.steps,
                "guidance_scale": job.request.guidance_scale,
                "generator": generator,
                "callback_on_step_end": on_step_end,
            }

            with torch.inference_mode():
                result = pipe(**call_args)

            if job.cancel_requested:
                self._finish_cancelled(job)
                self._write_manifest(job, output_dir)
                return
            if not result.images:
                raise GenerationError("The diffusion pipeline returned no image.")

            image = result.images[0]
            filename = f"image_{image_index + 1:04d}_seed_{seed}.png"
            image_path = output_dir / filename
            pnginfo = PngInfo()
            metadata = {
                "app": "Morphorum",
                "job_id": job.id,
                "model": job.model["name"],
                "model_path": job.model["path"],
                "family": job.model["family"],
                "prompt": job.request.prompt,
                "negative_prompt": job.request.negative_prompt,
                "seed": seed,
                "width": job.request.width,
                "height": job.request.height,
                "steps": job.request.steps,
                "guidance_scale": job.request.guidance_scale,
            }
            pnginfo.add_text("Morphorum", json.dumps(metadata, ensure_ascii=False))
            image.save(image_path, pnginfo=pnginfo)

            with self._lock:
                job.results.append(
                    {
                        "index": image_index + 1,
                        "seed": seed,
                        "filename": filename,
                        "path": str(image_path),
                        "url": f"/api/generation/jobs/{job.id}/images/{filename}",
                    }
                )
                job.progress = (image_index + 1) / total_images
                job.current_step = job.request.steps
            emit_console("info", "generation", f"Saved {filename}.")

        with self._lock:
            job.status = "completed"
            job.message = f"Generated {len(job.results)} image(s)"
            job.progress = 1.0
            job.eta_seconds = 0.0
            job.completed_at = _utc_now()
        self._write_manifest(job, output_dir)
        emit_console("info", "generation", f"Job {job.id} complete: {len(job.results)} image(s).")

    def _finish_cancelled(self, job: GenerationJob) -> None:
        with self._lock:
            job.status = "cancelled"
            job.message = "Generation cancelled"
            job.completed_at = _utc_now()
            job.eta_seconds = None
        emit_console("warning", "generation", f"Job {job.id} cancelled.")

    def _write_manifest(self, job: GenerationJob, output_dir: Path | None = None) -> None:
        if output_dir is None:
            output_dir = OUTPUTS_DIR / "images" / datetime.now().strftime("%Y-%m-%d") / job.id
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = job.public()
        manifest["model"] = dict(job.model)
        (output_dir / "job.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


generation_manager = GenerationManager()

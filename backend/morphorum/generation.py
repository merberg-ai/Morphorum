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
from .settings import load_settings

SUPPORTED_FAMILIES = {"sdxl", "flux", "zimage"}
FAMILY_IMAGE_EXTENSIONS = {
    "sdxl": {".safetensors", ".ckpt"},
    "flux": {".safetensors"},
}
FLUX_COMPONENT_REPO = "black-forest-labs/FLUX.1-schnell"
LORA_TAG = re.compile(r"<lora:([^:>]+):([+-]?(?:\d+(?:\.\d*)?|\.\d+))>", re.IGNORECASE)

CAPABILITIES: dict[str, dict[str, Any]] = {
    "sdxl": {
        "supported": True,
        "label": "SDXL",
        "steps": {"default": 25, "min": 1, "max": 100},
        "guidance": {"key": "cfg_scale", "label": "CFG", "default": 6.0, "min": 1.0, "max": 30.0},
        "negative_prompt": True,
        "default_resolution": {"width": 1024, "height": 1024},
        "samplers": {
            "default": "euler",
            "options": [
                {"id": "euler", "label": "Euler"},
                {"id": "euler_a", "label": "Euler a"},
                {"id": "dpmpp_2m", "label": "DPM++ 2M"},
                {"id": "dpmpp_2m_sde", "label": "DPM++ 2M SDE"},
                {"id": "ddim", "label": "DDIM"},
                {"id": "lms", "label": "LMS"},
                {"id": "heun", "label": "Heun"},
                {"id": "unipc", "label": "UniPC"},
            ],
        },
        "resolutions": [
            {"label": "Square 1:1", "width": 1024, "height": 1024},
            {"label": "Portrait 2:3", "width": 832, "height": 1216},
            {"label": "Landscape 3:2", "width": 1216, "height": 832},
            {"label": "Portrait 7:9", "width": 896, "height": 1152},
            {"label": "Landscape 9:7", "width": 1152, "height": 896},
        ],
    },
    "flux": {
        "supported": True,
        "label": "Flux",
        "steps": {"default": 28, "min": 1, "max": 50},
        "guidance": {"key": "guidance_scale", "label": "CFG", "default": 1.0, "min": 0.0, "max": 10.0},
        "negative_prompt": False,
        "default_resolution": {"width": 1024, "height": 1024},
        "samplers": {
            "default": "flowmatch_euler",
            "options": [
                {"id": "flowmatch_euler", "label": "FlowMatch Euler"},
            ],
        },
        "resolutions": [
            {"label": "Square 1:1", "width": 1024, "height": 1024},
            {"label": "Portrait 2:3", "width": 832, "height": 1216},
            {"label": "Landscape 3:2", "width": 1216, "height": 832},
            {"label": "Portrait 9:16", "width": 768, "height": 1360},
            {"label": "Landscape 16:9", "width": 1360, "height": 768},
        ],
        "variants": {
            "dev": {
                "label": "Flux Dev",
                "steps": {"default": 28, "min": 1, "max": 50},
                "guidance": {"key": "guidance_scale", "label": "CFG", "default": 1.0, "min": 0.0, "max": 10.0},
                "negative_prompt": False,
                "default_resolution": {"width": 1024, "height": 1024},
                "max_sequence_length": 512,
            },
            "schnell": {
                "label": "Flux Schnell",
                "steps": {"default": 4, "min": 1, "max": 8},
                "guidance": {"key": "guidance_scale", "label": "Guidance", "default": 0.0, "min": 0.0, "max": 0.0},
                "negative_prompt": False,
                "default_resolution": {"width": 1024, "height": 1024},
                "max_sequence_length": 256,
            },
        },
    },
    "zimage": {
        "supported": True,
        "label": "Z-Image Turbo",
        "steps": {"default": 9, "min": 1, "max": 20},
        "guidance": {"key": "guidance_scale", "label": "Guidance", "default": 0.0, "min": 0.0, "max": 0.0},
        "negative_prompt": False,
        "default_resolution": {"width": 1024, "height": 1024},
        "samplers": {
            "default": "flowmatch_euler",
            "options": [
                {"id": "flowmatch_euler", "label": "FlowMatch Euler"},
            ],
        },
        "resolutions": [
            {"label": "Square 1:1", "width": 1024, "height": 1024},
            {"label": "Portrait 2:3", "width": 832, "height": 1216},
            {"label": "Landscape 3:2", "width": 1216, "height": 832},
            {"label": "Portrait 9:16", "width": 768, "height": 1360},
            {"label": "Landscape 16:9", "width": 1360, "height": 768},
        ],
        "variants": {
            "turbo": {
                "label": "Z-Image Turbo",
                "steps": {"default": 9, "min": 1, "max": 20},
                "guidance": {"key": "guidance_scale", "label": "Guidance", "default": 0.0, "min": 0.0, "max": 0.0},
                "negative_prompt": False,
                "default_resolution": {"width": 1024, "height": 1024},
            },
        },
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
    sampler: str = "euler"
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
            sampler=str(payload.get("sampler", "euler")).strip().lower(),
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
    model_load_seconds: float | None = None
    last_step_seconds: float | None = None
    average_step_seconds: float | None = None
    seeds: list[int] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False
    _started_monotonic: float | None = field(default=None, repr=False)
    _last_step_monotonic: float | None = field(default=None, repr=False)
    _step_durations: list[float] = field(default_factory=list, repr=False)

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("_started_monotonic", None)
        data.pop("_last_step_monotonic", None)
        data.pop("_step_durations", None)
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
        self._pipeline_scheduler_config: dict[str, Any] | None = None
        self._pipeline_sampler: str | None = None
        self._pipeline_optimization: str | None = None

    def capabilities(self) -> dict[str, dict[str, Any]]:
        return CAPABILITIES

    def model_status(self) -> dict[str, Any]:
        with self._lock:
            loaded = self._pipeline is not None
            model_id = self._pipeline_model_id
            device = self._pipeline_device
            active = any(
                job.status in {"queued", "loading_model", "generating", "finalizing"}
                for job in self._jobs.values()
            )

        model = get_model(model_id) if model_id else None
        return {
            "loaded": loaded,
            "model_id": model_id,
            "model_name": model.get("name") if model else None,
            "family": model.get("family") if model else None,
            "device": device,
            "sampler": self._pipeline_sampler,
            "optimization": self._pipeline_optimization,
            "busy": active,
        }

    def unload_model(self) -> dict[str, Any]:
        with self._lock:
            active = [
                job.id
                for job in self._jobs.values()
                if job.status in {"queued", "loading_model", "generating", "finalizing"}
            ]
            if active:
                raise GenerationError(
                    "Cannot unload the model while generation is active. Cancel or wait for the current batch to finish."
                )
            was_loaded = self._pipeline is not None
            model_id = self._pipeline_model_id

        self._unload_pipeline()
        if was_loaded:
            emit_console("info", "generation", "Model unloaded manually.")
        return {
            "status": "unloaded" if was_loaded else "not_loaded",
            "model_id": model_id,
            "loaded": False,
        }

    @staticmethod
    def _unload_after_generation_enabled() -> bool:
        try:
            settings = load_settings()
            performance = settings.get("performance", {}) if isinstance(settings, dict) else {}
            return bool(performance.get("unload_after_generation", False))
        except Exception as exc:
            emit_console(
                "warning",
                "generation",
                f"Could not read unload-after-generation setting: {exc}",
            )
            return False

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

    @staticmethod
    def _model_variant(model: dict[str, Any]) -> str:
        variant = str(model.get("variant") or "").strip().lower()
        if variant:
            return variant
        if str(model.get("family", "")).lower() == "flux":
            name = f"{model.get('name', '')} {model.get('filename', '')}".lower()
            return "schnell" if "schnell" in name else "dev"
        return str(model.get("family", "")).lower()

    def _effective_capability(self, model: dict[str, Any]) -> dict[str, Any]:
        family = str(model.get("family", ""))
        base = dict(CAPABILITIES.get(family, {}))
        variant = self._model_variant(model)
        variant_config = base.get("variants", {}).get(variant, {})
        if variant_config:
            merged = dict(base)
            for key, value in variant_config.items():
                if isinstance(value, dict) and isinstance(base.get(key), dict):
                    merged[key] = {**base[key], **value}
                else:
                    merged[key] = value
            merged["variant"] = variant
            return merged
        base["variant"] = variant
        return base

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

        capability = self._effective_capability(model)
        sampler_config = capability.get("samplers", {})
        sampler_ids = {
            str(item.get("id"))
            for item in sampler_config.get("options", [])
            if isinstance(item, dict) and item.get("id")
        }
        if request.sampler not in sampler_ids:
            raise GenerationError(
                f"Sampler '{request.sampler}' is not supported for {capability.get('label', family)}."
            )

        model_path = Path(model["path"])
        if family == "zimage":
            required = (
                model_path / "model_index.json",
                model_path / "scheduler",
                model_path / "text_encoder",
                model_path / "tokenizer",
                model_path / "transformer",
                model_path / "vae",
            )
            if not model_path.is_dir() or not all(path.exists() for path in required):
                raise GenerationError(
                    "The selected Z-Image managed package is missing or incomplete. "
                    "Open Models and repair/re-download Z-Image-Turbo."
                )
        else:
            if not model_path.is_file():
                raise GenerationError("The selected checkpoint file no longer exists. Rescan Models.")
            allowed_extensions = FAMILY_IMAGE_EXTENSIONS.get(family, set())
            if model_path.suffix.lower() not in allowed_extensions:
                supported = ", ".join(sorted(allowed_extensions)) or "(none)"
                raise GenerationError(
                    f"The current {capability.get('label', family)} adapter only supports {supported} model files. "
                    f"'{model_path.suffix or '[no extension]'}' is indexed but cannot be generated by this adapter yet."
                )
        if not request.prompt:
            raise GenerationError("Prompt cannot be empty.")
        if LORA_TAG.search(request.prompt) or LORA_TAG.search(request.negative_prompt):
            raise GenerationError(
                "LoRA tags are recognized, but LoRA loading is the next adapter step. Remove the <lora:…> tag for this first image test."
            )
        if request.width < 64 or request.height < 64 or request.width > 4096 or request.height > 4096:
            raise GenerationError("Width and height must be between 64 and 4096 pixels.")
        divisor = 16 if family in {"flux", "zimage"} else 8
        if request.width % divisor or request.height % divisor:
            raise GenerationError(f"Width and height must be divisible by {divisor} for {capability.get('label', family)}.")

        steps_config = capability.get("steps", {})
        min_steps = int(steps_config.get("min", 1))
        max_steps = int(steps_config.get("max", 150))
        if not min_steps <= request.steps <= max_steps:
            raise GenerationError(
                f"Steps must be between {min_steps} and {max_steps} for {capability.get('label', family)}."
            )

        guidance_config = capability.get("guidance", {})
        min_guidance = float(guidance_config.get("min", 0.0))
        max_guidance = float(guidance_config.get("max", 30.0))
        if not min_guidance <= request.guidance_scale <= max_guidance:
            if family == "flux" and self._model_variant(model) == "schnell":
                raise GenerationError("Flux Schnell requires Guidance = 0.")
            if family == "zimage":
                raise GenerationError("Z-Image Turbo requires Guidance = 0.")
            raise GenerationError(
                f"Guidance must be between {min_guidance:g} and {max_guidance:g} for {capability.get('label', family)}."
            )
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

    def _load_sdxl_pipeline(self, job: GenerationJob, cache_dir: Path):
        try:
            import torch
            from diffusers import StableDiffusionXLPipeline
        except Exception as exc:
            raise GenerationError(f"Inference runtime is not installed correctly: {exc}") from exc

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        try:
            pipe = StableDiffusionXLPipeline.from_single_file(
                job.model["path"],
                torch_dtype=dtype,
                cache_dir=str(cache_dir),
            )
            pipe.set_progress_bar_config(disable=True)
            pipe.to(device)
        except Exception as exc:
            if self._is_cuda_oom(exc):
                raise self._friendly_error(exc, action=f"loading checkpoint '{job.model['name']}'") from exc
            raise GenerationError(
                f"Could not load checkpoint '{job.model['name']}'. Diffusers may need its matching pipeline config on first load. {exc}"
            ) from exc
        return pipe, device, device

    def _load_flux_pipeline(self, job: GenerationJob, cache_dir: Path):
        try:
            import torch
            from diffusers import FluxPipeline, FluxTransformer2DModel
            from diffusers.hooks import apply_group_offloading
        except Exception as exc:
            raise GenerationError(f"Flux inference runtime is not installed correctly: {exc}") from exc

        if not torch.cuda.is_available():
            raise GenerationError(
                "The first Flux adapter requires a CUDA-capable NVIDIA GPU. CPU Flux inference is intentionally disabled because it is impractically slow."
            )

        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        variant = self._model_variant(job.model)
        self._set_status(
            job,
            "loading_model",
            f"Loading {job.model['name']} and shared Flux components",
        )
        emit_console(
            "info",
            "generation",
            f"Loading Flux {variant} transformer: {job.model['path']}",
        )
        emit_console(
            "info",
            "generation",
            "Flux uses shared CLIP/T5/VAE components cached by Morphorum. The first Flux load may download several gigabytes.",
        )

        try:
            transformer = FluxTransformer2DModel.from_single_file(
                job.model["path"],
                torch_dtype=dtype,
                cache_dir=str(cache_dir),
            )

            optimization = "bf16-cpu-offload"
            compute_capability = torch.cuda.get_device_capability(0)
            supports_native_fp8 = (
                compute_capability >= (8, 9)
                and hasattr(torch, "float8_e4m3fn")
                and hasattr(transformer, "enable_layerwise_casting")
            )
            if supports_native_fp8:
                transformer.enable_layerwise_casting(
                    storage_dtype=torch.float8_e4m3fn,
                    compute_dtype=dtype,
                )
                optimization = "fp8-layerwise-bf16-compute"
                emit_console(
                    "info",
                    "generation",
                    "Flux fast path enabled: FP8 layerwise weight storage with BF16 compute.",
                )
            else:
                emit_console(
                    "warning",
                    "generation",
                    "Flux FP8 layerwise fast path unavailable; using BF16 with CPU offload.",
                )

            pipe = FluxPipeline.from_pretrained(
                FLUX_COMPONENT_REPO,
                transformer=transformer,
                torch_dtype=dtype,
                cache_dir=str(cache_dir),
            )
            pipe.set_progress_bar_config(disable=True)
            if hasattr(pipe.vae, "enable_tiling"):
                pipe.vae.enable_tiling()
            if hasattr(pipe.vae, "enable_slicing"):
                pipe.vae.enable_slicing()

            onload_device = torch.device("cuda")
            offload_device = torch.device("cpu")
            offloaded_components = 0
            for component_name in ("transformer", "text_encoder", "text_encoder_2", "vae"):
                component = getattr(pipe, component_name, None)
                if component is None:
                    continue
                try:
                    if component_name == "transformer":
                        try:
                            apply_group_offloading(
                                component,
                                onload_device=onload_device,
                                offload_device=offload_device,
                                offload_type="block_level",
                                num_blocks_per_group=1,
                                use_stream=True,
                            )
                            emit_console(
                                "info",
                                "generation",
                                "Flux transformer uses streamed block-level group offload (1 block/group).",
                            )
                        except Exception as block_exc:
                            emit_console(
                                "warning",
                                "generation",
                                f"Flux block-level offload unavailable ({block_exc}); falling back to streamed leaf-level offload.",
                            )
                            apply_group_offloading(
                                component,
                                onload_device=onload_device,
                                offload_device=offload_device,
                                offload_type="leaf_level",
                                use_stream=True,
                            )
                    else:
                        apply_group_offloading(
                            component,
                            onload_device=onload_device,
                            offload_device=offload_device,
                            offload_type="leaf_level",
                            use_stream=True,
                        )
                    offloaded_components += 1
                except Exception as component_exc:
                    raise GenerationError(
                        f"Could not configure Flux group offload for {component_name}: {component_exc}"
                    ) from component_exc

            if offloaded_components == 0:
                raise GenerationError("Flux group offload could not find any pipeline components to manage.")

            optimization += "+streamed-group-offload"
            self._pipeline_optimization = optimization
            emit_console(
                "info",
                "generation",
                "Flux VRAM headroom mode enabled: streamed group offloading keeps working memory available for activations.",
            )
        except Exception as exc:
            if self._is_cuda_oom(exc):
                raise self._friendly_error(exc, action=f"loading Flux model '{job.model['name']}'") from exc
            raise GenerationError(
                f"Could not load Flux model '{job.model['name']}'. The selected file must be a Flux transformer .safetensors checkpoint. "
                f"Morphorum also needs access to the shared Flux components on first load. {exc}"
            ) from exc

        return pipe, "cuda-offload", "cpu"

    def _load_zimage_pipeline(self, job: GenerationJob, cache_dir: Path):
        try:
            import torch
            from diffusers import ZImagePipeline
        except Exception as exc:
            raise GenerationError(
                f"Z-Image inference runtime is not installed correctly: {exc}"
            ) from exc

        if not torch.cuda.is_available():
            raise GenerationError(
                "The first Z-Image adapter requires a CUDA-capable NVIDIA GPU. "
                "CPU Z-Image inference is intentionally disabled because it is impractically slow."
            )

        model_path = Path(job.model["path"])
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        emit_console(
            "info",
            "generation",
            f"Loading managed Z-Image pipeline from: {model_path}",
        )

        def load_local_pipeline():
            return ZImagePipeline.from_pretrained(
                str(model_path),
                torch_dtype=dtype,
                low_cpu_mem_usage=False,
                local_files_only=True,
                cache_dir=str(cache_dir),
            )

        try:
            pipe = load_local_pipeline()
            pipe.set_progress_bar_config(disable=True)
            if hasattr(pipe.vae, "enable_tiling"):
                pipe.vae.enable_tiling()
            if hasattr(pipe.vae, "enable_slicing"):
                pipe.vae.enable_slicing()

            try:
                pipe.to("cuda")
                self._pipeline_optimization = "bf16-native-gpu"
                emit_console(
                    "info",
                    "generation",
                    "Z-Image native CUDA path enabled.",
                )
                return pipe, "cuda", "cuda"
            except Exception as native_exc:
                if not self._is_cuda_oom(native_exc):
                    raise

                emit_console(
                    "warning",
                    "generation",
                    "Z-Image native CUDA placement exhausted VRAM; retrying with model CPU offload.",
                )
                try:
                    del pipe
                except Exception:
                    pass
                gc.collect()
                torch.cuda.empty_cache()

                pipe = load_local_pipeline()
                pipe.set_progress_bar_config(disable=True)
                if hasattr(pipe.vae, "enable_tiling"):
                    pipe.vae.enable_tiling()
                if hasattr(pipe.vae, "enable_slicing"):
                    pipe.vae.enable_slicing()
                pipe.enable_model_cpu_offload()
                self._pipeline_optimization = "bf16-model-cpu-offload"
                return pipe, "cuda-offload", "cpu"
        except Exception as exc:
            if self._is_cuda_oom(exc):
                raise self._friendly_error(
                    exc,
                    action=f"loading Z-Image model '{job.model['name']}'",
                ) from exc
            raise GenerationError(
                f"Could not load managed Z-Image model '{job.model['name']}' from {model_path}. "
                f"The package may be incomplete or incompatible with this Diffusers runtime. {exc}"
            ) from exc

    def _load_pipeline(self, job: GenerationJob):
        model = job.model
        model_id = model["id"]
        family = str(model.get("family", ""))

        if self._pipeline is not None and self._pipeline_model_id == model_id:
            emit_console("info", "generation", f"Reusing loaded model: {model['name']}.")
            if family == "flux" or self._pipeline_device == "cuda-offload":
                generator_device = "cpu"
            else:
                generator_device = self._pipeline_device or "cpu"
            return self._pipeline, generator_device

        self._unload_pipeline()
        self._set_status(job, "loading_model", f"Loading {model['name']}")
        emit_console("info", "generation", f"Loading {family} checkpoint: {model['path']}")

        cache_dir = CACHE_DIR / "huggingface"
        cache_dir.mkdir(parents=True, exist_ok=True)

        if family == "sdxl":
            pipe, display_device, generator_device = self._load_sdxl_pipeline(job, cache_dir)
        elif family == "flux":
            pipe, display_device, generator_device = self._load_flux_pipeline(job, cache_dir)
        elif family == "zimage":
            pipe, display_device, generator_device = self._load_zimage_pipeline(job, cache_dir)
        else:
            raise GenerationError(f"No pipeline loader is registered for model family '{family}'.")

        self._pipeline = pipe
        self._pipeline_model_id = model_id
        self._pipeline_device = display_device
        self._pipeline_scheduler_config = dict(pipe.scheduler.config)
        self._pipeline_sampler = None
        if self._pipeline_optimization is None:
            self._pipeline_optimization = "native-gpu" if "cuda" in display_device else display_device
        emit_console(
            "info",
            "generation",
            f"Model ready on {display_device}: {model['name']} ({self._pipeline_optimization or 'default'}).",
        )
        return pipe, generator_device

    def _configure_sampler(self, pipe: Any, family: str, sampler: str) -> None:
        base_config = self._pipeline_scheduler_config or dict(pipe.scheduler.config)

        try:
            if family in {"flux", "zimage"}:
                from diffusers import FlowMatchEulerDiscreteScheduler

                if sampler != "flowmatch_euler":
                    label = "Flux" if family == "flux" else "Z-Image"
                    raise GenerationError(f"Unknown {label} sampler '{sampler}'.")
                pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(base_config)
            elif family == "sdxl":
                from diffusers import (
                    DDIMScheduler,
                    DPMSolverMultistepScheduler,
                    EulerAncestralDiscreteScheduler,
                    EulerDiscreteScheduler,
                    HeunDiscreteScheduler,
                    LMSDiscreteScheduler,
                    UniPCMultistepScheduler,
                )

                sampler_specs: dict[str, tuple[Any, dict[str, Any]]] = {
                    "euler": (EulerDiscreteScheduler, {}),
                    "euler_a": (EulerAncestralDiscreteScheduler, {}),
                    "dpmpp_2m": (
                        DPMSolverMultistepScheduler,
                        {"algorithm_type": "dpmsolver++", "solver_order": 2},
                    ),
                    "dpmpp_2m_sde": (
                        DPMSolverMultistepScheduler,
                        {"algorithm_type": "sde-dpmsolver++", "solver_order": 2},
                    ),
                    "ddim": (DDIMScheduler, {}),
                    "lms": (LMSDiscreteScheduler, {}),
                    "heun": (HeunDiscreteScheduler, {}),
                    "unipc": (UniPCMultistepScheduler, {}),
                }
                spec = sampler_specs.get(sampler)
                if spec is None:
                    raise GenerationError(f"Unknown sampler '{sampler}'.")
                scheduler_class, scheduler_kwargs = spec
                pipe.scheduler = scheduler_class.from_config(base_config, **scheduler_kwargs)
            else:
                raise GenerationError(f"Sampler switching is not implemented for model family '{family}'.")
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError(f"Could not configure sampler '{sampler}': {exc}") from exc

        if self._pipeline_sampler != sampler:
            emit_console("info", "generation", f"Sampler configured: {sampler}.")
        self._pipeline_sampler = sampler

    def _unload_pipeline(self) -> None:
        had_pipeline = self._pipeline is not None
        if had_pipeline:
            emit_console("info", "generation", "Unloading diffusion pipeline.")
        self._pipeline = None
        self._pipeline_model_id = None
        self._pipeline_device = None
        self._pipeline_scheduler_config = None
        self._pipeline_sampler = None
        self._pipeline_optimization = None

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

    def _build_call_args(
        self,
        job: GenerationJob,
        generator: Any,
        on_step_end: Any,
    ) -> dict[str, Any]:
        family = str(job.model.get("family", ""))
        call_args: dict[str, Any] = {
            "prompt": job.request.prompt,
            "width": job.request.width,
            "height": job.request.height,
            "num_inference_steps": job.request.steps,
            "guidance_scale": job.request.guidance_scale,
            "generator": generator,
            "callback_on_step_end": on_step_end,
        }

        if family == "sdxl":
            call_args["negative_prompt"] = job.request.negative_prompt or None
        elif family == "flux":
            capability = self._effective_capability(job.model)
            call_args["max_sequence_length"] = int(capability.get("max_sequence_length", 512))
        elif family == "zimage":
            pass
        else:
            raise GenerationError(f"No inference call builder is registered for model family '{family}'.")

        return call_args

    def _run_job(self, job: GenerationJob) -> None:
        if job.cancel_requested:
            return
        job.started_at = _utc_now()
        load_started = time.monotonic()
        pipe, device = self._load_pipeline(job)
        self._configure_sampler(pipe, job.model["family"], job.request.sampler)
        job.model_load_seconds = max(0.0, time.monotonic() - load_started)
        job._started_monotonic = time.monotonic()
        job._last_step_monotonic = None
        job._step_durations.clear()
        job.last_step_seconds = None
        job.average_step_seconds = None
        job.eta_seconds = None
        emit_console(
            "info",
            "generation",
            f"{job.id}: pipeline ready in {job.model_load_seconds:.1f}s; denoising timer starts now.",
        )
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
                now = time.monotonic()
                with self._lock:
                    job.current_step = step + 1
                    image_fraction = min(1.0, (step + 1) / max(1, job.request.steps))
                    job.progress = min(0.999, (image_index + image_fraction) / total_images)

                    if job._last_step_monotonic is None:
                        step_seconds = now - (job._started_monotonic or now)
                    else:
                        step_seconds = now - job._last_step_monotonic
                    job._last_step_monotonic = now
                    if step_seconds >= 0:
                        job._step_durations.append(step_seconds)
                        recent = job._step_durations[-8:]
                        job.last_step_seconds = step_seconds
                        job.average_step_seconds = sum(recent) / len(recent)

                    completed_steps = image_index * job.request.steps + (step + 1)
                    total_steps_all = total_images * job.request.steps
                    remaining_steps = max(0, total_steps_all - completed_steps)
                    if job.average_step_seconds is not None:
                        job.eta_seconds = max(0.0, job.average_step_seconds * remaining_steps)

                    cancelled = job.cancel_requested
                if cancelled:
                    pipeline._interrupt = True
                return callback_kwargs

            call_args = self._build_call_args(job, generator, on_step_end)

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
                "variant": self._model_variant(job.model),
                "prompt": job.request.prompt,
                "negative_prompt": job.request.negative_prompt,
                "seed": seed,
                "width": job.request.width,
                "height": job.request.height,
                "steps": job.request.steps,
                "guidance_scale": job.request.guidance_scale,
                "sampler": job.request.sampler,
                "max_sequence_length": (
                    self._effective_capability(job.model).get("max_sequence_length")
                    if job.model.get("family") == "flux"
                    else None
                ),
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

        if self._unload_after_generation_enabled():
            with self._lock:
                job.status = "finalizing"
                job.message = "Unloading model after generation"
                job.progress = 1.0
                job.eta_seconds = 0.0
            self._unload_pipeline()
            emit_console("info", "generation", f"{job.id}: model unloaded after batch completion.")

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

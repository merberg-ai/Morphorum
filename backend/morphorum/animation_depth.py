from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .console import emit_console
from .paths import CACHE_DIR, ensure_runtime_dirs

DEPTH_CACHE_VERSION = 1
DEFAULT_DEPTH_MODEL = "depth-anything-v2-small"


class DepthError(RuntimeError):
    pass


@dataclass(frozen=True)
class DepthModelSpec:
    id: str
    label: str
    repo_id: str
    depth_type: str = "relative"
    license: str = "apache-2.0"


DEPTH_MODELS: dict[str, DepthModelSpec] = {
    DEFAULT_DEPTH_MODEL: DepthModelSpec(
        id=DEFAULT_DEPTH_MODEL,
        label="Depth Anything V2 Small",
        repo_id="depth-anything/Depth-Anything-V2-Small-hf",
    ),
}


def depth_model_catalog() -> list[dict[str, Any]]:
    return [asdict(spec) for spec in DEPTH_MODELS.values()]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _depth_root() -> Path:
    ensure_runtime_dirs()
    root = CACHE_DIR / "depth"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _source_digest(image: Image.Image) -> str:
    rgb = image.convert("RGB")
    digest = hashlib.sha256()
    digest.update(f"{rgb.width}x{rgb.height}:RGB".encode("utf-8"))
    digest.update(rgb.tobytes())
    return digest.hexdigest()


def _cache_key(image: Image.Image, spec: DepthModelSpec) -> str:
    digest = hashlib.sha256()
    digest.update(f"morphorum-depth-v{DEPTH_CACHE_VERSION}\n".encode("utf-8"))
    digest.update(spec.repo_id.encode("utf-8"))
    digest.update(b"\n")
    digest.update(_source_digest(image).encode("ascii"))
    return digest.hexdigest()


def _cache_paths(cache_key: str) -> dict[str, Path]:
    if len(cache_key) != 64 or any(ch not in "0123456789abcdef" for ch in cache_key):
        raise DepthError("Invalid depth cache key.")
    base = _depth_root() / cache_key
    return {
        "data": base.with_suffix(".npz"),
        "preview": base.with_suffix(".png"),
        "metadata": base.with_suffix(".json"),
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


class DepthManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._model: Any = None
        self._processor: Any = None
        self._loaded_model_id: str | None = None
        self._device: str | None = None
        self._last_result: dict[str, Any] | None = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "loaded": self._model is not None,
                "model_id": self._loaded_model_id,
                "device": self._device,
                "last_result": dict(self._last_result) if self._last_result else None,
            }

    def _resolve_spec(self, model_id: str | None) -> DepthModelSpec:
        key = str(model_id or DEFAULT_DEPTH_MODEL).strip().lower()
        spec = DEPTH_MODELS.get(key)
        if spec is None:
            raise DepthError(
                f"Unknown depth model '{key}'. Available: {', '.join(DEPTH_MODELS)}."
            )
        return spec

    @staticmethod
    def _resolve_device(requested: str | None) -> str:
        value = str(requested or "auto").strip().lower()
        if value not in {"auto", "cuda", "cpu"}:
            raise DepthError("Depth device must be auto, cuda, or cpu.")
        try:
            import torch
        except Exception as exc:
            raise DepthError(f"PyTorch is required for depth estimation: {exc}") from exc
        if value == "cuda":
            if not torch.cuda.is_available():
                raise DepthError("CUDA depth inference was requested but CUDA is unavailable.")
            return "cuda"
        if value == "cpu":
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def load(self, model_id: str | None = None, *, device: str = "auto") -> dict[str, Any]:
        spec = self._resolve_spec(model_id)
        resolved_device = self._resolve_device(device)
        with self._lock:
            if (
                self._model is not None
                and self._loaded_model_id == spec.id
                and self._device == resolved_device
            ):
                return self.status()

            self.unload()
            emit_console(
                "info",
                "depth",
                f"Loading {spec.label} on {resolved_device}.",
            )
            try:
                import torch
                from transformers import AutoImageProcessor, AutoModelForDepthEstimation

                processor = AutoImageProcessor.from_pretrained(spec.repo_id)
                model = AutoModelForDepthEstimation.from_pretrained(spec.repo_id)
                model.eval()
                model.to(resolved_device)
            except Exception as exc:
                self._model = None
                self._processor = None
                self._loaded_model_id = None
                self._device = None
                raise DepthError(f"Could not load {spec.label}: {exc}") from exc

            self._processor = processor
            self._model = model
            self._loaded_model_id = spec.id
            self._device = resolved_device
            emit_console(
                "info",
                "depth",
                f"{spec.label} ready on {resolved_device}.",
            )
            return self.status()

    def unload(self) -> None:
        with self._lock:
            had_model = self._model is not None
            self._model = None
            self._processor = None
            self._loaded_model_id = None
            self._device = None
            if had_model:
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
                emit_console("info", "depth", "Depth estimator unloaded.")

    @staticmethod
    def _normalize_depth(raw_depth: np.ndarray) -> tuple[np.ndarray, float, float]:
        depth = np.asarray(raw_depth, dtype=np.float32)
        if depth.ndim != 2:
            depth = np.squeeze(depth)
        if depth.ndim != 2:
            raise DepthError(f"Depth estimator returned unexpected shape {depth.shape!r}.")
        if not np.isfinite(depth).all():
            raise DepthError("Depth estimator returned non-finite values.")

        minimum = float(depth.min())
        maximum = float(depth.max())
        span = maximum - minimum
        if span <= 1e-12:
            normalized = np.zeros_like(depth, dtype=np.float32)
        else:
            normalized = ((depth - minimum) / span).astype(np.float32, copy=False)
        return normalized, minimum, maximum

    def _run_inference(
        self,
        image: Image.Image,
        *,
        model_id: str,
        device: str,
    ) -> tuple[np.ndarray, str]:
        self.load(model_id, device=device)
        with self._lock:
            model = self._model
            processor = self._processor
            resolved_device = str(self._device or "cpu")
        if model is None or processor is None:
            raise DepthError("Depth estimator is not loaded.")

        try:
            import torch

            rgb = image.convert("RGB")
            inputs = processor(images=rgb, return_tensors="pt")
            inputs = {
                key: value.to(resolved_device) if hasattr(value, "to") else value
                for key, value in inputs.items()
            }
            with torch.inference_mode():
                outputs = model(**inputs)
            processed = processor.post_process_depth_estimation(
                outputs,
                target_sizes=[(rgb.height, rgb.width)],
            )
            predicted = processed[0]["predicted_depth"]
            if hasattr(predicted, "detach"):
                predicted = predicted.detach()
            if hasattr(predicted, "float"):
                predicted = predicted.float()
            if hasattr(predicted, "cpu"):
                predicted = predicted.cpu()
            raw = np.asarray(predicted, dtype=np.float32)
            return raw, resolved_device
        except Exception as exc:
            raise DepthError(f"Depth inference failed: {exc}") from exc

    def estimate(
        self,
        image: Image.Image,
        *,
        model_id: str | None = None,
        device: str = "auto",
        force: bool = False,
        release_after: bool = True,
    ) -> dict[str, Any]:
        spec = self._resolve_spec(model_id)
        rgb = image.convert("RGB")
        cache_key = _cache_key(rgb, spec)
        paths = _cache_paths(cache_key)

        if not force and all(path.is_file() for path in paths.values()):
            try:
                metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
            result = {
                **metadata,
                "cache_key": cache_key,
                "cache_hit": True,
                "data_path": str(paths["data"]),
                "preview_path": str(paths["preview"]),
                "metadata_path": str(paths["metadata"]),
            }
            with self._lock:
                self._last_result = dict(result)
            emit_console("info", "depth", f"Depth cache hit {cache_key[:12]}.")
            return result

        emit_console("info", "depth", f"Estimating depth for {rgb.width}x{rgb.height} image.")
        try:
            raw, resolved_device = self._run_inference(
                rgb,
                model_id=spec.id,
                device=device,
            )
            normalized, raw_min, raw_max = self._normalize_depth(raw)
            np.savez_compressed(
                paths["data"],
                raw=raw.astype(np.float32, copy=False),
                normalized=normalized,
            )
            preview = Image.fromarray(
                np.clip(np.rint(normalized * 255.0), 0, 255).astype(np.uint8),
                mode="L",
            )
            preview.save(paths["preview"], format="PNG")

            metadata = {
                "cache_version": DEPTH_CACHE_VERSION,
                "cache_key": cache_key,
                "model_id": spec.id,
                "model_label": spec.label,
                "repo_id": spec.repo_id,
                "depth_type": spec.depth_type,
                "device": resolved_device,
                "width": int(rgb.width),
                "height": int(rgb.height),
                "raw_min": raw_min,
                "raw_max": raw_max,
                "normalized_min": float(normalized.min()),
                "normalized_max": float(normalized.max()),
                "convention": "relative inverse depth; larger values are nearer",
                "preview_convention": "white=near, black=far",
                "source_sha256": _source_digest(rgb),
                "created_at": _utc_now(),
            }
            _write_json_atomic(paths["metadata"], metadata)
            result = {
                **metadata,
                "cache_hit": False,
                "data_path": str(paths["data"]),
                "preview_path": str(paths["preview"]),
                "metadata_path": str(paths["metadata"]),
            }
            with self._lock:
                self._last_result = dict(result)
            emit_console(
                "info",
                "depth",
                f"Depth estimate cached as {cache_key[:12]} ({resolved_device}).",
            )
            return result
        finally:
            if release_after:
                self.unload()

    def cached(self, cache_key: str) -> dict[str, Any] | None:
        paths = _cache_paths(cache_key)
        if not all(path.is_file() for path in paths.values()):
            return None
        try:
            metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return {
            **metadata,
            "cache_key": cache_key,
            "cache_hit": True,
            "data_path": str(paths["data"]),
            "preview_path": str(paths["preview"]),
            "metadata_path": str(paths["metadata"]),
        }

    def preview_path(self, cache_key: str) -> Path:
        path = _cache_paths(cache_key)["preview"]
        if not path.is_file():
            raise DepthError("Depth preview is not cached.")
        return path


depth_manager = DepthManager()

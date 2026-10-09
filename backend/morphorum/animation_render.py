from __future__ import annotations

import gc
import json
import random
import shutil
import threading
import time
import uuid
from copy import deepcopy
from functools import wraps
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from PIL.PngImagePlugin import PngInfo

from .animation_3d import Camera3DError, render_depth_warp, reverse_camera_chain
from .animation_depth import DepthError, depth_manager
from .animation_hybrid_render import (
    HybridRenderError, freeze_hybrid_source, frozen_hybrid_frame,
)
from .animation_motion import (
    _frame_transform_matrix,
    capture_frames,
    render_affine,
)
from .animation_resolution import resolve_project_frame, validate_project_schedules
from .animation_temporal import blend_future_anchor
from .animation_performance import (
    AnimationPerformance, append_performance_record, load_performance_records,
    performance_record, summarize_records,
)
from .console import emit_console
from .generation import GenerationError, GenerationRequest, generation_manager
from .loras import lora_catalog
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


def _detach_conditioning_to_cpu(value: Any):
    try:
        import torch
    except Exception:
        torch = None

    if torch is not None and isinstance(value, torch.Tensor):
        return value.detach().to("cpu")
    if isinstance(value, list):
        return [_detach_conditioning_to_cpu(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_detach_conditioning_to_cpu(item) for item in value)
    return value


# Multiple LoRA weights and keyframed prompts can create a distinct conditioning
# cache key on each animation anchor. Retain only the most recent small set of
# embeddings; old entries otherwise keep CUDA tensors (and potentially autograd
# graphs) alive across the entire render.
MAX_CONDITIONING_CACHE_ENTRIES = 8


def _inference_only_conditioning(function):
    """Diffusers encode_prompt() is not itself decorated with no_grad.

    Pipeline.__call__() wraps its own inference in no_grad, but our animation
    renderer encodes blended prompts *before* entering pipeline.__call__.
    Without this guard, encoding a new prompt for every LoRA strength can
    retain a whole CLIP forward graph in conditioning_cache each frame.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        import torch

        with torch.inference_mode():
            return function(*args, **kwargs)

    return wrapped


def _cache_conditioning_value(
    cache: dict[tuple[Any, ...], Any] | None,
    key: tuple[Any, ...],
    value: Any,
) -> None:
    if cache is None:
        return
    while len(cache) >= MAX_CONDITIONING_CACHE_ENTRIES:
        cache.pop(next(iter(cache)))
    cache[key] = value


@_inference_only_conditioning
def _prompt_conditioning_kwargs(
    pipe: Any,
    family: str,
    positive: dict[str, Any],
    negative: dict[str, Any],
    *,
    guidance_scale: float,
    max_sequence_length: int = 512,
    conditioning_cache: dict[tuple[Any, ...], Any] | None = None,
    cache_zimage_on_cpu: bool = False,
    lora_signature: tuple[Any, ...] = (),
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

            def sdxl_encoded(prompt_text: str, negative_text: str):
                key = (
                    "sdxl",
                    prompt_text,
                    negative_text,
                    bool(do_cfg),
                    tuple(lora_signature),
                )
                if conditioning_cache is not None and key in conditioning_cache:
                    return conditioning_cache[key]
                encoded = pipe.encode_prompt(
                    prompt=prompt_text,
                    negative_prompt=negative_text or None,
                    num_images_per_prompt=1,
                    do_classifier_free_guidance=do_cfg,
                )
                _cache_conditioning_value(conditioning_cache, key, encoded)
                return encoded

            first = sdxl_encoded(from_prompt, from_negative)
            second = sdxl_encoded(to_prompt, to_negative)
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
            def flux_encoded(prompt_text: str):
                key = (
                    "flux",
                    prompt_text,
                    int(max_sequence_length),
                    tuple(lora_signature),
                )
                if conditioning_cache is not None and key in conditioning_cache:
                    return conditioning_cache[key]
                encoded = pipe.encode_prompt(
                    prompt=prompt_text,
                    num_images_per_prompt=1,
                    max_sequence_length=max_sequence_length,
                )
                _cache_conditioning_value(conditioning_cache, key, encoded)
                return encoded

            first = flux_encoded(from_prompt)
            second = flux_encoded(to_prompt)
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
            def zimage_embeds(prompt_text: str):
                key = (
                    "zimage",
                    prompt_text,
                    int(max_sequence_length),
                    tuple(lora_signature),
                )
                if conditioning_cache is not None and key in conditioning_cache:
                    return conditioning_cache[key]

                encoded = pipe.encode_prompt(
                    prompt=prompt_text,
                    do_classifier_free_guidance=False,
                    max_sequence_length=max_sequence_length,
                )[0]
                if cache_zimage_on_cpu:
                    encoded = _detach_conditioning_to_cpu(encoded)
                    generation_manager.release_inference_memory()

                _cache_conditioning_value(conditioning_cache, key, encoded)
                return encoded

            first = zimage_embeds(from_prompt)
            second = zimage_embeds(to_prompt)
            return {
                "prompt": None,
                "prompt_embeds": _blend_value(
                    first, second, positive_to_weight
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


def _resolved_lora_signature(resolved: dict[str, Any]) -> tuple[Any, ...]:
    values = []
    for item in resolved.get("loras", []) if isinstance(resolved, dict) else []:
        if not isinstance(item, dict):
            continue
        values.append((
            str(item.get("id") or item.get("adapter_name") or item.get("name") or ""),
            round(float(item.get("weight", 1.0)), 6),
        ))
    return tuple(values)


def _prompt_state_for_frame(
    resolved: dict[str, Any],
    *,
    applied: bool,
    reason: str | None = None,
) -> dict[str, Any]:
    prompts = resolved.get("prompts", {}) if isinstance(resolved, dict) else {}
    positive = prompts.get("positive", {}) if isinstance(prompts, dict) else {}
    negative = prompts.get("negative", {}) if isinstance(prompts, dict) else {}

    def transition(value: Any) -> dict[str, Any]:
        source = value if isinstance(value, dict) else {}
        return {
            "mode": str(source.get("mode") or "blend"),
            "from_frame": int(source.get("from_frame") or 0),
            "to_frame": int(source.get("to_frame") or 0),
            "from_text": str(source.get("from_text") or ""),
            "to_text": str(source.get("to_text") or ""),
            "from_weight": float(source.get("from_weight") or 0.0),
            "to_weight": float(source.get("to_weight") or 0.0),
        }

    return {
        "frame": int(resolved.get("frame") or 0),
        "applied": bool(applied),
        "reason": reason,
        "positive": transition(positive),
        "negative": transition(negative),
        "loras": deepcopy(resolved.get("loras", [])),
    }


def _transform_telemetry(
    matrix: np.ndarray,
    *,
    width: int,
    height: int,
) -> dict[str, Any]:
    transform = np.asarray(matrix, dtype=np.float64)
    center = np.array(
        [(width - 1) / 2.0, (height - 1) / 2.0, 1.0],
        dtype=np.float64,
    )
    mapped_center = transform @ center
    scale = float(np.hypot(transform[0, 0], transform[1, 0]))
    rotation = float(np.degrees(np.arctan2(transform[1, 0], transform[0, 0])))
    return {
        "zoom": scale,
        "rotation_degrees": rotation,
        "center_offset_x": float(mapped_center[0] - center[0]),
        "center_offset_y": float(mapped_center[1] - center[1]),
        "matrix": [
            [float(value) for value in row]
            for row in transform.tolist()
        ],
    }


def _frame_state_for_frame(
    resolved: dict[str, Any],
    *,
    seed: int,
    diffusion_mode: str,
    motion_applied: bool,
    cumulative_matrix: np.ndarray,
    depth_state: dict[str, Any] | None = None,
    cadence_state: dict[str, Any] | None = None,
    timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    motion = resolved.get("motion", {})
    generation = resolved.get("generation", {})
    retention_strength = float(generation.get("strength", 0.0))
    denoise_strength = (
        1.0 - retention_strength
        if diffusion_mode in {"img2img", "transform-only", "cadence-transform"}
        else None
    )
    dimensions = resolved.get("dimensions", {})
    width = int(dimensions.get("width") or 1)
    height = int(dimensions.get("height") or 1)
    seed_state = generation.get("seed", {})
    camera_3d = resolved.get("camera_3d", {})
    animation_mode = str(resolved.get("animation_mode") or "2d")
    return {
        "frame": int(resolved.get("frame") or 0),
        "animation_mode": animation_mode,
        "motion_applied": bool(motion_applied),
        "motion": {
            "angle": float(motion.get("angle", 0.0)),
            "zoom": float(motion.get("zoom", 1.0)),
            "translation_x": float(motion.get("translation_x", 0.0)),
            "translation_y": float(motion.get("translation_y", 0.0)),
            "border_mode": str(motion.get("border_mode") or "replicate"),
        },
        "cumulative_2d": _transform_telemetry(
            cumulative_matrix,
            width=width,
            height=height,
        ),
        "camera_3d": {
            "translation_x": float(camera_3d.get("translation_x", 0.0)),
            "translation_y": float(camera_3d.get("translation_y", 0.0)),
            "translation_z": float(camera_3d.get("translation_z", 0.0)),
            "rotation_x": float(camera_3d.get("rotation_x", 0.0)),
            "rotation_y": float(camera_3d.get("rotation_y", 0.0)),
            "rotation_z": float(camera_3d.get("rotation_z", 0.0)),
            "fov": float(camera_3d.get("fov", 40.0)),
            "projection_mode": str(camera_3d.get("projection_mode") or "legacy"),
            "hole_fill": str(camera_3d.get("hole_fill") or "nearest"),
        },
        "depth_3d": deepcopy(depth_state) if depth_state else None,
        "cadence": deepcopy(cadence_state) if cadence_state else {
            "diffusion": int(resolved.get("cadence", {}).get("diffusion", 1) or 1),
            "anchor": True,
        },
        "timings": deepcopy(timings) if timings else {},
        "generation": {
            "strength": retention_strength,
            "denoise_strength": denoise_strength,
            "noise": float(generation.get("noise", 0.0)),
            "steps": int(generation.get("steps", 1)),
            "guidance": float(generation.get("guidance", 0.0)),
            "sampler": str(generation.get("sampler") or ""),
            "seed": int(seed),
            "seed_behavior": str(seed_state.get("behavior") or "fixed"),
            "seed_increment": int(seed_state.get("increment") or 0),
            "random_at_render": bool(seed_state.get("random_at_render")),
            "diffusion_mode": str(diffusion_mode),
        },
    }


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


def _prepare_depth_input(
    image: Image.Image,
    setting: str,
) -> tuple[Image.Image, str]:
    raw = str(setting or "auto").strip().lower()
    maximum = max(image.size)
    if raw == "full":
        return image, "full"
    if raw == "auto":
        target = min(512, maximum)
        label = "auto"
    else:
        try:
            target = max(128, min(2048, int(raw)))
        except (TypeError, ValueError):
            target = min(512, maximum)
            label = "auto"
        else:
            label = str(target)

    if maximum <= target:
        return image, label

    scale = target / maximum
    resized = image.resize(
        (
            max(2, int(round(image.width * scale))),
            max(2, int(round(image.height * scale))),
        ),
        Image.Resampling.BILINEAR,
    )
    return resized, label


def _resize_depth_map(
    depth: np.ndarray,
    *,
    width: int,
    height: int,
) -> np.ndarray:
    value = np.asarray(depth, dtype=np.float32)
    if value.shape == (height, width):
        return value
    depth_image = Image.fromarray(value, mode="F")
    resized = depth_image.resize((width, height), Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32)


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
    image.save(
        temp,
        format="PNG",
        pnginfo=pnginfo,
        compress_level=1,
        optimize=False,
    )
    temp.replace(path)


def _last_diffused_anchor(
    project_id: str, render_id: str, before_frame: int,
) -> int:
    """Resume-safe: determine which already saved frame last ran diffusion."""
    for frame in range(before_frame - 1, 0, -1):
        path = _frame_path(project_id, render_id, frame)
        if not path.is_file():
            continue
        with Image.open(path) as opened:
            try:
                metadata = json.loads(opened.info.get("Morphorum", "{}"))
            except (ValueError, TypeError):
                continue
        state = metadata.get("render_state") or {}
        if (state.get("generation") or {}).get("diffusion_mode") == "img2img":
            return frame
    return 0


def _tween_between_depth_anchors(
    job: "AnimationRenderJob",
    *,
    previous_anchor: int,
    future_anchor: int,
    future_image: Image.Image,
    depth_resolution_setting: str,
    lora_records: list[dict[str, Any]] | None,
) -> int:
    """Refine already-rendered cadence frames after the next anchor exists.

    Does not modify the forward input used for subsequent diffusion. Runs on
    CPU only; depth of the future anchor is computed once and cached on disk.
    Every changed PNG is written atomically, retaining frame metadata.
    """
    distance = future_anchor - previous_anchor
    if distance <= 1:
        return 0
    if distance > 32:
        emit_console(
            "warning", "animation",
            f"{job.id}: skipping temporal tween over {distance} frames; "
            "maximum supported anchor gap is 32.",
        )
        return 0

    width = future_image.width
    height = future_image.height
    depth_input, _label = _prepare_depth_input(
        future_image, depth_resolution_setting,
    )
    result = depth_manager.estimate(
        depth_input, device="cpu", release_after=False,
    )
    depth = _resize_depth_map(
        depth_manager.load_cached_array(str(result["cache_key"])),
        width=width, height=height,
    )
    camera_states = {
        index: resolve_project_frame(
            job.project, index, lora_records=lora_records,
        )["camera_3d"]
        for index in range(previous_anchor + 1, future_anchor + 1)
    }
    source_camera = camera_states[future_anchor]
    settings = job.project.get("temporal") or {}
    mix = float(settings.get("mix", 0.65))
    contrast = float(settings.get("contrast_threshold", 96.0))

    # Complete all calculations before replacing any PNG. If reprojection
    # fails, preserve the entire forward-only segment.
    changes: list[tuple[Path, Image.Image, dict[str, Any]]] = []
    for frame in range(previous_anchor + 1, future_anchor):
        matrix, offset = reverse_camera_chain([
            camera_states[index]
            for index in range(frame + 1, future_anchor + 1)
        ])
        camera = camera_states[frame]
        projected = render_depth_warp(
            future_image,
            depth,
            source_fov=float(source_camera["fov"]),
            fov=float(camera["fov"]),
            projection_mode="splat",
            fill_mode="nearest",
            transform_matrix=matrix,
            transform_offset=offset,
        )
        path = _frame_path(job.project_id, job.id, frame)
        with Image.open(path) as opened:
            forward_image = opened.convert("RGB").copy()
            metadata = json.loads(opened.info["Morphorum"])
        mask_path = _render_dir(job.project_id, job.id) / "masks" / f"frame_{frame:06d}.png"
        forward_holes = None
        if mask_path.is_file():
            with Image.open(mask_path) as mask_opened:
                forward_holes = mask_opened.convert("L").copy()

        blend = blend_future_anchor(
            forward_image,
            projected.image,
            future_holes=projected.hole_mask,
            forward_holes=forward_holes,
            position=(frame - previous_anchor) / distance,
            mix=mix,
            contrast_threshold=contrast,
        )
        metadata.setdefault("render_state", {})["temporal"] = {
            "mode": "future-anchor",
            "previous_anchor": previous_anchor,
            "future_anchor": future_anchor,
            "mix": mix,
            "contrast_threshold": contrast,
            "fraction_blended": blend.fraction_blended,
            "fraction_repaired": blend.fraction_replaced,
            "average_weight": blend.average_weight,
            "future_coverage": projected.telemetry["projected_coverage"],
        }
        changes.append((path, blend.image, metadata))
    for path, image, metadata in changes:
        _save_frame(image, path, metadata=metadata)
    return len(changes)


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
    current_step_total: int = 0
    total_frames: int = 0
    progress: float = 0.0
    eta_seconds: float | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False
    model_load_seconds: float | None = None
    load_progress: float = 0.0
    load_phase: str = ""
    load_message: str = ""
    load_detail: str | None = None
    frame_seconds: float | None = None
    average_frame_seconds: float | None = None
    preview: dict[str, Any] | None = None
    current_prompt_state: dict[str, Any] = field(default_factory=dict)
    current_frame_state: dict[str, Any] = field(default_factory=dict)
    resumed: bool = False
    performance: dict[str, Any] = field(default_factory=dict)
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
        snapshot = self.project.get("_hybrid_snapshot")
        payload["hybrid_source"] = (
            {"enabled": True, "mode": "anchor-init",
             "source_fps": snapshot["source_fps"], "source_frames": snapshot["source_frames"]}
            if isinstance(snapshot, dict) and snapshot.get("enabled")
            else {"enabled": False}
        )
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
        records: list[dict[str, Any]] | None = None
        positive_prompts = project.get("prompts", {})
        has_lora_tags = any(
            "<lora:" in str(value or "").lower()
            for value in (
                positive_prompts.values()
                if isinstance(positive_prompts, dict)
                else []
            )
        )
        if has_lora_tags:
            records = lora_catalog()

        for frame in range(total):
            resolved = resolve_project_frame(
                project,
                frame,
                lora_records=records,
            )
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
        if (start_mode == "source"
                and not project.get("hybrid", {}).get("enabled")
                and not source_path.is_file()):
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

        try:
            seed_plan = self._resolve_seed_plan(project)
            snapshot = freeze_hybrid_source(project, output_dir)
        except (HybridRenderError, OSError, ValueError):
            # Submission must not leave incomplete snapshots/output folders.
            shutil.rmtree(output_dir, ignore_errors=True)
            raise
        job = AnimationRenderJob(
            id=render_id,
            project_id=project_id,
            project=deepcopy(project),
            seed_plan=seed_plan,
            total_frames=int(project["animation"]["max_frames"]),
        )
        job.project.setdefault("_render_model_snapshot", deepcopy(model))
        if snapshot is not None:
            job.project["_hybrid_snapshot"] = snapshot
            emit_console("info", "animation",
                f"{render_id}: frozen {snapshot['source_frames']} extracted frame references "
                f"({snapshot['source_fps']:g} FPS) for hybrid anchor input.")
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
            load_progress=float(payload.get("load_progress") or 0.0),
            load_phase=str(payload.get("load_phase") or ""),
            load_message=str(payload.get("load_message") or ""),
            load_detail=payload.get("load_detail"),
            current_prompt_state=deepcopy(payload.get("current_prompt_state") or {}),
            current_frame_state=deepcopy(payload.get("current_frame_state") or {}),
            performance=deepcopy(payload.get("performance") or {}),
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

    def performance_report(self, project_id: str, render_id: str) -> dict[str, Any]:
        """Diagnostics for existing renders, including interrupted runs."""
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", project_id) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,100}", render_id
        ):
            raise AnimationRenderError("Invalid project or render identifier.")
        path = _manifest_path(project_id, render_id)
        if not path.is_file():
            raise AnimationRenderError("Animation render manifest not found.")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AnimationRenderError("Animation render manifest is unreadable.") from exc
        if manifest.get("project_id") != project_id or manifest.get("id") != render_id:
            raise AnimationRenderError("Render identity mismatch.")
        try:
            records = load_performance_records(
                _render_dir(project_id, render_id) / "performance.jsonl"
            )
        except OSError as exc:
            raise AnimationRenderError(f"Could not read performance records: {exc}") from exc
        return {
            "project_id": project_id,
            "render_id": render_id,
            "status": manifest.get("status"),
            "summary": summarize_records(records),
            "frames": records,
        }

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
        animation_mode = str(animation.get("mode", "2d") or "2d").strip().lower()
        if animation_mode not in {"2d", "3d"}:
            animation_mode = "2d"
        depth_resolution_setting = str(
            project.get("camera_3d", {}).get("depth_resolution") or "auto"
        ).strip().lower()

        load_started = time.monotonic()
        pipe = None
        generator_device = "cpu"
        conditioning_cache: dict[tuple[Any, ...], Any] = {}
        lora_records: list[dict[str, Any]] | None = None
        positive_prompts = project.get("prompts", {})
        if any(
            "<lora:" in str(value or "").lower()
            for value in (
                positive_prompts.values()
                if isinstance(positive_prompts, dict)
                else []
            )
        ):
            lora_records = lora_catalog()

        def on_model_load(
            progress: float,
            phase: str,
            message: str,
            detail: str | None = None,
        ) -> None:
            with self._lock:
                job.status = "loading_model"
                job.load_progress = max(0.0, min(1.0, float(progress)))
                job.load_phase = str(phase)
                job.load_message = str(message)
                job.load_detail = detail
                job.message = str(message)

        render_dir = _render_dir(job.project_id, job.id)
        performance_path = render_dir / "performance.jsonl"
        # Keep a bounded summary in the render manifest, and a detailed
        # per-frame diagnostic sidecar that survives cancellation/restart.
        performance_tracker = AnimationPerformance()
        try:
            for prior_record in load_performance_records(performance_path):
                if int(prior_record.get("frame", -1)) < start_frame:
                    performance_tracker.observe(prior_record)
        except OSError as exc:
            emit_console("warning", "animation", f"{job.id}: previous performance records unavailable: {exc}")
        job.performance = performance_tracker.public()
        copied_source = render_dir / "source.png"
        hybrid_snapshot = project.get("_hybrid_snapshot")
        if project.get("hybrid", {}).get("enabled") and not hybrid_snapshot:
            raise AnimationRenderError("Hybrid render snapshot is missing; refusing to use live source frames.")

        cumulative_matrix = np.eye(3, dtype=np.float64)
        if animation_mode == "2d" and start_frame > 1:
            for completed_frame in range(1, start_frame):
                prior_resolved = resolve_project_frame(
                    project,
                    completed_frame,
                    lora_records=lora_records,
                )
                prior_motion = prior_resolved["motion"]
                prior_step = _frame_transform_matrix(
                    width=width,
                    height=height,
                    angle=float(prior_motion["angle"]),
                    zoom=float(prior_motion["zoom"]),
                    translation_x=float(prior_motion["translation_x"]),
                    translation_y=float(prior_motion["translation_y"]),
                )
                cumulative_matrix = prior_step @ cumulative_matrix

        if start_frame == 0:
            resolved = resolve_project_frame(project, 0, lora_records=lora_records)
            seed = int(job.seed_plan[0])

            hybrid_first = frozen_hybrid_frame(hybrid_snapshot, render_dir, 0)
            if hybrid_first is not None:
                hybrid_path, hybrid_info = hybrid_first
                with self._lock:
                    job.current_prompt_state = _prompt_state_for_frame(
                        resolved, applied=False,
                        reason="Hybrid frame 0 uses extracted source video; diffusion begins at later anchors.",
                    )
                    job.current_frame_state = _frame_state_for_frame(
                        resolved, seed=seed, diffusion_mode="hybrid-source",
                        motion_applied=False, cumulative_matrix=cumulative_matrix,
                    )
                    job.current_frame_state["hybrid_source"] = {**hybrid_info, "applied": True}
                with Image.open(hybrid_path) as opened:
                    frame_image = _prepare_source(opened, width, height)
                start_metadata = {
                    "source_frame": True, "generated_start": False,
                    "hybrid_source": {**hybrid_info, "applied": True},
                }
                job.message = f"Prepared hybrid source frame 1 of {total}"
            elif start_mode == "source":
                with self._lock:
                    job.current_prompt_state = _prompt_state_for_frame(
                        resolved,
                        applied=False,
                        reason="Frame 0 uses the uploaded starting image; diffusion is not applied.",
                    )
                    job.current_frame_state = _frame_state_for_frame(
                        resolved,
                        seed=seed,
                        diffusion_mode="source",
                        motion_applied=False,
                        cumulative_matrix=cumulative_matrix,
                    )
                with Image.open(copied_source) as opened:
                    frame_image = _prepare_source(opened, width, height)
                start_metadata = {
                    "source_frame": True,
                    "generated_start": False,
                }
                job.message = f"Prepared starting image frame 1 of {total}"
            else:
                with self._lock:
                    job.current_prompt_state = _prompt_state_for_frame(
                        resolved,
                        applied=True,
                    )
                    job.current_frame_state = _frame_state_for_frame(
                        resolved,
                        seed=seed,
                        diffusion_mode="txt2img",
                        motion_applied=False,
                        cumulative_matrix=cumulative_matrix,
                    )
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
                    loras=deepcopy(resolved.get("loras", [])),
                )

                with self._lock:
                    job.status = "loading_model"
                    job.current_frame = 0
                    job.current_step = 0
                    job.current_step_total = steps
                    job.message = f"Loading model for starting frame 1 of {total}"

                pipe, generator_device, validated_model = (
                    generation_manager.prepare_txt2img(
                        request,
                        on_model_load,
                    )
                )
                job.model_load_seconds = max(
                    0.0,
                    time.monotonic() - load_started,
                )
                with self._lock:
                    job.status = "rendering"
                    job.load_progress = 1.0
                    job.load_phase = "ready"
                    job.load_message = "Model pipeline ready"
                    job.message = f"Generating starting frame 1 of {total}"
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
                    conditioning_cache=conditioning_cache,
                    cache_zimage_on_cpu=(
                        family == "zimage"
                        and generation_manager.pipeline_optimization()
                        in {
                            "bf16-conservative-group-offload",
                            "bf16-streamed-group-offload",
                        }
                    ),
                    lora_signature=_resolved_lora_signature(resolved),
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
                del result, call_args, conditioning, generator
                pipe = None
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
                    "render_state": deepcopy(job.current_frame_state),
                },
            )
            job.results = [
                {
                    "frame": 0,
                    "seed": seed,
                    "filename": path.name,
                    "path": str(path),
                    **({"hybrid_source": start_metadata["hybrid_source"]}
                       if hybrid_first is not None else {}),
                }
            ]
            job.current_frame = 0
            used_txt2img = start_mode == "prompt" and hybrid_first is None
            job.current_step = int(resolved["generation"]["steps"]) if used_txt2img else 0
            job.current_step_total = int(resolved["generation"]["steps"]) if used_txt2img else 0
            job.progress = 1 / total
            job.message = f"Starting frame 1 of {total} complete"
            self._write_manifest(job)
            emit_console(
                "info",
                "animation",
                f"{job.id}: starting frame 0 complete using "
                f"{'hybrid-source' if hybrid_first is not None else start_mode} mode.",
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

        previous_diffusion_anchor = _last_diffused_anchor(
            job.project_id, job.id, start_frame,
        )
        previous_camera_fov = 40.0
        if animation_mode == "3d" and start_frame > 0:
            previous_resolved = resolve_project_frame(
                project,
                start_frame - 1,
                lora_records=lora_records,
            )
            previous_camera_fov = float(
                previous_resolved.get("camera_3d", {}).get("fov", 40.0)
            )

        for frame in range(start_frame, total):
            # Read-only allocator snapshot; never synchronize or clear CUDA
            # caches in the hot frame loop just to collect diagnostics.
            cuda_before = generation_manager.cuda_memory_status()
            phase_memory: dict[str, dict[str, Any] | None] = {
                "frame_start": cuda_before,
            }
            if job.cancel_requested:
                self._cancel(job)
                return

            frame_started = time.monotonic()
            timings: dict[str, float] = {}
            resolve_started = time.monotonic()
            resolved = resolve_project_frame(project, frame, lora_records=lora_records)
            timings["resolve"] = max(0.0, time.monotonic() - resolve_started)
            depth_state: dict[str, Any] | None = None
            if animation_mode == "3d":
                try:
                    depth_input, depth_resolution_label = _prepare_depth_input(
                        frame_image,
                        depth_resolution_setting,
                    )
                    depth_started = time.monotonic()
                    depth_result = depth_manager.estimate(
                        depth_input,
                        device="cpu",
                        release_after=False,
                    )
                    depth_map = depth_manager.load_cached_array(
                        str(depth_result["cache_key"])
                    )
                    timings["depth"] = max(0.0, time.monotonic() - depth_started)

                    depth_map = _resize_depth_map(
                        depth_map,
                        width=width,
                        height=height,
                    )
                    camera = resolved["camera_3d"]
                    warp_started = time.monotonic()
                    warp = render_depth_warp(
                        frame_image,
                        depth_map,
                        translation_x=float(camera["translation_x"]),
                        translation_y=float(camera["translation_y"]),
                        translation_z=float(camera["translation_z"]),
                        rotation_x=float(camera["rotation_x"]),
                        rotation_y=float(camera["rotation_y"]),
                        rotation_z=float(camera["rotation_z"]),
                        fov=float(camera["fov"]),
                        source_fov=previous_camera_fov,
                        projection_mode=str(camera.get("projection_mode") or "legacy"),
                        fill_mode=str(camera.get("hole_fill") or "nearest"),
                    )
                    timings["warp"] = max(0.0, time.monotonic() - warp_started)
                    previous_camera_fov = float(camera["fov"])
                    transformed = warp.image
                    mask_path = _render_dir(job.project_id, job.id) / "masks" / f"frame_{frame:06d}.png"
                    if warp.hole_mask is not None:
                        mask_path.parent.mkdir(parents=True, exist_ok=True)
                        warp.hole_mask.save(mask_path)
                    depth_state = {
                        "disocclusion_mask": (
                            f"masks/frame_{frame:06d}.png" if warp.hole_mask is not None else None
                        ),
                        "cache_key": str(depth_result["cache_key"]),
                        "cache_hit": bool(depth_result.get("cache_hit")),
                        "device": str(depth_result.get("device") or "cpu"),
                        "seconds": timings["depth"],
                        "internal_width": depth_input.width,
                        "internal_height": depth_input.height,
                        "resolution_setting": depth_resolution_label,
                        **warp.telemetry,
                    }
                except (DepthError, Camera3DError) as exc:
                    raise AnimationRenderError(
                        f"3D depth/camera warp failed at frame {frame}: {exc}"
                    ) from exc
            else:
                warp_started = time.monotonic()
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
                cumulative_matrix = step_matrix @ cumulative_matrix
                timings["warp"] = max(0.0, time.monotonic() - warp_started)

            generation = resolved["generation"]
            retention_strength = float(generation["strength"])
            if not 0.0 <= retention_strength <= 1.0:
                raise AnimationRenderError(
                    f"Frame {frame} strength resolved to {retention_strength:g}; "
                    "Deforum-style strength must be between 0 and 1."
                )
            denoise_strength = 1.0 - retention_strength
            cadence_value = max(
                1,
                int(resolved.get("cadence", {}).get("diffusion", 1) or 1),
            )
            cadence_anchor = (
                cadence_value <= 1
                or frame % cadence_value == 0
                or frame == total - 1
            )
            should_diffuse = denoise_strength > 0.0 and cadence_anchor
            cadence_state = {
                "diffusion": cadence_value,
                "anchor": bool(cadence_anchor),
                "phase": int(frame % cadence_value),
            }
            if should_diffuse:
                diffusion_mode = "img2img"
                prompt_reason = None
            elif denoise_strength <= 0.0:
                diffusion_mode = "transform-only"
                prompt_reason = (
                    "Retention strength is 1.0, so this frame skips diffusion."
                )
            else:
                diffusion_mode = "cadence-transform"
                prompt_reason = (
                    f"Diffusion cadence {cadence_value} skips this intermediate frame; "
                    "camera transform is applied without diffusion."
                )

            with self._lock:
                job.current_prompt_state = _prompt_state_for_frame(
                    resolved,
                    applied=should_diffuse,
                    reason=prompt_reason,
                )
                job.current_frame_state = _frame_state_for_frame(
                    resolved,
                    seed=int(job.seed_plan[frame]),
                    diffusion_mode=diffusion_mode,
                    motion_applied=True,
                    cumulative_matrix=cumulative_matrix,
                    depth_state=depth_state,
                    cadence_state=cadence_state,
                    timings=timings,
                )

            positive = resolved["prompts"]["positive"]
            negative = resolved["prompts"]["negative"]
            seed = int(job.seed_plan[frame])
            steps = int(generation["steps"])
            guidance = float(generation["guidance"])
            sampler = str(generation["sampler"])
            noise_amount = float(generation["noise"])
            noise_started = time.monotonic()
            if should_diffuse:
                transformed = _add_uniform_noise(
                    transformed,
                    amount=noise_amount,
                    seed=seed,
                )
            timings["noise"] = max(0.0, time.monotonic() - noise_started)

            with self._lock:
                job.status = "rendering"
                job.current_frame = frame
                job.current_step = 0
                job.current_step_total = 0
                job.message = f"Rendering frame {frame + 1} of {total}"

            if not should_diffuse:
                image = transformed
                timings["prepare"] = 0.0
                timings["conditioning"] = 0.0
                timings["diffusion"] = 0.0
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
                    loras=deepcopy(resolved.get("loras", [])),
                )

                prepare_started = time.monotonic()
                pipe, generator_device, validated_model = (
                    generation_manager.prepare_img2img(
                        request,
                        on_model_load,
                    )
                )
                timings["prepare"] = max(
                    0.0,
                    time.monotonic() - prepare_started,
                )
                phase_memory["post_prepare"] = generation_manager.cuda_memory_status()
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
                with self._lock:
                    job.status = "rendering"
                    job.load_progress = 1.0
                    job.load_phase = "ready"
                    job.load_message = "Model pipeline ready"
                    job.message = f"Rendering frame {frame + 1} of {total}"

                import torch

                generator = torch.Generator(
                    device=generator_device
                ).manual_seed(seed)

                effective_steps = max(1, int(round(steps * denoise_strength)))
                with self._lock:
                    job.current_step_total = effective_steps

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

                conditioning_started = time.monotonic()
                conditioning = _prompt_conditioning_kwargs(
                    pipe,
                    family,
                    positive,
                    negative,
                    guidance_scale=guidance,
                    max_sequence_length=int(
                        capability.get("max_sequence_length", 512)
                    ),
                    conditioning_cache=conditioning_cache,
                    cache_zimage_on_cpu=(
                        family == "zimage"
                        and generation_manager.pipeline_optimization()
                        in {
                            "bf16-conservative-group-offload",
                            "bf16-streamed-group-offload",
                        }
                    ),
                    lora_signature=_resolved_lora_signature(resolved),
                )
                timings["conditioning"] = max(
                    0.0,
                    time.monotonic() - conditioning_started,
                )
                phase_memory["post_conditioning"] = generation_manager.cuda_memory_status()
                call_args.update(conditioning)

                diffusion_started = time.monotonic()
                with torch.inference_mode():
                    result = pipe(**call_args)
                timings["diffusion"] = max(
                    0.0,
                    time.monotonic() - diffusion_started,
                )
                # This sample includes denoising plus the pipeline's VAE encode/decode
                # work. Deeper UNet/VAE separation will require family-specific hooks;
                # do not add per-step synchronization just for profiling.
                phase_memory["post_diffusion_decode"] = (
                    generation_manager.cuda_memory_status()
                )
                if job.cancel_requested:
                    self._cancel(job)
                    return
                if not result.images:
                    raise AnimationRenderError(
                        f"Img2img returned no image for frame {frame}."
                    )
                image = result.images[0].convert("RGB")
                del result, call_args, conditioning, generator

            with self._lock:
                job.current_frame_state["timings"] = deepcopy(timings)

            path = _frame_path(job.project_id, job.id, frame)
            save_started = time.monotonic()
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
                    "render_state": deepcopy(job.current_frame_state),
                },
            )
            timings["save"] = max(0.0, time.monotonic() - save_started)
            with self._lock:
                job.current_frame_state["timings"] = deepcopy(timings)

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

            job.current_frame = frame
            job.current_step = job.current_step_total if should_diffuse else 0
            job.progress = (frame + 1) / total
            job.message = f"Rendered frame {frame + 1} of {total}"

            manifest_started = time.monotonic()
            self._write_manifest(job)
            timings["manifest"] = max(
                0.0,
                time.monotonic() - manifest_started,
            )

            if (
                should_diffuse
                and animation_mode == "3d"
                and str(project.get("temporal", {}).get("mode") or "forward")
                == "future-anchor"
                and float(project.get("temporal", {}).get("mix", 0.0)) > 0
            ):
                tween_started = time.monotonic()
                try:
                    refined = _tween_between_depth_anchors(
                        job,
                        previous_anchor=previous_diffusion_anchor,
                        future_anchor=frame,
                        future_image=image,
                        depth_resolution_setting=depth_resolution_setting,
                        lora_records=lora_records,
                    )
                    if refined:
                        emit_console(
                            "info", "animation",
                            f"{job.id}: depth-aligned frame blending updated "
                            f"{refined} intermediate frame(s) between anchors "
                            f"{previous_diffusion_anchor} and {frame}.",
                        )
                except (Camera3DError, DepthError, ValueError, OSError) as exc:
                    emit_console(
                        "warning", "animation",
                        f"{job.id}: depth-aligned blending skipped for "
                        f"anchor {frame}: {exc}. Original cadence frames retained.",
                    )
                timings["temporal"] = max(0.0, time.monotonic() - tween_started)
            if should_diffuse:
                previous_diffusion_anchor = frame

            frame_image = image
            memory_started = time.monotonic()
            memory_maintenance = generation_manager.maintain_inference_memory()
            timings["memory"] = max(
                0.0,
                time.monotonic() - memory_started,
            )
            timings["memory_trimmed"] = 1.0 if memory_maintenance.get("trimmed") else 0.0
            phase_memory["post_maintenance"] = generation_manager.cuda_memory_status()

            frame_seconds = max(0.0, time.monotonic() - frame_started)
            timings["total"] = frame_seconds
            job._frame_times.append(frame_seconds)
            recent = job._frame_times[-8:]
            job.frame_seconds = frame_seconds
            job.average_frame_seconds = sum(recent) / len(recent)
            remaining = max(0, total - frame - 1)
            job.eta_seconds = job.average_frame_seconds * remaining
            with self._lock:
                job.current_frame_state["timings"] = deepcopy(timings)

            memory = generation_manager.cuda_memory_status()
            status_method = getattr(generation_manager, "model_status", None)
            try:
                pipeline_status = status_method() if callable(status_method) else {}
            except Exception:
                pipeline_status = {}
            record = performance_record(
                frame=frame,
                diffused=should_diffuse,
                timings=timings,
                cuda_before=cuda_before,
                cuda_after=memory,
                model_status=pipeline_status,
                conditioning_cache_entries=len(conditioning_cache),
                phase_memory=phase_memory,
            )
            performance_tracker.observe(record)
            job.performance = performance_tracker.public()
            try:
                append_performance_record(performance_path, record)
            except OSError as exc:
                emit_console(
                    "warning", "animation",
                    f"{job.id}: could not save performance details for frame {frame}: {exc}",
                )
            if should_diffuse and timings["diffusion"] >= 30.0:
                emit_console(
                    "warning", "animation",
                    f"{job.id}: slow diffusion anchor {frame} took "
                    f"{timings['diffusion']:.1f}s; execution device "
                    f"{record.get('pipeline_device') or 'unknown'}, "
                    f"cached LoRAs {record['resident_loras']}, "
                    f"active {len(record['active_loras'])}. "
                    "See performance.jsonl for allocator growth; "
                    "no automatic CPU fallback was activated.",
                )
            memory_text = ""
            if memory is not None:
                memory_text = (
                    f" VRAM free {memory['free_gib']:.1f}/{memory['total_gib']:.1f} GiB, "
                    f"allocated {memory['allocated_gib']:.1f}, "
                    f"reserved {memory['reserved_gib']:.1f} GiB."
                )

            depth_text = ""
            if depth_state is not None:
                depth_text = (
                    f" 3D depth {depth_state['seconds']:.2f}s "
                    f"({'cache' if depth_state['cache_hit'] else 'CPU'}), "
                    f"coverage {depth_state['projected_coverage'] * 100:.1f}%."
                )
            emit_console(
                "info",
                "animation",
                f"{job.id}: frame {frame}/{total - 1} complete "
                f"in {frame_seconds:.1f}s, seed {seed}, "
                f"strength {retention_strength:g} "
                f"(denoise {denoise_strength:g}), noise {noise_amount:g}, "
                f"cadence {cadence_value} "
                f"({'anchor' if cadence_anchor else 'transform'})."
                f"{depth_text} "
                f"timing resolve {timings.get('resolve', 0):.2f}s, "
                f"warp {timings.get('warp', 0):.2f}s, "
                f"cond {timings.get('conditioning', 0):.2f}s, "
                f"diff {timings.get('diffusion', 0):.2f}s, "
                f"save {timings.get('save', 0):.2f}s, "
                f"manifest {timings.get('manifest', 0):.2f}s, "
                f"mem {timings.get('memory', 0):.2f}s."
                f"{memory_text}",
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
        if str(job.project.get("animation", {}).get("mode") or "2d").lower() == "3d":
            depth_manager.unload()
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
        if str(job.project.get("animation", {}).get("mode") or "2d").lower() == "3d":
            depth_manager.unload()
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
        depth_manager.unload()
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
        if generation_manager._is_cuda_oom(exc):
            job.error += (
                " This render is resumable; after Morphorum unloads the failed pipeline, "
                "Resume will continue from the last completed frame."
            )
        job.completed_at = _utc_now()
        job.eta_seconds = None
        self._write_manifest(job)
        emit_console(
            "error",
            "animation",
            f"Animation render {job.id} failed: {error}",
        )


animation_render_manager = AnimationRenderManager()

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from typing import Any

from .animation_projects import create_animation_project, normalize_animation_project
from .animation_resolution import validate_project_schedules
from .generation import CAPABILITIES, SUPPORTED_FAMILIES
from .model_index import get_model
from .schedules import validate_numeric_schedule


IMPORTER_VERSION = 1
MAX_SOURCE_BYTES = 1_048_576
MAX_NESTING_DEPTH = 12
MAX_CONTAINER_ITEMS = 10_000
MAX_PROMPT_KEYFRAMES = 2_000
MAX_REPORTED_KEYS = 500

_MODEL_SOURCE_KEYS = {
    "ckpt",
    "checkpoint",
    "model",
    "model_checkpoint",
    "model_name",
    "model_path",
}
_UNSUPPORTED_EXACT = {
    "use_mask",
    "use_alpha_as_mask",
    "invert_mask",
    "overlay_mask",
    "mask_file",
    "mask_image",
    "use_init",
    "init_image",
    "video_init_path",
    "extract_nth_frame",
    "color_coherence",
    "color_force_grayscale",
}
_UNSUPPORTED_PREFIXES = (
    "hybrid_",
    "mask_",
    "cn_",
    "controlnet",
    "optical_flow",
    "raft",
    "parseq",
)
_SAMPLER_ALIASES = {
    "euler": "euler",
    "euler_a": "euler_a",
    "euler a": "euler_a",
    "euler ancestral": "euler_a",
    "dpmpp_2m": "dpmpp_2m",
    "dpm++ 2m": "dpmpp_2m",
    "dpm++ 2m karras": "dpmpp_2m",
    "dpmpp_2m_sde": "dpmpp_2m_sde",
    "dpm++ 2m sde": "dpmpp_2m_sde",
    "dpm++ 2m sde karras": "dpmpp_2m_sde",
    "ddim": "ddim",
    "lms": "lms",
    "heun": "heun",
    "unipc": "unipc",
    "flowmatch_euler": "flowmatch_euler",
    "flowmatch euler": "flowmatch_euler",
}


class DeforumImportError(ValueError):
    pass


def _safe_filename(value: Any) -> str:
    text = str(value or "").replace("\\", "/").split("/")[-1].strip()
    text = "".join(character for character in text if character.isprintable())
    return text[:160] or "deforum-settings.json"


def _guard_structure(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise DeforumImportError(
            f"Deforum settings exceed the maximum nesting depth of {MAX_NESTING_DEPTH}."
        )
    if counter is None:
        counter = [0]
    if isinstance(value, dict):
        counter[0] += len(value)
        if counter[0] > MAX_CONTAINER_ITEMS:
            raise DeforumImportError("Deforum settings contain too many object/list items.")
        for key, item in value.items():
            if len(str(key)) > 512:
                raise DeforumImportError("Deforum settings contain an excessively long key.")
            _guard_structure(item, depth=depth + 1, counter=counter)
    elif isinstance(value, list):
        counter[0] += len(value)
        if counter[0] > MAX_CONTAINER_ITEMS:
            raise DeforumImportError("Deforum settings contain too many object/list items.")
        for item in value:
            _guard_structure(item, depth=depth + 1, counter=counter)
    elif isinstance(value, str) and len(value) > MAX_SOURCE_BYTES:
        raise DeforumImportError("Deforum settings contain an excessively large string value.")


def parse_deforum_source(content: Any, *, filename: str = "") -> dict[str, Any]:
    if not isinstance(content, str):
        raise DeforumImportError("Deforum import content must be JSON text.")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_SOURCE_BYTES:
        raise DeforumImportError(
            f"Deforum settings are too large. Maximum import size is {MAX_SOURCE_BYTES} bytes."
        )
    if not content.strip():
        raise DeforumImportError("Deforum settings file is empty.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        suffix = _safe_filename(filename).lower()
        if suffix.endswith(".txt"):
            raise DeforumImportError(
                "This TXT file is not JSON-serialized Deforum settings. "
                "B6.1 accepts JSON objects (including JSON saved with a .txt extension); "
                "Python assignments or notebook text are intentionally not executed."
            ) from exc
        raise DeforumImportError(
            f"Invalid Deforum JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}."
        ) from exc
    if not isinstance(parsed, dict):
        raise DeforumImportError("Deforum settings root must be a JSON object.")
    _guard_structure(parsed)
    return parsed


def _mapping(
    source_key: str,
    target: str | None,
    status: str,
    source_value: Any,
    mapped_value: Any = None,
    message: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source_key": source_key,
        "target": target,
        "status": status,
        "source_value": deepcopy(source_value),
    }
    if mapped_value is not None:
        item["mapped_value"] = deepcopy(mapped_value)
    if message:
        item["message"] = message
    return item


def _first(source: dict[str, Any], *keys: str) -> tuple[str | None, Any]:
    for key in keys:
        if key in source:
            return key, source[key]
    return None, None


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
    label: str,
    warnings: list[str],
) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        warnings.append(f"{label} is not a valid integer; using {default}.")
        return default
    if number < minimum or number > maximum:
        warnings.append(
            f"{label}={number} is outside {minimum}..{maximum}; using "
            f"{max(minimum, min(maximum, number))}."
        )
    return max(minimum, min(maximum, number))


def _bounded_float(
    value: Any,
    *,
    default: float,
    minimum: float,
    maximum: float,
    label: str,
    warnings: list[str],
) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
        if not math.isfinite(number):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        warnings.append(f"{label} is not a valid number; using {default:g}.")
        return default
    if number < minimum or number > maximum:
        warnings.append(
            f"{label}={number:g} is outside {minimum:g}..{maximum:g}; using "
            f"{max(minimum, min(maximum, number)):g}."
        )
    return max(minimum, min(maximum, number))


def _schedule_text(
    value: Any,
    *,
    default: str,
    source_key: str,
    max_frames: int,
    fps: float,
    seed: int,
    warnings: list[str],
) -> tuple[str, bool]:
    if isinstance(value, bool) or value is None:
        warnings.append(f"{source_key} is not a numeric schedule; using {default}.")
        return default, False
    if isinstance(value, (int, float)):
        text = f"0:({value})"
    else:
        text = str(value).strip()
        if not text:
            warnings.append(f"{source_key} is empty; using {default}.")
            return default, False
        if ":" not in text:
            text = f"0:({text})"
    validation = validate_numeric_schedule(
        text,
        max_frames=max_frames,
        seed=seed,
        fps=fps,
    )
    if not validation.get("valid", False):
        message = "; ".join(
            str(item.get("message") or "invalid schedule")
            for item in validation.get("issues", [])
        )
        warnings.append(
            f"{source_key} was not imported because its schedule is invalid: {message}"
        )
        return default, False
    return text, True


def _prompt_map(
    value: Any,
    *,
    max_frames: int,
    source_key: str,
    warnings: list[str],
) -> tuple[dict[str, str], bool]:
    if isinstance(value, str):
        return {"0": value}, True
    if not isinstance(value, dict):
        warnings.append(f"{source_key} is not a prompt map or string; it was ignored.")
        return {"0": ""}, False
    if len(value) > MAX_PROMPT_KEYFRAMES:
        raise DeforumImportError(
            f"{source_key} has more than {MAX_PROMPT_KEYFRAMES} prompt keyframes."
        )
    result: dict[int, str] = {}
    skipped = 0
    for raw_frame, raw_text in value.items():
        try:
            frame = int(str(raw_frame).strip())
        except (TypeError, ValueError):
            skipped += 1
            continue
        if frame < 0 or frame >= max_frames:
            skipped += 1
            continue
        result[frame] = str(raw_text or "")
    if skipped:
        warnings.append(
            f"{source_key}: ignored {skipped} non-integer or out-of-range prompt keyframe(s)."
        )
    if not result:
        result[0] = ""
    elif 0 not in result:
        result[0] = ""
    return {str(frame): result[frame] for frame in sorted(result)}, True


def _selected_model(model_id: Any, *, required: bool) -> dict[str, Any] | None:
    selected = str(model_id or "").strip()
    if not selected:
        if required:
            raise DeforumImportError(
                "Choose an indexed Morphorum checkpoint before creating the imported project."
            )
        return None
    model = get_model(selected)
    if not isinstance(model, dict):
        raise DeforumImportError("The selected Morphorum model is not in the current model index.")
    family = str(model.get("family") or "").strip().lower()
    if model.get("kind") != "checkpoints" or family not in SUPPORTED_FAMILIES:
        raise DeforumImportError(
            "Deforum import requires an indexed SDXL, Flux, or Z-Image checkpoint/model."
        )
    return model


def _sampler_for_model(
    raw: Any,
    *,
    model: dict[str, Any] | None,
    warnings: list[str],
) -> tuple[str, bool]:
    family = str(model.get("family") or "") if model else ""
    capability = CAPABILITIES.get(family, {}) if family else {}
    sampler_config = capability.get("samplers", {}) if isinstance(capability, dict) else {}
    default = str(sampler_config.get("default") or "flowmatch_euler")
    source = str(raw or "").strip().lower()
    normalized = re.sub(r"\s+", " ", source.replace("-", " "))
    alias = _SAMPLER_ALIASES.get(source) or _SAMPLER_ALIASES.get(normalized)
    if not source:
        return default, True
    if alias is None:
        warnings.append(
            f"Sampler '{raw}' has no Morphorum mapping; using '{default}'."
        )
        return default, False
    if model:
        allowed = {
            str(item.get("id"))
            for item in sampler_config.get("options", [])
            if isinstance(item, dict) and item.get("id")
        }
        if alias not in allowed:
            warnings.append(
                f"Sampler '{raw}' maps to '{alias}', which is not supported by "
                f"{family or 'the selected model'}; using '{default}'."
            )
            return default, False
    return alias, True


def _seed_behavior(value: Any, warnings: list[str]) -> tuple[str, bool]:
    source = str(value or "fixed").strip().lower()
    mapping = {
        "fixed": "fixed",
        "random": "random",
        "iter": "increment",
        "iterate": "increment",
        "increment": "increment",
    }
    if source in mapping:
        return mapping[source], True
    warnings.append(
        f"Seed behavior '{value}' is not safely equivalent; using fixed."
    )
    return "fixed", False


def _compatibility_validation(
    project: dict[str, Any],
    *,
    model_selected: bool,
) -> dict[str, Any]:
    result = validate_project_schedules(project)
    issues = []
    for issue in result.get("issues", []):
        item = dict(issue)
        if item.get("field") == "tracks.prompts.positive":
            message = str(item.get("message") or "")
            if (not model_selected and "LoRA" in message) or "not found" in message.lower():
                item["severity"] = "warning"
        issues.append(item)
    result["issues"] = issues
    result["valid"] = not any(item.get("severity") == "error" for item in issues)
    return result


def translate_deforum_settings(
    settings: dict[str, Any],
    *,
    filename: str = "",
    model_id: Any = None,
    project_name: Any = None,
    require_model: bool = False,
) -> dict[str, Any]:
    source = deepcopy(settings)
    warnings: list[str] = []
    mappings: list[dict[str, Any]] = []
    used_keys: set[str] = set()

    model = _selected_model(model_id, required=require_model)
    family = str(model.get("family") or "").strip().lower() if model else ""
    capability = CAPABILITIES.get(family, {}) if model else {}
    default_sampler = str(capability.get("samplers", {}).get("default") or "flowmatch_euler")

    raw_name_key, raw_name = _first(source, "batch_name", "project_name", "name")
    if raw_name_key:
        used_keys.add(raw_name_key)
    name = str(project_name or raw_name or "Imported Deforum Animation").strip()
    name = name[:160] or "Imported Deforum Animation"

    max_key, max_value = _first(source, "max_frames")
    max_frames = _bounded_int(
        max_value if max_key else 120,
        default=120,
        minimum=1,
        maximum=1_000_000,
        label="max_frames",
        warnings=warnings,
    )
    if max_key:
        used_keys.add(max_key)
        mappings.append(_mapping(max_key, "animation.max_frames", "mapped", max_value, max_frames))

    fps_key, fps_value = _first(source, "fps")
    fps = _bounded_float(
        fps_value if fps_key else 24.0,
        default=24.0,
        minimum=1.0,
        maximum=240.0,
        label="fps",
        warnings=warnings,
    )
    if fps_key:
        used_keys.add(fps_key)
        mappings.append(_mapping(fps_key, "animation.fps", "mapped", fps_value, fps))

    width_key, width_value = _first(source, "W", "width")
    width = _bounded_int(
        width_value if width_key else 1024,
        default=1024,
        minimum=64,
        maximum=8192,
        label=width_key or "width",
        warnings=warnings,
    )
    if width_key:
        used_keys.add(width_key)
        mappings.append(_mapping(width_key, "animation.width", "mapped", width_value, width))

    height_key, height_value = _first(source, "H", "height")
    height = _bounded_int(
        height_value if height_key else 1024,
        default=1024,
        minimum=64,
        maximum=8192,
        label=height_key or "height",
        warnings=warnings,
    )
    if height_key:
        used_keys.add(height_key)
        mappings.append(_mapping(height_key, "animation.height", "mapped", height_value, height))

    if width % 8 or height % 8:
        warnings.append(
            "Imported dimensions are not divisible by 8. Morphorum preserved them in the "
            "preview, but supported diffusion families may require divisibility by 8 or 16."
        )

    mode_key, mode_value = _first(source, "animation_mode")
    raw_mode = str(mode_value or "2D").strip().lower()
    if raw_mode == "3d":
        mode = "3d"
        mode_ok = True
    elif raw_mode == "2d":
        mode = "2d"
        mode_ok = True
    else:
        mode = "2d"
        mode_ok = False
        if mode_key:
            warnings.append(
                f"Deforum animation_mode '{mode_value}' is not a native Morphorum "
                "2D/3D mode; preview defaults to 2D."
            )
    if mode_key:
        used_keys.add(mode_key)
        mappings.append(
            _mapping(
                mode_key,
                "animation.mode",
                "mapped" if mode_ok else "unsupported",
                mode_value,
                mode,
            )
        )

    seed_key, seed_value = _first(source, "seed")
    seed = _bounded_int(
        seed_value if seed_key else -1,
        default=-1,
        minimum=-1,
        maximum=2**32 - 1,
        label="seed",
        warnings=warnings,
    )
    if seed_key:
        used_keys.add(seed_key)
        mappings.append(_mapping(seed_key, "generation.seed", "mapped", seed_value, seed))

    behavior_key, behavior_value = _first(source, "seed_behavior")
    behavior, behavior_ok = _seed_behavior(behavior_value if behavior_key else "fixed", warnings)
    if behavior_key:
        used_keys.add(behavior_key)
        mappings.append(
            _mapping(
                behavior_key,
                "generation.seed_behavior",
                "mapped" if behavior_ok else "mapped_with_warning",
                behavior_value,
                behavior,
            )
        )

    increment_key, increment_value = _first(source, "seed_iter_N", "seed_increment")
    seed_increment = _bounded_int(
        increment_value if increment_key else 1,
        default=1,
        minimum=-2**31,
        maximum=2**31 - 1,
        label=increment_key or "seed_increment",
        warnings=warnings,
    )
    if increment_key:
        used_keys.add(increment_key)
        mappings.append(
            _mapping(increment_key, "generation.seed_increment", "mapped", increment_value, seed_increment)
        )

    project_payload: dict[str, Any] = {
        "name": name,
        "animation": {
            "max_frames": max_frames,
            "fps": fps,
            "width": width,
            "height": height,
            "mode": mode,
            "start_mode": "prompt",
            "prompt_transition": "blend",
        },
        "model": {
            "model_id": str(model.get("id") or "") if model else "",
            "family": family,
            "variant": str(model.get("variant") or "").strip().lower() if model else "",
        },
        "motion": {
            "angle": "0:(0)",
            "zoom": "0:(1.0)",
            "translation_x": "0:(0)",
            "translation_y": "0:(0)",
            "border_mode": "replicate",
        },
        "camera_3d": {
            "translation_x": "0:(0)",
            "translation_y": "0:(0)",
            "translation_z": "0:(0)",
            "rotation_x": "0:(0)",
            "rotation_y": "0:(0)",
            "rotation_z": "0:(0)",
            "fov": "0:(40)",
            "depth_resolution": "auto",
            "projection_mode": "legacy",
            "hole_fill": "nearest",
        },
        "generation": {
            "strength": "0:(0.65)",
            "noise": "0:(0.02)",
            "steps": "0:(20)",
            "guidance": "0:(0)",
            "sampler": default_sampler,
            "seed": seed,
            "seed_behavior": behavior,
            "seed_increment": seed_increment,
        },
        "cadence": {"diffusion": "0:(1)"},
        "notes": "",
    }

    prompt_key, prompt_value = _first(source, "animation_prompts", "prompts")
    if prompt_key:
        used_keys.add(prompt_key)
        prompts, prompt_ok = _prompt_map(
            prompt_value,
            max_frames=max_frames,
            source_key=prompt_key,
            warnings=warnings,
        )
        project_payload["prompts"] = prompts
        mappings.append(
            _mapping(
                prompt_key,
                "tracks.prompts.positive",
                "mapped" if prompt_ok else "mapped_with_warning",
                prompt_value,
                prompts,
            )
        )

    negative_key, negative_value = _first(
        source,
        "animation_prompts_negative",
        "negative_prompts",
        "negative_prompt",
    )
    if negative_key:
        used_keys.add(negative_key)
        negatives, negative_ok = _prompt_map(
            negative_value,
            max_frames=max_frames,
            source_key=negative_key,
            warnings=warnings,
        )
        project_payload["negative_prompts"] = negatives
        mappings.append(
            _mapping(
                negative_key,
                "tracks.prompts.negative",
                "mapped" if negative_ok else "mapped_with_warning",
                negative_value,
                negatives,
            )
        )

    schedule_mappings = [
        ("angle", "motion", "angle", "0:(0)"),
        ("zoom", "motion", "zoom", "0:(1.0)"),
        ("strength_schedule", "generation", "strength", "0:(0.65)"),
        ("noise_schedule", "generation", "noise", "0:(0.02)"),
    ]
    for source_key, section, target_key, default in schedule_mappings:
        if source_key not in source:
            continue
        used_keys.add(source_key)
        schedule, ok = _schedule_text(
            source[source_key],
            default=default,
            source_key=source_key,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
            warnings=warnings,
        )
        project_payload[section][target_key] = schedule
        mappings.append(
            _mapping(
                source_key,
                f"{section}.{target_key}",
                "mapped" if ok else "rejected",
                source[source_key],
                schedule,
            )
        )

    for source_key in ("translation_x", "translation_y"):
        if source_key not in source:
            continue
        used_keys.add(source_key)
        if mode == "3d":
            section = "camera_3d"
            message = (
                "Copied into Morphorum 3D camera space. Deforum and Morphorum camera "
                "units/signs may not be visually identical; inspect the timeline before rendering."
            )
            status = "mapped_with_warning"
            warnings.append(f"{source_key}: {message}")
        else:
            section = "motion"
            message = None
            status = "mapped"
        schedule, ok = _schedule_text(
            source[source_key],
            default="0:(0)",
            source_key=source_key,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
            warnings=warnings,
        )
        project_payload[section][source_key] = schedule
        mappings.append(
            _mapping(
                source_key,
                f"{section}.{source_key}",
                status if ok else "rejected",
                source[source_key],
                schedule,
                message,
            )
        )

    for source_key, target_key in (
        ("translation_z", "translation_z"),
        ("rotation_3d_x", "rotation_x"),
        ("rotation_3d_y", "rotation_y"),
        ("rotation_3d_z", "rotation_z"),
    ):
        if source_key not in source:
            continue
        used_keys.add(source_key)
        schedule, ok = _schedule_text(
            source[source_key],
            default="0:(0)",
            source_key=source_key,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
            warnings=warnings,
        )
        project_payload["camera_3d"][target_key] = schedule
        message = (
            "Direct numeric compatibility mapping only. Verify Deforum/Morphorum "
            "3D coordinate direction and scale in preview before a long render."
        )
        warnings.append(f"{source_key}: {message}")
        mappings.append(
            _mapping(
                source_key,
                f"camera_3d.{target_key}",
                "mapped_with_warning" if ok else "rejected",
                source[source_key],
                schedule,
                message,
            )
        )

    fov_key, fov_value = _first(source, "fov_schedule", "fov")
    if fov_key:
        used_keys.add(fov_key)
        schedule, ok = _schedule_text(
            fov_value,
            default="0:(40)",
            source_key=fov_key,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
            warnings=warnings,
        )
        project_payload["camera_3d"]["fov"] = schedule
        mappings.append(
            _mapping(
                fov_key,
                "camera_3d.fov",
                "mapped_with_warning" if ok else "rejected",
                fov_value,
                schedule,
                "Verify field-of-view equivalence before rendering.",
            )
        )

    steps_key, steps_value = _first(source, "steps_schedule", "steps")
    if steps_key:
        used_keys.add(steps_key)
        schedule, ok = _schedule_text(
            steps_value,
            default="0:(20)",
            source_key=steps_key,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
            warnings=warnings,
        )
        project_payload["generation"]["steps"] = schedule
        mappings.append(
            _mapping(
                steps_key,
                "generation.steps",
                "mapped" if ok else "rejected",
                steps_value,
                schedule,
            )
        )

    guidance_key, guidance_value = _first(source, "cfg_scale_schedule", "cfg_scale")
    if guidance_key:
        used_keys.add(guidance_key)
        schedule, ok = _schedule_text(
            guidance_value,
            default="0:(0)",
            source_key=guidance_key,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
            warnings=warnings,
        )
        project_payload["generation"]["guidance"] = schedule
        mappings.append(
            _mapping(
                guidance_key,
                "generation.guidance",
                "mapped" if ok else "rejected",
                guidance_value,
                schedule,
            )
        )

    cadence_key, cadence_value = _first(source, "diffusion_cadence")
    if cadence_key:
        used_keys.add(cadence_key)
        schedule, ok = _schedule_text(
            cadence_value,
            default="0:(1)",
            source_key=cadence_key,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
            warnings=warnings,
        )
        project_payload["cadence"]["diffusion"] = schedule
        mappings.append(
            _mapping(
                cadence_key,
                "cadence.diffusion",
                "mapped" if ok else "rejected",
                cadence_value,
                schedule,
            )
        )

    sampler_key, sampler_value = _first(source, "sampler", "sampler_name")
    sampler, sampler_ok = _sampler_for_model(
        sampler_value if sampler_key else "",
        model=model,
        warnings=warnings,
    )
    project_payload["generation"]["sampler"] = sampler
    if sampler_key:
        used_keys.add(sampler_key)
        mappings.append(
            _mapping(
                sampler_key,
                "generation.sampler",
                "mapped" if sampler_ok else "mapped_with_warning",
                sampler_value,
                sampler,
            )
        )

    for key in sorted(_MODEL_SOURCE_KEYS):
        if key not in source:
            continue
        used_keys.add(key)
        message = (
            "Imported model/checkpoint paths are passive metadata only. "
            "Morphorum will use only the explicitly selected indexed model."
        )
        warnings.append(f"{key}: {message}")
        mappings.append(
            _mapping(key, None, "ignored_path", source[key], message=message)
        )

    unsupported_keys: list[str] = []
    unmapped_keys: list[str] = []
    for key in source:
        if key in used_keys:
            continue
        lowered = str(key).strip().lower()
        if lowered in _UNSUPPORTED_EXACT or lowered.startswith(_UNSUPPORTED_PREFIXES):
            unsupported_keys.append(str(key))
            mappings.append(
                _mapping(
                    str(key),
                    None,
                    "unsupported",
                    source[key],
                    message="Preserved as passive compatibility metadata; no B6.1 runtime effect.",
                )
            )
        else:
            unmapped_keys.append(str(key))
            mappings.append(
                _mapping(
                    str(key),
                    None,
                    "unmapped",
                    source[key],
                    message="Preserved as passive compatibility metadata.",
                )
            )

    source_filename = _safe_filename(filename)
    source_sha256 = hashlib.sha256(
        json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode("utf-8")
    ).hexdigest()
    project_payload["compatibility"] = {
        "deforum": {
            "importer_version": IMPORTER_VERSION,
            "source_filename": source_filename,
            "source_sha256": source_sha256,
            "source_settings": source,
            "unsupported_keys": unsupported_keys[:MAX_REPORTED_KEYS],
            "unmapped_keys": unmapped_keys[:MAX_REPORTED_KEYS],
        }
    }

    candidate = normalize_animation_project(
        project_payload,
        project_id="deforum-preview",
        prefer_tracks=False,
    )
    validation = _compatibility_validation(
        candidate,
        model_selected=model is not None,
    )

    for issue in validation.get("issues", []):
        if issue.get("severity") == "warning":
            warnings.append(
                f"{issue.get('field', 'schedule')}: {issue.get('message', 'warning')}"
            )

    if model is None:
        warnings.insert(
            0,
            "No Morphorum model selected yet. Choose an indexed model before creating the project.",
        )

    return {
        "importer_version": IMPORTER_VERSION,
        "source_filename": source_filename,
        "source_sha256": source_sha256,
        "model_required": model is None,
        "selected_model": (
            {
                "id": model.get("id"),
                "name": model.get("name"),
                "family": model.get("family"),
                "variant": model.get("variant"),
            }
            if model
            else None
        ),
        "project": candidate,
        "mappings": mappings[:MAX_REPORTED_KEYS],
        "warnings": list(dict.fromkeys(warnings)),
        "unsupported_keys": unsupported_keys[:MAX_REPORTED_KEYS],
        "unmapped_keys": unmapped_keys[:MAX_REPORTED_KEYS],
        "validation": validation,
        "can_create": bool(model) and bool(validation.get("valid", False)),
    }


def preview_deforum_import(
    content: Any,
    *,
    filename: str = "",
    model_id: Any = None,
    project_name: Any = None,
) -> dict[str, Any]:
    settings = parse_deforum_source(content, filename=filename)
    return translate_deforum_settings(
        settings,
        filename=filename,
        model_id=model_id,
        project_name=project_name,
        require_model=False,
    )


def create_deforum_import(
    content: Any,
    *,
    filename: str = "",
    model_id: Any = None,
    project_name: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = parse_deforum_source(content, filename=filename)
    report = translate_deforum_settings(
        settings,
        filename=filename,
        model_id=model_id,
        project_name=project_name,
        require_model=True,
    )
    if not report.get("validation", {}).get("valid", False):
        first = next(
            (
                issue
                for issue in report["validation"].get("issues", [])
                if issue.get("severity") == "error"
            ),
            None,
        )
        message = str(first.get("message") if first else "Imported schedules are invalid.")
        raise DeforumImportError(
            f"Deforum import cannot create a project until validation errors are fixed: {message}"
        )
    project = create_animation_project(report["project"])
    return project, report

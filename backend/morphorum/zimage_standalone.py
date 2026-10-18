"""Z2 standalone Z-Image dependency resolver (read-only, fail-closed).

A resolution plan is not a load authorization. Managed Z-Image remains separate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .zimage_inspect import inspect_zimage_checkpoint

REQUIRED_COMPONENTS = ("text_encoder", "tokenizer", "vae", "scheduler")
MAX_CONFIG_BYTES = 1024 * 1024


def _read_component_json(path: Path) -> dict[str, Any] | None:
    """Inspect bounded local JSON only; never follow symlinks."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CONFIG_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, UnicodeError, ValueError):
        return None


def inspect_encoder_bundle(path: str | Path) -> dict[str, Any]:
    """Inspect adjacent encoder configuration/tokenizer evidence.

    Never selects an encoder solely from filename or directory proximity.
    """
    file = Path(path)
    info = inspect_zimage_checkpoint(file)
    result: dict[str, Any] = {
        "path": str(file), "status": "unverified", "encoder_family": "unknown",
        "configuration_present": False, "tokenizer_present": False,
        "issues": [], "loadable": False,
    }
    if info.get("component_type") != "text_encoder":
        result["issues"].append("Safetensors tensor structure is not a recognized text encoder.")
        return result
    # A single-file encoder may come with optional adjacent HF configuration.
    config = _read_component_json(file.parent / "config.json")
    if config is None:
        result["issues"].append("Missing or invalid adjacent config.json.")
    else:
        result["configuration_present"] = True
        model_type = str(config.get("model_type") or "").lower()
        architectures = config.get("architectures", [])
        if model_type == "qwen3" and isinstance(architectures, list) and any(
            isinstance(item, str) and item.startswith("Qwen3")
            for item in architectures
        ):
            result["encoder_family"] = "qwen3"
        else:
            result["issues"].append("Encoder config does not positively identify Qwen3.")
        for field in ("hidden_size", "num_hidden_layers", "num_attention_heads", "vocab_size"):
            value = config.get(field)
            if type(value) is not int or value <= 0:
                result["issues"].append(f"Missing or invalid Qwen3 configuration: {field}.")
    tokenizer = file.parent / "tokenizer.json"
    if tokenizer.is_file() and not tokenizer.is_symlink() and 0 < tokenizer.stat().st_size:
        result["tokenizer_present"] = True
    else:
        result["issues"].append("Missing adjacent tokenizer.json.")
    if not result["issues"]:
        result["status"] = "component_evidence_present"
        result["issues"].append(
            "Files are present but transformer/encoder shape matching and runtime loading remain unverified."
        )
    return result



def resolve_standalone_dependencies(
    checkpoint: str | Path, indexed_components: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Inventory possible dependencies without loading tensors or selecting by filename.

    A detected Qwen-like encoder is a *candidate*, not a compatible encoder.
    No architecture or tokenizer compatibility is implied by directory proximity.
    """
    source = Path(checkpoint)
    inspection = inspect_zimage_checkpoint(source)
    result: dict[str, Any] = {
        "source": "external",
        "loader": "zimage-single-file",
        "checkpoint": str(source),
        "inspection": inspection,
        "status": "unsupported",
        "ready": False,
        "loadable": False,
        "missing_components": list(REQUIRED_COMPONENTS),
        "encoder_candidates": [],
        "conversion_strategy": "unresolved",
        "reason": "",
    }
    if inspection["status"] not in ("candidate", "needs_components"):
        result["reason"] = inspection["reason"]
        return result

    candidates = []
    for row in indexed_components:
        if row.get("family") != "zimage" or row.get("kind") != "components":
            continue
        path = row.get("path")
        if not isinstance(path, str):
            continue
        probe = inspect_zimage_checkpoint(path)
        if probe.get("component_type") != "text_encoder":
            continue
        bundle = inspect_encoder_bundle(path)
        candidates.append({
            "id": row.get("id"),
            "path": str(Path(path)),
            "status": bundle["status"],
            "bundle": bundle,
            "reason": "Encoder tensor pattern detected; final architecture and tensor compatibility remain unverified.",
        })
    result["encoder_candidates"] = candidates
    architecture = inspection.get("architecture")
    precision = inspection.get("tensor_validation", {}).get("precision")
    if architecture == "zimage_original_transformer" and precision == "floating":
        result["conversion_strategy"] = "candidate_for_explicit_diffusers_conversion"
    elif architecture == "zimage_diffusers_transformer" and precision == "floating":
        result["conversion_strategy"] = "candidate_for_diffusers_transformer_import"
    elif precision == "quantized":
        result["conversion_strategy"] = "blocked_quantization_mapping_unverified"
    result["status"] = "needs_components"
    result["reason"] = (
        "Standalone Z-Image loader is not yet verified. "
        + ("Text encoder candidate(s) detected, but compatibility is unverified. "
           if candidates else "No recognized text encoder candidates were indexed. ")
        + "A matching tokenizer, VAE, scheduler and full transformer mapping are required."
    )
    return result


def require_verified_standalone(plan: dict[str, Any]) -> None:
    """Explicit guard for future standalone runtime integration."""
    if plan.get("source") != "external" or plan.get("loader") != "zimage-single-file":
        raise ValueError("Not a standalone Z-Image resolution plan.")
    # Intentionally fail closed until runtime verification is implemented.
    raise RuntimeError("Standalone Z-Image loader is not verified or enabled.")

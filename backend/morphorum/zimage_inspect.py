"""Bounded, read-only inspection of external Z-Image safetensors checkpoints.

This module does not load weights or certify runtime compatibility. No pickle.
"""
from __future__ import annotations

import json
import os
import struct
from collections import Counter
from pathlib import Path
from typing import Any

MAX_HEADER_BYTES = 16 * 1024 * 1024
MAX_TENSORS = 250_000
MAX_RANK = 16
MAX_METADATA_ENTRIES = 256

_DTYPE_BYTES = {
    "BOOL": 1, "U8": 1, "I8": 1, "F8_E4M3": 1,
    "F8_E4M3FN": 1, "F8_E5M2": 1, "F8_E4M3FNUZ": 1,
    "F8_E5M2FNUZ": 1, "I16": 2, "U16": 2, "F16": 2,
    "BF16": 2, "I32": 4, "U32": 4, "F32": 4,
    "I64": 8, "U64": 8, "F64": 8, "F4": 0.5,
}


def inspect_zimage_checkpoint(path: str | Path) -> dict[str, Any]:
    """Inspect a checkpoint without reading its tensor payload.

    `candidate` means inspectable and potentially convertible, *not* ready
    for generation. Only a subsequent architecture-specific loader may approve
    a standalone file as supported.
    """
    result: dict[str, Any] = {
        "status": "unsupported", "ready": False, "loadable": False,
        "reason": "", "tensor_count": 0, "dtypes": {},
        "component_hints": [], "sample_keys": [],
    }

    def reject(reason: str) -> dict[str, Any]:
        result["reason"] = reason
        return result

    file = Path(path)
    if file.suffix.lower() != ".safetensors":
        return reject("Only safetensors is accepted for standalone Z-Image inspection; pickle and GGUF are not loaded.")
    try:
        if not file.is_file() or file.is_symlink():
            return reject("Checkpoint is missing, not a regular file, or is a symbolic link.")
        size = file.stat().st_size
        if size < 10:
            return reject("Checkpoint is empty or too small for a safetensors header.")
        with file.open("rb") as handle:
            header_bytes = handle.read(8)
            if len(header_bytes) != 8:
                return reject("Truncated safetensors length prefix.")
            header_size = struct.unpack("<Q", header_bytes)[0]
            if not 2 <= header_size <= MAX_HEADER_BYTES or header_size > size - 8:
                return reject("Invalid or oversized safetensors header.")
            header = handle.read(header_size)
            if len(header) != header_size:
                return reject("Truncated safetensors header.")
        parsed = json.loads(header)
        if not isinstance(parsed, dict) or len(parsed) > MAX_TENSORS + 1:
            return reject("Invalid safetensors header or excessive tensor count.")
        metadata = parsed.pop("__metadata__", {})
        if not isinstance(metadata, dict) or len(metadata) > MAX_METADATA_ENTRIES or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in metadata.items()
        ):
            return reject("Invalid safetensors metadata.")
        if not parsed:
            return reject("No tensors in checkpoint.")
        payload_size = size - header_size - 8
        intervals: list[tuple[int, int]] = []
        dtypes: Counter[str] = Counter()
        prefixes: Counter[str] = Counter()
        key_samples: list[str] = []
        tensor_keys: set[str] = set()
        tensor_shapes: dict[str, list[int]] = {}
        for key, spec in parsed.items():
            if not isinstance(key, str) or not key or not isinstance(spec, dict):
                return reject("Malformed tensor entry.")
            if set(spec) != {"dtype", "shape", "data_offsets"}:
                return reject("Malformed tensor attributes.")
            dtype, shape, offsets = spec["dtype"], spec["shape"], spec["data_offsets"]
            if dtype not in _DTYPE_BYTES or not isinstance(shape, list) or len(shape) > MAX_RANK:
                return reject("Unknown tensor dtype or invalid tensor shape.")
            if any(type(dim) is not int or dim < 0 for dim in shape):
                return reject("Invalid tensor dimension.")
            if not isinstance(offsets, list) or len(offsets) != 2 or any(type(n) is not int for n in offsets):
                return reject("Invalid tensor byte offsets.")
            start, end = offsets
            if start < 0 or end < start or end > payload_size:
                return reject("Tensor byte offsets exceed checkpoint bounds.")
            elements = 1
            for dim in shape:
                elements *= dim
            expected_bits = int(elements * _DTYPE_BYTES[dtype] * 8)
            if (expected_bits + 7) // 8 != end - start:
                return reject("Tensor dimensions and dtype do not match byte offsets.")
            tensor_keys.add(key)
            tensor_shapes[key] = shape
            intervals.append((start, end))
            dtypes[dtype] += 1
            prefixes[key.split(".", 1)[0]] += 1
            if len(key_samples) < 12:
                key_samples.append(key[:180])
        intervals.sort()
        previous_end = 0
        for start, end in intervals:
            if start != previous_end:
                return reject("Tensor payload has overlapping or missing byte regions.")
            previous_end = end
        if previous_end != payload_size:
            return reject("Tensor payload contains unreferenced bytes.")
        result.update(tensor_count=len(parsed), dtypes=dict(dtypes), sample_keys=key_samples)
        # Detect Qwen-like encoder weights from structure, never filename.
        normalized_keys = {
            key.removeprefix("text_encoder.").removeprefix("language_model.")
            for key in tensor_keys
        }
        encoder_signature = (
            "model.embed_tokens.weight" in normalized_keys
            and any(key.startswith("model.layers.") and ".self_attn.q_proj.weight" in key
                    for key in normalized_keys)
            and any(key.startswith("model.layers.") and ".mlp.gate_proj.weight" in key
                    for key in normalized_keys)
            and not any(key.startswith(("transformer.", "diffusion_model.", "vae."))
                        for key in tensor_keys)
        )
        if encoder_signature:
            result["status"] = "auxiliary"
            result["component_type"] = "text_encoder"
            result["reason"] = (
                "Text-encoder-like weights detected from tensor structure. Indexed as an "
                "auxiliary component only; tokenizer, configuration and exact Z-Image "
                "checkpoint compatibility remain unverified."
            )
            return result
        # Z2.2: conservative architectural evidence from upstream Z-Image
        # transformer naming (original ComfyUI and Diffusers layouts).
        # This is a fingerprint, never permission to execute a model.
        native = {key.removeprefix("model.diffusion_model.").removeprefix("transformer.")
                  for key in tensor_keys}
        original_markers = {
            "x_embedder": any(k.startswith("x_embedder.") for k in native),
            "final_layer": any(k.startswith("final_layer.") for k in native),
            "cap_embedder": any(k.startswith("cap_embedder.") for k in native),
            "noise_refiner": any(k.startswith("noise_refiner.") for k in native),
            "context_refiner": any(k.startswith("context_refiner.") for k in native),
            "layers": any(k.startswith("layers.") for k in native),
        }
        diffusers_markers = dict(original_markers)
        diffusers_markers["x_embedder"] = any(k.startswith("all_x_embedder.") for k in native)
        diffusers_markers["final_layer"] = any(k.startswith("all_final_layer.") for k in native)
        layout = None
        if all(original_markers.values()):
            layout = "zimage_original_transformer"
        elif all(diffusers_markers.values()):
            layout = "zimage_diffusers_transformer"
        result["architecture"] = layout or "unverified"
        result["architecture_evidence"] = (
            original_markers if layout == "zimage_original_transformer"
            else diffusers_markers if layout else original_markers
        )
        if layout:
            # Inspect tensor dimensions and contiguous layer IDs, without
            # assuming a particular released Z-Image depth or hidden size.
            import re
            numbered = {}
            for block in ("layers", "noise_refiner", "context_refiner"):
                matches = set()
                for key in native:
                    found = re.match(r"^" + block + r"\\.(\\d+)\\.", key)
                    if found:
                        matches.add(int(found.group(1)))
                numbered[block] = {
                    "count": len(matches),
                    "contiguous": bool(matches) and matches == set(range(max(matches) + 1)),
                    "highest_index": max(matches) if matches else None,
                }
            # Shape checks are sanity checks, not an architecture certification.
            invalid_matrix = []
            for key, shape in tensor_shapes.items():
                if key.endswith((".weight", ".bias")) and shape and any(dim == 0 for dim in shape):
                    invalid_matrix.append(key[:180])
            quantized = [dtype for dtype in dtypes if dtype.startswith("F8_") or dtype == "F4"]
            scale_keys = [key for key in tensor_keys
                          if key.endswith((".scale", ".weight_scale", ".scale_inv", ".weight_scale_inv"))]
            result["tensor_validation"] = {
                "blocks": numbered,
                "zero_sized_parameters": invalid_matrix[:20],
                "precision": "quantized" if quantized else "floating",
                "quantized_dtypes": sorted(quantized),
                "scale_tensor_count": len(scale_keys),
                "quantization_convention": "unverified" if quantized else "not_applicable",
            }
            if quantized:
                result["precision_warning"] = (
                    "FP8/low-bit tensors detected; scaling convention and conversion support "
                    "are not verified even if scale tensors exist."
                )
            problems = [
                name for name, info in numbered.items()
                if not info["contiguous"]
            ]
            if invalid_matrix:
                problems.append("zero-sized parameters")
            if problems:
                result["status"] = "unsupported"
                result["reason"] = "Incomplete or malformed structural evidence: " + ", ".join(problems)
                return result
            result["status"] = "needs_components"
            result["reason"] = (
                "Z-Image transformer structural signature detected (" + layout + "). "
                "Completeness, tensor dimensions, quantization support and accompanying "
                "Qwen3 encoder/tokenizer, VAE and scheduler are not yet verified."
            )
            return result
        # This is a heuristic inventory, not a filename-based family guess.
        tokens = set(prefixes)
        hints = []
        for component in ("transformer", "text_encoder", "tokenizer", "vae", "scheduler"):
            if component in tokens:
                hints.append(component)
        if "model" in tokens or "diffusion_model" in tokens:
            hints.append("wrapped_model")
        result["component_hints"] = hints
        if any(dtype.startswith("F8_") or dtype == "F4" for dtype in dtypes):
            result["precision_warning"] = "Low-precision tensors require architecture-specific quantization verification."
        if hints == ["transformer"] or hints == ["wrapped_model"]:
            result["status"] = "needs_components"
            result["reason"] = (
                "Looks like transformer-only weights; a verified matching text encoder, tokenizer, VAE "
                "and scheduler are required. Architecture and mapping remain unverified."
            )
        elif hints:
            result["status"] = "candidate"
            result["reason"] = (
                "Recognizable component namespaces found; architecture, tensor mapping, "
                "required auxiliary components and loader compatibility are not yet verified."
            )
        else:
            result["status"] = "unsupported"
            result["reason"] = (
                "Tensor layout does not identify a supported Z-Image architecture. "
                "No filename-based assumptions were made."
            )
        return result
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, OverflowError) as exc:
        return reject(f"Unable to inspect safetensors safely: {type(exc).__name__}.")

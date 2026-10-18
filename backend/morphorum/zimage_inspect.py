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

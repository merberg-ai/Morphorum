"""Z2.17 complete read-only external-vs-managed Z-Image tensor schema comparison.

The managed weight *index* and each referenced shard's safetensors *header*
are independently inspected. No weight payload, model object or GPU is loaded.
Even complete name/shape matches do not authorize FP8 conversion or inference.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from .zimage_conversion import ConversionPreflightError, plan_original_tensor_mapping
from .zimage_fp8_validation import validate_fp8_single_file
from .zimage_inspect import MAX_HEADER_BYTES, inspect_zimage_checkpoint

MAX_INDEX_BYTES = 8 * 1024 * 1024
MAX_SHARDS = 64
MAX_TENSORS = 12000
MAX_REPORT_ITEMS = 16
_REFERENCE = {
    "transformer": ("transformer", "diffusion_pytorch_model.safetensors.index.json"),
    "encoder": ("text_encoder", "model.safetensors.index.json"),
}


class SchemaInspectionError(ValueError):
    pass


def _read_json(path: Path, limit: int) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SchemaInspectionError("Missing or unsafe reference JSON.")
    if path.stat().st_size > limit:
        raise SchemaInspectionError("Reference JSON exceeds size bound.")
    with path.open("rb") as handle:
        content = handle.read(limit + 1)
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise SchemaInspectionError("Malformed JSON.") from exc
    if not isinstance(data, dict):
        raise SchemaInspectionError("Reference JSON must be an object.")
    return data


def _safe_child(folder: Path, filename: str) -> Path:
    if (not isinstance(filename, str) or not filename or
            filename != Path(filename).name or
            "/" in filename or "\\" in filename or filename in (".", "..")):
        raise SchemaInspectionError("Invalid shard filename in managed index.")
    path = folder / filename
    if path.is_symlink() or not path.is_file():
        raise SchemaInspectionError("Missing or unsafe managed shard.")
    return path


def read_managed_component_schema(root: str | Path, family: str) -> dict[str, tuple[int, ...]]:
    """Strict HF-index-to-safetensors-header integrity check; read no weights."""
    if family not in _REFERENCE:
        raise SchemaInspectionError("Unsupported reference component.")
    root = Path(root)
    directory_name, index_file = _REFERENCE[family]
    directory = root / directory_name
    if root.is_symlink() or directory.is_symlink():
        raise SchemaInspectionError("Managed package uses an unsafe symbolic link.")
    index = _read_json(directory / index_file, MAX_INDEX_BYTES)
    weight_map = index.get("weight_map")
    if (not isinstance(weight_map, dict) or not weight_map or
            len(weight_map) > MAX_TENSORS or
            any(not isinstance(key, str) or not key or
                not isinstance(value, str) for key, value in weight_map.items())):
        raise SchemaInspectionError("Managed shard index is malformed or oversized.")
    shard_names = set(weight_map.values())
    if len(shard_names) > MAX_SHARDS:
        raise SchemaInspectionError("Too many managed weight shards.")
    observed: dict[str, tuple[int, ...]] = {}
    for filename in sorted(shard_names):
        if not filename.endswith(".safetensors"):
            raise SchemaInspectionError("Managed index references a non-safetensors shard.")
        shard = _safe_child(directory, filename)
        with shard.open("rb") as handle:
            length_bytes = handle.read(8)
            if len(length_bytes) != 8:
                raise SchemaInspectionError("Truncated managed shard header.")
            header_size = struct.unpack("<Q", length_bytes)[0]
            size = shard.stat().st_size
            if not 2 <= header_size <= MAX_HEADER_BYTES or header_size + 8 > size:
                raise SchemaInspectionError("Invalid managed shard header length.")
            raw = handle.read(header_size)
            if len(raw) != header_size:
                raise SchemaInspectionError("Truncated managed shard header payload.")
        try:
            specs = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise SchemaInspectionError("Malformed managed safetensors header.") from exc
        if not isinstance(specs, dict):
            raise SchemaInspectionError("Managed safetensors header is not an object.")
        specs.pop("__metadata__", None)
        if len(specs) > MAX_TENSORS:
            raise SchemaInspectionError("Excessive tensors in managed shard.")
        payload_size = size - 8 - header_size
        intervals = []
        for name, spec in specs.items():
            if (not isinstance(name, str) or not isinstance(spec, dict) or
                    set(spec) != {"dtype", "shape", "data_offsets"}):
                raise SchemaInspectionError("Malformed managed tensor specification.")
            shape = spec["shape"]
            offsets = spec["data_offsets"]
            if (not isinstance(shape, list) or len(shape) > 16 or
                    any(type(n) is not int or n < 0 for n in shape) or
                    not isinstance(offsets, list) or len(offsets) != 2 or
                    any(type(n) is not int for n in offsets)):
                raise SchemaInspectionError("Invalid managed tensor dimensions or offsets.")
            start, end = offsets
            if start < 0 or end < start or end > payload_size:
                raise SchemaInspectionError("Managed tensor offsets exceed file bounds.")
            bytes_per = {"F32": 4, "F16": 2, "BF16": 2, "F64": 8,
                         "F8_E4M3": 1, "F8_E4M3FN": 1}.get(spec["dtype"])
            if bytes_per is None or math.prod(shape) * bytes_per != end - start:
                raise SchemaInspectionError("Managed tensor shape/byte length mismatch.")
            if name in observed or weight_map.get(name) != filename:
                raise SchemaInspectionError("Managed shard contains duplicate or unindexed tensors.")
            intervals.append((start, end))
            observed[name] = tuple(shape)
        intervals.sort()
        cursor = 0
        for start, end in intervals:
            if start != cursor:
                raise SchemaInspectionError("Managed shard has holes or overlapping tensor bytes.")
            cursor = end
        if cursor != payload_size:
            raise SchemaInspectionError("Managed shard contains unindexed payload bytes.")
    if set(observed) != set(weight_map):
        raise SchemaInspectionError("Managed weight_map does not cover all shard tensor names.")
    return observed


def _external_shapes(path: Path) -> tuple[dict[str, tuple[int, ...]], int]:
    """Return actual model parameters, discarding ONLY proven unit input scales.

    In ComfyUI comfy/utils.py convert_old_quants, the old .scale_input
    is discarded if and only if its scalar value is exactly 1.0. Non-unit
    scales cannot be silently ignored because they affect inference math.
    All other tensors must participate in the complete schema comparison.
    """
    with path.open("rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise SchemaInspectionError("Truncated external safetensors header.")
        length = struct.unpack("<Q", raw_length)[0]
        if length < 2 or length > MAX_HEADER_BYTES:
            raise SchemaInspectionError("Invalid external safetensors header.")
        raw = handle.read(length)
        if len(raw) != length:
            raise SchemaInspectionError("Truncated external safetensors header.")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise SchemaInspectionError("Malformed external header.")
        data.pop("__metadata__", None)
        if len(data) > MAX_TENSORS:
            raise SchemaInspectionError("External tensor count exceeds bound.")
        removed_unit_scales = 0
        result: dict[str, tuple[int, ...]] = {}
        for name, spec in data.items():
            if name == "scaled_fp8" or name.endswith(".scale_weight"):
                continue
            if name.endswith(".scale_input"):
                weight_key = name[:-len(".scale_input")] + ".weight"
                weight_spec = data.get(weight_key)
                if not isinstance(weight_spec, dict) or weight_spec.get("dtype") != "F8_E4M3":
                    raise SchemaInspectionError("Orphan input scale without a matching FP8 weight.")
                shape = spec.get("shape")
                offsets = spec.get("data_offsets")
                formats = {"F32": ("<f", 4), "F16": ("<e", 2), "BF16": (None, 2)}
                fmt_and_size = formats.get(spec.get("dtype"))
                if (shape not in ([], [1]) or fmt_and_size is None
                        or not isinstance(offsets, list) or len(offsets) != 2
                        or offsets[1] - offsets[0] != fmt_and_size[1]):
                    raise SchemaInspectionError("Unsupported input scale scalar dtype or shape.")
                handle.seek(8 + length + offsets[0])
                raw_scalar = handle.read(fmt_and_size[1])
                if len(raw_scalar) != fmt_and_size[1]:
                    raise SchemaInspectionError("Truncated input scale.")
                if spec["dtype"] == "BF16":
                    # BF16 1.0 is exactly 0x3f80; reject non-unit and NaN codes.
                    is_unit = struct.unpack("<H", raw_scalar)[0] == 0x3F80
                else:
                    is_unit = struct.unpack(fmt_and_size[0], raw_scalar)[0] == 1.0
                if not is_unit:
                    raise SchemaInspectionError(
                        "Non-unit .scale_input requires explicitly verified input-scale handling."
                    )
                removed_unit_scales += 1
                continue
            result[name] = tuple(spec["shape"])
    return result, removed_unit_scales

def _original_transformer_shapes(
    original: dict[str, tuple[int, ...]],
) -> tuple[dict[str, tuple[int, ...]], int]:
    """Reproduce Diffusers' Z-Image single-file renames as schema operations."""
    results: dict[str, tuple[int, ...]] = {}
    splits = 0
    for original_name, shape in original.items():
        name = original_name.removeprefix("model.diffusion_model.")
        for old, new in (
            ("final_layer.", "all_final_layer.2-1."),
            ("x_embedder.", "all_x_embedder.2-1."),
            (".attention.out.bias", ".attention.to_out.0.bias"),
            (".attention.k_norm.weight", ".attention.norm_k.weight"),
            (".attention.q_norm.weight", ".attention.norm_q.weight"),
            (".attention.out.weight", ".attention.to_out.0.weight"),
        ):
            name = name.replace(old, new)
        if name == "norm_final.weight":
            continue
        if name.endswith(".attention.qkv.weight"):
            if len(shape) < 2 or shape[0] % 3:
                raise SchemaInspectionError("Fused QKV shape cannot be split into three.")
            parts = (shape[0] // 3, *shape[1:])
            splits += 1
            for part in ("q", "k", "v"):
                target = name.replace(".attention.qkv.weight", f".attention.to_{part}.weight")
                if target in results:
                    raise SchemaInspectionError("Duplicate mapped QKV tensor name.")
                results[target] = parts
        else:
            if name in results:
                raise SchemaInspectionError("Duplicate mapped tensor name.")
            results[name] = shape
    if not results:
        raise SchemaInspectionError("No mapped transformer parameters.")
    # Independent existing conservative mapping gate must agree with this plan.
    try:
        plan_original_tensor_mapping(original, results)
    except ConversionPreflightError as exc:
        raise SchemaInspectionError("Legacy mapping gate disagrees with target plan.") from exc
    return results, splits


def compare_tensor_schemas(
    external: dict[str, tuple[int, ...]],
    managed: dict[str, tuple[int, ...]],
) -> dict[str, Any]:
    """Pure exact names/shapes comparison with bounded discrepancy examples."""
    missing = sorted(set(managed) - set(external))
    extra = sorted(set(external) - set(managed))
    wrong = [
        {"name": k, "external": list(external[k]), "managed": list(managed[k])}
        for k in sorted(set(external) & set(managed))
        if external[k] != managed[k]
    ]
    exact = not missing and not extra and not wrong and bool(external) and bool(managed)
    return {
        "status": "schema_matches" if exact else "schema_mismatch",
        "mapped_tensor_count": len(external), "reference_tensor_count": len(managed),
        "missing_reference_tensors": len(missing), "unexpected_external_tensors": len(extra),
        "shape_mismatches": len(wrong),
        "missing_examples": missing[:MAX_REPORT_ITEMS],
        "unexpected_examples": extra[:MAX_REPORT_ITEMS],
        "shape_mismatch_examples": wrong[:MAX_REPORT_ITEMS],
        "schema_verified": exact,
        "loadable": False, "conversion_enabled": False, "runtime_verified": False,
    }


def validate_complete_tensor_schema(
    external_checkpoint: str | Path,
    managed_root: str | Path, *,
    family: str,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full header-only comparison; fail closed on unavailable reference shards."""
    result = {
        "status": "blocked", "family": family,
        "schema_verified": False, "loadable": False,
        "conversion_enabled": False, "runtime_verified": False,
    }
    try:
        source = Path(external_checkpoint)
        inspection = inspect_zimage_checkpoint(source)
        expected_status = ("auxiliary" if family == "encoder" else "needs_components")
        if inspection.get("status") != expected_status:
            raise SchemaInspectionError("External checkpoint architecture is unrecognized.")
        if family == "encoder" and inspection.get("component_type") != "text_encoder":
            raise SchemaInspectionError("External file is not a Qwen-like encoder.")
        if family == "transformer" and inspection.get("architecture") != "zimage_original_transformer":
            raise SchemaInspectionError("Only original Z-Image transformer mapping is supported.")
        evidence = validation if validation is not None else validate_fp8_single_file(source)
        if evidence.get("status") != "reference_matched":
            raise SchemaInspectionError("Z2.15 complete FP8 scale checks have not passed.")
        stat = source.stat()
        shapes, discarded_unit_input_scales = _external_shapes(source)
        if family == "transformer":
            mapped, qkv_count = _original_transformer_shapes(shapes)
        elif family == "encoder":
            mapped, qkv_count = shapes, 0
        else:
            raise SchemaInspectionError("Unknown model family.")
        managed = read_managed_component_schema(managed_root, family)
        after = source.stat()
        if stat.st_size != after.st_size or stat.st_mtime_ns != after.st_mtime_ns:
            raise SchemaInspectionError("External checkpoint changed during schema analysis.")
        result.update(compare_tensor_schemas(mapped, managed))
        result["fused_qkv_splits"] = qkv_count
        result["source_parameter_count"] = len(shapes)
        result["discarded_unit_input_scale_count"] = discarded_unit_input_scales
        result["reference_origin"] = "managed_Z-Image-Turbo_sharded_safetensors_headers"
        return result
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError,
            struct.error) as exc:
        result["reason"] = str(exc)[:220]
        return result

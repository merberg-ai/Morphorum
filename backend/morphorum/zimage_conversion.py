"""Z2.5 isolated conversion staging policy for standalone Z-Image.

Planning only: does not deserialize tensors, execute converters, or authorize loading.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .zimage_inspect import inspect_zimage_checkpoint


class ConversionPreflightError(ValueError):
    pass


def plan_conversion(checkpoint: str | Path, cache_root: str | Path) -> dict[str, Any]:
    """Prepare a deterministic, non-executable conversion location.

    The fingerprint includes canonical source path and file metadata, so an
    overwritten or modified checkpoint cannot silently reuse a stale cache.
    """
    file = Path(checkpoint).expanduser()
    cache = Path(cache_root).expanduser()
    if file.is_symlink() or not file.is_file():
        raise ConversionPreflightError("Checkpoint must be an existing regular non-symlink file.")
    if cache.is_symlink():
        raise ConversionPreflightError("Cache root must not be a symlink.")
    file = file.resolve(strict=True)
    cache = cache.resolve(strict=False)
    if file == cache or cache == file.parent or file in cache.parents:
        raise ConversionPreflightError("Conversion cache cannot be the checkpoint or its ancestor.")
    if file.parent == cache or cache in file.parents:
        raise ConversionPreflightError("Conversion cache cannot contain the source checkpoint.")
    stat = file.stat()
    inspection = inspect_zimage_checkpoint(file)
    layout = inspection.get("architecture")
    precision = inspection.get("tensor_validation", {}).get("precision")
    if inspection.get("status") != "needs_components" or layout not in {
        "zimage_original_transformer", "zimage_diffusers_transformer"
    }:
        raise ConversionPreflightError("Checkpoint architecture is unverified or structurally rejected.")
    if precision != "floating" or any(k.startswith("F8_") or k == "F4"
                                       for k in inspection.get("dtypes", {})):
        raise ConversionPreflightError("Quantized checkpoint mapping is not verified; FP8 conversion is blocked.")
    if set(inspection.get("dtypes", {})) - {"F16", "BF16", "F32", "F64"}:
        raise ConversionPreflightError("Unexpected tensor dtype; explicit converter support is required.")
    signature = "|".join((os.path.normcase(str(file)), str(stat.st_size), str(stat.st_mtime_ns), layout))
    cache_id = hashlib.sha256(signature.encode("utf-8", "surrogatepass")).hexdigest()[:32]
    destination = cache / "standalone-zimage" / cache_id
    # The cache is not created here. A future writer must use atomic staging,
    # verify target paths and tensor mapping, then publish a validated manifest.
    return {
        "source": "external",
        "checkpoint": str(file),
        "source_size_bytes": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "architecture": layout,
        "strategy": "convert_original_to_diffusers" if layout == "zimage_original_transformer"
                    else "verify_diffusers_tensor_mapping",
        "cache_destination": str(destination),
        "cache_key": cache_id,
        "state": "planning_only",
        "ready": False,
        "loadable": False,
        "conversion_enabled": False,
        "reason": "A matching converter, complete component verification and runtime acceptance are required.",
    }


def stage_verified_tensor_copy(
    checkpoint: str | Path,
    cache_root: str | Path,
    *,
    expected_tensor_shapes: dict[str, tuple[int, ...]],
) -> dict[str, Any]:
    """Atomically stage only an exactly matched Diffusers-layout state dict.

    This is a conservative executable byte-preserving staging primitive, not
    an original-layout converter or a production-ready model. Explicit expected
    tensor keys/shapes must come from an independently verified architecture
    schema. No partial or extra weights are accepted, and no GPU is used.
    """
    import json
    import shutil
    import tempfile
    import struct

    plan = plan_conversion(checkpoint, cache_root)
    if plan["architecture"] != "zimage_diffusers_transformer":
        raise ConversionPreflightError("Original-layout conversion mapping is not yet verified.")
    if not expected_tensor_shapes:
        raise ConversionPreflightError("Complete expected tensor schema is required.")
    file = Path(plan["checkpoint"])
    # Read the bounded header only, not the model payload.
    with file.open("rb") as handle:
        size = struct.unpack("<Q", handle.read(8))[0]
        if size > 16 * 1024 * 1024:
            raise ConversionPreflightError("Safetensors header exceeds safety bound.")
        fields = json.loads(handle.read(size))
    fields.pop("__metadata__", None)
    if set(fields) != set(expected_tensor_shapes):
        raise ConversionPreflightError("Checkpoint tensor names do not exactly match the verified schema.")
    for key, dims in expected_tensor_shapes.items():
        spec = fields[key]
        if not isinstance(dims, tuple) or tuple(spec["shape"]) != dims:
            raise ConversionPreflightError(f"Tensor shape mismatch: {key[:120]}")
    destination = Path(plan["cache_destination"])
    if destination.exists() or destination.is_symlink():
        raise ConversionPreflightError("Cache destination already exists; refusing overwrite.")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".zimage-stage-", dir=str(parent)))
    try:
        target = temp / "diffusion_pytorch_model.safetensors"
        with file.open("rb") as source, target.open("xb") as output:
            shutil.copyfileobj(source, output, length=4 * 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if target.stat().st_size != plan["source_size_bytes"]:
            raise ConversionPreflightError("Copied tensor payload size does not match the source.")
        # Source can change mid-copy; conservatively reject rather than publish.
        after = file.stat()
        if after.st_size != plan["source_size_bytes"] or after.st_mtime_ns != plan["source_mtime_ns"]:
            raise ConversionPreflightError("Source checkpoint changed during staging.")
        source_sha256 = hashlib.sha256()
        staged_sha256 = hashlib.sha256()
        for item, digest in ((file, source_sha256), (target, staged_sha256)):
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
        if source_sha256.digest() != staged_sha256.digest():
            raise ConversionPreflightError("Staged checkpoint checksum differs from original.")
        manifest = {
            "schema": 1, "kind": "unverified_diffusers_weight_stage",
            "source": plan["checkpoint"], "cache_key": plan["cache_key"],
            "tensor_count": len(fields), "runtime_verified": False, "loadable": False,
            "source_sha256": source_sha256.hexdigest(),
            "staged_sha256": staged_sha256.hexdigest(),
        }
        (temp / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8"
        )
        os.rename(temp, destination)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return {
        **plan, "state": "staged_unverified", "staged_file": str(destination / target.name),
        "conversion_enabled": False, "ready": False, "loadable": False,
    }


def plan_original_tensor_mapping(
    tensor_shapes: dict[str, tuple[int, ...]],
    expected_output_shapes: dict[str, tuple[int, ...]],
) -> dict[str, Any]:
    """Validate a complete original-to-Diffusers mapping without loading weights.

    Mirrors the upstream Z-Image renames and fused QKV splitting. A caller must
    supply an independently obtained *complete* target architecture schema.
    """
    if not tensor_shapes or not expected_output_shapes:
        raise ConversionPreflightError("Both complete source and target tensor schemas are required.")
    mapped: dict[str, tuple[int, ...]] = {}
    operations: list[dict[str, Any]] = []
    for original, shape in tensor_shapes.items():
        if not isinstance(shape, tuple) or not shape or any(type(n) is not int or n <= 0 for n in shape):
            raise ConversionPreflightError("Invalid source tensor shape.")
        key = original.removeprefix("model.diffusion_model.")
        if key == "norm_final.weight":
            continue  # Explicit upstream excluded tensor.
        for old, new in (
            ("final_layer.", "all_final_layer.2-1."),
            ("x_embedder.", "all_x_embedder.2-1."),
            (".attention.out.bias", ".attention.to_out.0.bias"),
            (".attention.k_norm.weight", ".attention.norm_k.weight"),
            (".attention.q_norm.weight", ".attention.norm_q.weight"),
            (".attention.out.weight", ".attention.to_out.0.weight"),
        ):
            key = key.replace(old, new)
        if key.endswith(".attention.qkv.weight"):
            if len(shape) < 2 or shape[0] % 3:
                raise ConversionPreflightError("Fused QKV first dimension must be divisible by 3.")
            split_shape = (shape[0] // 3, *shape[1:])
            for part in ("q", "k", "v"):
                target = key.replace(".attention.qkv.weight", f".attention.to_{part}.weight")
                if target in mapped:
                    raise ConversionPreflightError("Duplicate converted tensor key.")
                mapped[target] = split_shape
            operations.append({"source": original, "action": "split_qkv", "targets": [
                key.replace(".attention.qkv.weight", f".attention.to_{p}.weight") for p in ("q", "k", "v")
            ]})
        else:
            if key in mapped:
                raise ConversionPreflightError("Duplicate converted tensor key.")
            mapped[key] = shape
            operations.append({"source": original, "action": "rename", "targets": [key]})
    if mapped != expected_output_shapes:
        raise ConversionPreflightError("Mapped tensor names and shapes do not exactly match target schema.")
    return {
        "status": "schema_verified_mapping_only",
        "operations": operations,
        "tensor_count": len(mapped),
        "ready": False, "loadable": False, "conversion_enabled": False,
    }

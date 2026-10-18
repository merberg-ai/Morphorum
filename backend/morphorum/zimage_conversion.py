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
        manifest = {
            "schema": 1, "kind": "unverified_diffusers_weight_stage",
            "source": plan["checkpoint"], "cache_key": plan["cache_key"],
            "tensor_count": len(fields), "runtime_verified": False, "loadable": False,
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

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

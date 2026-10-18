"""Z2.16 isolated FP8-to-BF16 window experiment.

Never writes model-sized tensors, touches managed installations, converts the
entire state dict, or authorizes production loading. Diagnostic planning only
reads safetensors headers; publishing requires an explicit isolated directory.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile
from typing import Any

from .zimage_fp8_validation import validate_fp8_single_file
from .zimage_inspect import MAX_HEADER_BYTES, inspect_zimage_checkpoint

MAX_TENSORS = 2
MAX_ELEMENTS_PER_WINDOW = 64
MAX_WINDOWS = 4


class FP8PrototypeError(ValueError):
    """Safety preflight error for an optional, non-production experiment."""


def _header(source: Path) -> tuple[dict[str, Any], int]:
    with source.open("rb") as stream:
        length_bytes = stream.read(8)
        if len(length_bytes) != 8:
            raise FP8PrototypeError("Truncated safetensors length prefix.")
        count = struct.unpack("<Q", length_bytes)[0]
        if count < 2 or count > MAX_HEADER_BYTES:
            raise FP8PrototypeError("Unsafe safetensors header size.")
        content = stream.read(count)
        if len(content) != count:
            raise FP8PrototypeError("Truncated safetensors header.")
    data = json.loads(content)
    data.pop("__metadata__", None)
    return data, 8 + count


def _choose_keys(header: dict[str, Any], family: str) -> list[str]:
    weights = sorted(
        k for k, v in header.items()
        if k.endswith(".weight") and v["dtype"] == "F8_E4M3"
    )
    if family == "transformer":
        qkv = next((k for k in weights if k.endswith(".attention.qkv.weight")), None)
        regular = next((k for k in weights if ".attention.qkv.weight" not in k), None)
        candidates = [regular, qkv]
    else:
        candidates = [
            next((k for k in weights if k.endswith(".self_attn.q_proj.weight")), None),
            next((k for k in weights if k.endswith(".mlp.down_proj.weight")), None),
        ]
    return [k for k in candidates if k is not None][:MAX_TENSORS]


def plan_fp8_bf16_windows(path: str | Path, *,
                          validated: dict[str, Any] | None = None) -> dict[str, Any]:
    """Choose bounded real-tensor windows after full independent Z2.15 validation.

    Returns a read-only plan; no paths for model installation or loader approval.
    """
    source = Path(path)
    inspection = inspect_zimage_checkpoint(source)
    family = (
        "encoder" if inspection.get("component_type") == "text_encoder" else
        "transformer" if inspection.get("architecture") == "zimage_original_transformer" else
        None
    )
    result: dict[str, Any] = {
        "status": "blocked", "kind": "z2.16_bf16_window_only",
        "family": family, "windows": [], "ready": False, "loadable": False,
        "conversion_enabled": False, "full_checkpoint_conversion": False,
    }
    if family is None or source.is_symlink():
        result["reason"] = "Unrecognized layout or unsafe source."
        return result
    evidence = validated if validated is not None else validate_fp8_single_file(source)
    if evidence.get("status") != "reference_matched":
        result["reason"] = "Independent Z2.15 CPU reference validation must pass."
        return result
    stat = source.stat()
    header, _ = _header(source)
    keys = _choose_keys(header, family)
    if not keys:
        result["reason"] = "No appropriate FP8 window selection."
        return result

    for key in keys:
        spec = header[key]
        dims = spec["shape"]
        if not dims or any(type(d) is not int or d < 1 for d in dims):
            result["reason"] = "Invalid FP8 weight dimensions."
            return result
        scale_key = key[:-len(".weight")] + ".scale_weight"
        if scale_key not in header:
            result["reason"] = "Selected weight has no scale tensor."
            return result
        count = math.prod(dims)
        regions = [("full", 0, count, key)]
        if key.endswith(".attention.qkv.weight"):
            if len(dims) != 2 or dims[0] % 3:
                result["reason"] = "Fused QKV needs rank two and divisible first axis."
                return result
            partition = count // 3
            regions = [
                (part, i * partition, partition,
                 key.replace(".attention.qkv.weight", f".attention.to_{part}.weight"))
                for i, part in enumerate(("q", "k", "v"))
            ]
        for part, offset, region_elements, target in regions:
            length = min(MAX_ELEMENTS_PER_WINDOW, region_elements)
            result["windows"].append({
                "source_tensor": key, "target_hint": target, "partition": part,
                "source_shape": dims, "element_offset": offset,
                "elements": length, "output_dtype": "BF16",
                "output_shape": [length],
                "is_model_tensor": False,
            })
    if len(result["windows"]) > MAX_WINDOWS:
        result["reason"] = "Window count exceeds experiment bound."
        result["windows"] = []
        return result
    result.update({
        "status": "planned", "reason": "A preview plan, not permission to load.",
        "source_size_bytes": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "windows_count": len(result["windows"]),
        "max_source_bytes": sum(w["elements"] for w in result["windows"]),
        "max_bf16_bytes": sum(w["elements"] * 2 for w in result["windows"]),
        "managed_components_used": False,
    })
    return result


def _check_isolated_destination(source: Path, destination: Path,
                                managed_root: str | Path | None) -> None:
    if source.is_symlink() or destination.is_symlink():
        raise FP8PrototypeError("Symlink source/destination is not allowed.")
    original = source.resolve(strict=True)
    scratch = destination.resolve(strict=False)
    model_dir = original.parent
    if (scratch == model_dir or model_dir in scratch.parents or
            scratch in model_dir.parents or scratch == original):
        raise FP8PrototypeError("Experiment output must be outside the checkpoint tree.")
    if managed_root is not None:
        managed = Path(managed_root).resolve(strict=False)
        if scratch == managed or managed in scratch.parents or scratch in managed.parents:
            raise FP8PrototypeError("Experiment output must be outside the managed model tree.")
    if scratch.exists() or scratch.is_symlink():
        raise FP8PrototypeError("Experiment output directory already exists.")
    # Prevent traversing through symlinks in any existing destination ancestor.
    for parent in (destination, *destination.parents):
        if parent.is_symlink():
            raise FP8PrototypeError("Symlink destination ancestor is not allowed.")


def export_fp8_bf16_windows(
    checkpoint: str | Path,
    output_directory: str | Path, *,
    managed_root: str | Path | None = None,
) -> dict[str, Any]:
    """Explicit opt-in: atomically write ONLY small BF16 sample windows.

    Never called by model scanning, diagnostics, generators, or the updater.
    Requires CPU PyTorch. No source mutation, no GPU, no model loading.
    """
    import torch
    from .zimage_cache import CacheIntegrityError, ExclusiveCacheReservation

    if not hasattr(torch, "float8_e4m3fn"):
        raise FP8PrototypeError("CPU PyTorch FP8 support unavailable.")
    source = Path(checkpoint)
    destination = Path(output_directory)
    # Always protect Morphorum's configured managed-model directory. An
    # optional extra root extends protection; it never disables the default.
    from .settings import managed_model_location
    _check_isolated_destination(source, destination, managed_model_location("zimage"))
    if managed_root is not None:
        _check_isolated_destination(source, destination, managed_root)
    plan = plan_fp8_bf16_windows(source)
    if plan["status"] != "planned":
        raise FP8PrototypeError(plan["reason"])
    header, payload_start = _header(source)
    before = source.stat()
    tensor_entries = {}
    payload = bytearray()
    manifest_windows = []
    with source.open("rb") as stream:
        for index, item in enumerate(plan["windows"]):
            source_key = item["source_tensor"]
            spec = header[source_key]
            scale_key = source_key[:-len(".weight")] + ".scale_weight"
            scale_spec = header[scale_key]
            scale_offset = scale_spec["data_offsets"][0]
            stream.seek(payload_start + scale_offset)
            scale_data = stream.read(4)
            if len(scale_data) != 4:
                raise FP8PrototypeError("Scale truncated during window extraction.")
            scale = struct.unpack("<f", scale_data)[0]
            if not math.isfinite(scale) or scale <= 0:
                raise FP8PrototypeError("Invalid scale during window extraction.")
            data_offset = spec["data_offsets"][0] + item["element_offset"]
            stream.seek(payload_start + data_offset)
            values = stream.read(item["elements"])
            if len(values) != item["elements"]:
                raise FP8PrototypeError("FP8 window truncated.")
            # Follows comfy-kitchen's default BF16 computation: cast both
            # inputs to BF16 before multiplying, not F32 multiply then cast.
            fp8_values = torch.frombuffer(bytearray(values), dtype=torch.uint8)
            fp8_values = fp8_values.view(torch.float8_e4m3fn)
            bf16_scale = torch.tensor(scale, dtype=torch.bfloat16, device="cpu")
            converted = fp8_values.to(dtype=torch.bfloat16) * bf16_scale
            if not bool(torch.isfinite(converted).all().item()):
                raise FP8PrototypeError("Nonfinite dequantized window.")
            # Independently decode the exact FP8 bytes and verify the BF16
            # result via a separately created tensor on CPU.
            from .zimage_fp8_evidence import _decode_e4m3fn_byte
            decoded = [_decode_e4m3fn_byte(value) for value in values]
            if any(v is None for v in decoded):
                raise FP8PrototypeError("NaN FP8 code in selected window.")
            reference = torch.tensor(decoded, dtype=torch.float32).to(torch.bfloat16)
            reference = reference * bf16_scale
            if not torch.equal(converted, reference):
                raise FP8PrototypeError("FP8-to-BF16 reference mismatch.")
            raw = converted.contiguous().view(torch.uint8).numpy().tobytes()
            if len(raw) != item["elements"] * 2:
                raise FP8PrototypeError("BF16 window byte count mismatch.")
            name = f"prototype_window_{index:03d}"
            start = len(payload)
            payload.extend(raw)
            tensor_entries[name] = {
                "dtype": "BF16", "shape": item["output_shape"],
                "data_offsets": [start, len(payload)],
            }
            manifest_windows.append({
                **item, "output_name": name, "scale": scale,
                "source_sample_sha256": hashlib.sha256(values).hexdigest(),
                "output_sample_sha256": hashlib.sha256(raw).hexdigest(),
                "reference": "cpu_torch_bf16_cast_then_multiply",
                "verified": True,
            })
    after = source.stat()
    if (after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns or
            after.st_size != plan["source_size_bytes"] or
            after.st_mtime_ns != plan["source_mtime_ns"]):
        raise FP8PrototypeError("Source changed during experiment.")

    serialized = json.dumps(tensor_entries, sort_keys=True, separators=(",", ":")).encode()
    output_bytes = struct.pack("<Q", len(serialized)) + serialized + payload
    manifest = {
        "schema": 1, "kind": "z2.16_nonloadable_bf16_windows",
        "source_size_bytes": before.st_size,
        "source_mtime_ns": before.st_mtime_ns,
        "samples": manifest_windows,
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "managed_components_used": False, "ready": False,
        "loadable": False, "conversion_enabled": False,
    }
    try:
        lock = ExclusiveCacheReservation(destination)
        lock.__enter__()
    except CacheIntegrityError as exc:
        raise FP8PrototypeError(str(exc)) from exc
    temporary = None
    try:
        temporary = Path(tempfile.mkdtemp(prefix=".zimage-fp8-prototype-", dir=destination.parent))
        with (temporary / "samples.safetensors").open("xb") as handle:
            handle.write(output_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        with (temporary / "manifest.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        # Verify independent file header/byte ranges and manifest digest.
        with (temporary / "samples.safetensors").open("rb") as handle:
            count = struct.unpack("<Q", handle.read(8))[0]
            actual_header = json.loads(handle.read(count))
            actual_payload = handle.read()
        if (actual_header != tensor_entries or actual_payload != payload or
                hashlib.sha256((temporary / "samples.safetensors").read_bytes()).hexdigest()
                != manifest["output_sha256"]):
            raise FP8PrototypeError("Export integrity verification failed.")
        if destination.exists():
            raise FP8PrototypeError("Experiment destination appeared concurrently.")
        os.rename(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        lock.__exit__(None, None, None)
    return {
        "status": "sample_windows_exported", "output_directory": str(destination),
        "window_count": len(manifest_windows),
        "bf16_payload_bytes": len(payload),
        "ready": False, "loadable": False, "conversion_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI defaults to inspection; --export is required before any write."""
    import argparse
    parser = argparse.ArgumentParser(description="Z2.16 isolated FP8 BF16 window experiment")
    parser.add_argument("--checkpoint", required=True, help="Existing safetensors source")
    parser.add_argument("--output", help="Fresh scratch directory, outside checkpoint and managed trees")
    parser.add_argument("--managed-root", help="Optional managed package root for write protection")
    parser.add_argument("--export", action="store_true", help="Explicitly write tiny non-loadable samples")
    args = parser.parse_args(argv)
    if args.export:
        if not args.output:
            parser.error("--export requires --output")
        try:
            result = export_fp8_bf16_windows(
                args.checkpoint, args.output, managed_root=args.managed_root
            )
        except (FP8PrototypeError, OSError) as exc:
            parser.error(str(exc))
    else:
        result = plan_fp8_bf16_windows(args.checkpoint)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("planned", "sample_windows_exported") else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Z2.18 isolated streaming FP8 -> BF16 experiment, NEVER a runtime loader.

Read-only planner is safe in diagnostics. Writing needs an explicit command-line
--export, new scratch path, complete real managed schema match, and disk budget.
All source/managed files remain untouched; published output is non-loadable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile
from typing import Any

from .settings import managed_model_location
from .zimage_cache import CacheIntegrityError, ExclusiveCacheReservation, sha256_file
from .zimage_conversion import plan_original_tensor_mapping
from .zimage_schema_validation import (
    _external_shapes, read_managed_component_schema, validate_complete_tensor_schema,
)
from .zimage_inspect import MAX_HEADER_BYTES

CHUNK = 2 * 1024 * 1024
RESERVE_BYTES = 2 * 1024 ** 3
MAX_OUTPUT_BYTES = 80 * 1024 ** 3
MAX_OUTPUT_TENSORS = 12000
_SUPPORTED_COPY = {"F32": 4, "BF16": 2, "F16": 2}


class FP8StreamError(ValueError):
    pass


def _load_header(source: Path) -> tuple[dict[str, Any], int]:
    if source.is_symlink() or not source.is_file():
        raise FP8StreamError("Unsafe or missing checkpoint.")
    with source.open("rb") as f:
        raw = f.read(8)
        if len(raw) != 8:
            raise FP8StreamError("Truncated safetensors file.")
        size = struct.unpack("<Q", raw)[0]
        if size < 2 or size > MAX_HEADER_BYTES or size + 8 > source.stat().st_size:
            raise FP8StreamError("Invalid safetensors header size.")
        body = f.read(size)
        if len(body) != size:
            raise FP8StreamError("Truncated safetensors header.")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise FP8StreamError("Malformed safetensors header.") from exc
    if not isinstance(data, dict):
        raise FP8StreamError("Malformed safetensors tensor map.")
    data.pop("__metadata__", None)
    return data, 8 + size


def _valid_destination(source: Path, dest: Path, managed_root: Path):
    managed_defaults = managed_model_location("zimage")
    src_dir = source.resolve(strict=True).parent
    dst = dest.resolve(strict=False)
    for path in (dest, *dest.parents):
        if path.is_symlink():
            raise FP8StreamError("Symlink destination or parent is forbidden.")
    for protected in (src_dir, managed_root.resolve(strict=False), managed_defaults):
        if dst == protected or protected in dst.parents or dst in protected.parents:
            raise FP8StreamError("Scratch destination intersects source or managed model directory.")
    if dest.exists() or dest.is_symlink():
        raise FP8StreamError("Scratch destination must be new, no overwrite permitted.")


def _free_space(destination: Path) -> int | None:
    existing = destination
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    try:
        return shutil.disk_usage(existing).free
    except OSError:
        return None


def _tensor_actions(source: Path, managed: Path, family: str):
    header, payload_start = _load_header(source)
    shapes, calibration = _external_shapes(source)
    target = read_managed_component_schema(managed, family)
    if family == "transformer":
        operations = plan_original_tensor_mapping(shapes, target)["operations"]
    elif family == "encoder":
        if shapes != target:
            raise FP8StreamError("Qwen encoder parameters do not exactly match managed reference.")
        operations = [{"source": key, "action": "rename", "targets": [key]}
                      for key in shapes]
    else:
        raise FP8StreamError("Unsupported checkpoint family.")
    actions = []
    size = 0
    for op in operations:
        src = op["source"]
        spec = header[src]
        shape = tuple(spec["shape"])
        dtype = spec["dtype"]
        if dtype == "F8_E4M3":
            dest_dtype, stride = "BF16", 2
            scale_key = src[:-len(".weight")] + ".scale_weight"
            scale_spec = header.get(scale_key)
            if scale_spec is None or scale_spec.get("dtype") != "F32" or scale_spec.get("shape") != [1]:
                raise FP8StreamError("Missing scalar FP8 weight scale.")
        elif dtype in _SUPPORTED_COPY:
            dest_dtype, stride = dtype, _SUPPORTED_COPY[dtype]
            scale_key = None
        else:
            raise FP8StreamError("Unsupported parameter dtype.")
        offset_start, offset_end = spec["data_offsets"]
        if dtype == "F8_E4M3":
            if offset_end - offset_start != math.prod(shape):
                raise FP8StreamError("FP8 tensor length/shape mismatch.")
        elif offset_end - offset_start != math.prod(shape) * stride:
            raise FP8StreamError("Floating tensor length/shape mismatch.")
        if len(op["targets"]) not in (1, 3):
            raise FP8StreamError("Invalid mapped output count.")
        if len(op["targets"]) == 3 and (len(shape) < 2 or shape[0] % 3):
            raise FP8StreamError("Invalid fused QKV dimensions.")
        for index, key in enumerate(op["targets"]):
            target_shape = target[key]
            count = math.prod(target_shape)
            raw_unit = 1 if dtype == "F8_E4M3" else stride
            raw_count = count * raw_unit
            read_offset = offset_start + index * raw_count
            if read_offset + raw_count > offset_end:
                raise FP8StreamError("QKV split exceeds source tensor bounds.")
            written = count * stride
            actions.append({
                "name": key, "source": src, "shape": list(target_shape),
                "source_dtype": dtype, "output_dtype": dest_dtype,
                "source_offset": read_offset, "source_bytes": raw_count,
                "output_offset": size, "output_bytes": written, "scale_key": scale_key,
            })
            size += written
    if not actions or len(actions) > MAX_OUTPUT_TENSORS or size > MAX_OUTPUT_BYTES:
        raise FP8StreamError("Unsafe converted tensor count or output size.")
    if set(a["name"] for a in actions) != set(target):
        raise FP8StreamError("Final output schema is incomplete.")
    return header, payload_start, actions, calibration, size


def plan_fp8_stream(checkpoint: str | Path, managed_root: str | Path,
                    *, family: str, scratch: str | Path | None = None) -> dict[str, Any]:
    """Exact output-dtype and byte budget; NO filesystem writes."""
    result: dict[str, Any] = {
        "status": "blocked", "family": family, "mode": "read_only_preflight",
        "conversion_enabled": False, "loadable": False, "runtime_verified": False,
    }
    try:
        source = Path(checkpoint)
        managed = Path(managed_root)
        reference = validate_complete_tensor_schema(source, managed, family=family)
        if reference["status"] != "schema_matches":
            raise FP8StreamError("Z2.17.2 exact model schema and FP8 scale checks must pass.")
        _, _, actions, calibration, payload = _tensor_actions(source, managed, family)
        specs = {}
        position = 0
        for action in actions:
            specs[action["name"]] = {
                "dtype": action["output_dtype"], "shape": action["shape"],
                "data_offsets": [position, position + action["output_bytes"]],
            }
            position += action["output_bytes"]
        header_length = len(json.dumps(specs, separators=(",", ":")).encode("utf-8"))
        if header_length > MAX_HEADER_BYTES:
            raise FP8StreamError("Output header exceeds bound.")
        exact_total = 8 + header_length + payload
        source_fp8 = sum(a["source_bytes"] for a in actions if a["source_dtype"] == "F8_E4M3")
        result.update({
            "status": "planned", "source_size_bytes": source.stat().st_size,
            "output_payload_bytes": payload, "output_exact_bytes": exact_total,
            "disk_required_bytes": exact_total + RESERVE_BYTES,
            "disk_reserve_bytes": RESERVE_BYTES, "tensor_count": len(actions),
            "fp8_output_tensors": sum(a["source_dtype"] == "F8_E4M3" for a in actions),
            "fp8_input_bytes": source_fp8,
            "max_input_chunk_bytes": CHUNK, "estimated_peak_conversion_ram_bytes": 8 * CHUNK,
            "activation_scale_count": calibration["count"],
            "activation_scales_required_for_bf16_linear": False,
            "fp8_runtime_scale_binding_verified": False,
            "managed_components_used": False,
            "note": "CPU streaming only. Does not prove 16GB GPU inference feasibility.",
        })
        if scratch is not None:
            destination = Path(scratch)
            _valid_destination(source, destination, managed)
            free = _free_space(destination)
            result["scratch_free_bytes"] = free
            result["scratch_space_sufficient"] = free is not None and free >= result["disk_required_bytes"]
            if not result["scratch_space_sufficient"]:
                result["status"] = "insufficient_disk"
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        result["reason"] = str(exc)[:250]
    return result


def export_fp8_stream(checkpoint: str | Path, managed_root: str | Path,
                      *, family: str, scratch: str | Path) -> dict[str, Any]:
    """Explicit, non-loadable BF16 parameter export into an isolated directory."""
    import torch

    source = Path(checkpoint)
    managed = Path(managed_root)
    destination = Path(scratch)
    _valid_destination(source, destination, managed)
    plan = plan_fp8_stream(source, managed, family=family, scratch=destination)
    if plan["status"] != "planned":
        raise FP8StreamError(plan.get("reason", plan["status"]))
    header, payload_start, actions, _, payload_bytes = _tensor_actions(source, managed, family)
    source_stat = source.stat()
    if payload_bytes != plan["output_payload_bytes"]:
        raise FP8StreamError("Output budget changed between preflight and export.")
    specs = {
        row["name"]: {"dtype": row["output_dtype"], "shape": row["shape"],
                      "data_offsets": [row["output_offset"], row["output_offset"] + row["output_bytes"]]}
        for row in actions
    }
    encoded = json.dumps(specs, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_HEADER_BYTES:
        raise FP8StreamError("Output header exceeds safety bound.")
    if 8 + len(encoded) + payload_bytes != plan["output_exact_bytes"]:
        raise FP8StreamError("Output bytes differ from preflight.")
    temp = None
    try:
        with ExclusiveCacheReservation(destination):
            temp = Path(tempfile.mkdtemp(prefix=".z218-stream-", dir=destination.parent))
            filename = "diffusion_pytorch_model.safetensors" if family == "transformer" else "model.safetensors"
            artifact = temp / filename
            per_tensor_hashes = {}
            with source.open("rb") as src, artifact.open("xb") as out:
                out.write(struct.pack("<Q", len(encoded)))
                out.write(encoded)
                for row in actions:
                    scale = None
                    if row["scale_key"] is not None:
                        scale_spec = header[row["scale_key"]]
                        src.seek(payload_start + scale_spec["data_offsets"][0])
                        scale_data = src.read(4)
                        if len(scale_data) != 4:
                            raise FP8StreamError("FP8 scale truncated.")
                        scale = torch.tensor(struct.unpack("<f", scale_data)[0],
                                             dtype=torch.bfloat16, device="cpu")
                        if not bool(torch.isfinite(scale).item()) or float(scale) <= 0:
                            raise FP8StreamError("Invalid FP8 scalar weight scale.")
                    digest = hashlib.sha256()
                    src.seek(payload_start + row["source_offset"])
                    remaining = row["source_bytes"]
                    produced = 0
                    while remaining:
                        chunk = src.read(min(remaining, CHUNK))
                        if not chunk:
                            raise FP8StreamError("Source truncated during streaming.")
                        if scale is not None:
                            tensor = torch.frombuffer(bytearray(chunk), dtype=torch.uint8).view(
                                torch.float8_e4m3fn
                            ).to(torch.bfloat16)
                            converted = tensor * scale
                            if not bool(torch.isfinite(converted).all().item()):
                                raise FP8StreamError("Nonfinite FP8 conversion output.")
                            output = converted.contiguous().view(torch.uint8).numpy().tobytes()
                        else:
                            output = chunk
                        out.write(output)
                        digest.update(output)
                        produced += len(output)
                        remaining -= len(chunk)
                    if produced != row["output_bytes"]:
                        raise FP8StreamError("Converted tensor size mismatch.")
                    per_tensor_hashes[row["name"]] = digest.hexdigest()
                out.flush()
                os.fsync(out.fileno())
            after = source.stat()
            if after.st_size != source_stat.st_size or after.st_mtime_ns != source_stat.st_mtime_ns:
                raise FP8StreamError("Source changed during streaming conversion.")
            if artifact.stat().st_size != plan["output_exact_bytes"]:
                raise FP8StreamError("Converted file size differs from exact budget.")
            # Independently validate actual output header, every name/dtype/shape
            # and all offsets. No model loading is performed.
            with artifact.open("rb") as file:
                length = struct.unpack("<Q", file.read(8))[0]
                actual = json.loads(file.read(length))
            if actual != specs:
                raise FP8StreamError("Converted header integrity check failed.")
            full_hash = sha256_file(artifact)
            manifest = {
                "schema": 1, "kind": "z218_experimental_nonloadable_bf16_conversion",
                "source": str(source.resolve()), "family": family,
                "source_size_bytes": source_stat.st_size,
                "source_mtime_ns": source_stat.st_mtime_ns,
                "output_sha256": full_hash, "output_file": filename,
                "output_bytes": plan["output_exact_bytes"],
                "tensor_sha256": per_tensor_hashes,
                "source_full_hash_verified": False,
                "ready": False, "loadable": False, "runtime_verified": False,
                "conversion_enabled": False,
            }
            with (temp / "manifest.json").open("x", encoding="utf-8") as file:
                json.dump(manifest, file, indent=2, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            if destination.exists() or destination.is_symlink():
                raise FP8StreamError("Scratch destination appeared concurrently.")
            os.rename(temp, destination)
            temp = None
    except CacheIntegrityError as exc:
        raise FP8StreamError(str(exc)) from exc
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
    return {"status": "exported_nonloadable", "output_directory": str(destination),
            "tensor_count": len(actions), "output_bytes": plan["output_exact_bytes"],
            "output_sha256": full_hash, "loadable": False,
            "runtime_verified": False, "conversion_enabled": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Morphorum Z2.18 isolated conversion (CPU only)")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--managed-root", required=True, help="Managed Z-Image-Turbo package directory")
    parser.add_argument("--family", choices=("transformer", "encoder"), required=True)
    parser.add_argument("--scratch", help="New isolated output directory on a disk with enough room")
    parser.add_argument("--export", action="store_true",
                        help="Explicitly export a NON-LOADABLE scratch checkpoint")
    args = parser.parse_args(argv)
    if args.export and not args.scratch:
        parser.error("--export requires --scratch")
    try:
        result = (export_fp8_stream(args.checkpoint, args.managed_root,
                                  family=args.family, scratch=args.scratch)
                  if args.export else plan_fp8_stream(
                      args.checkpoint, args.managed_root, family=args.family,
                      scratch=args.scratch))
    except (FP8StreamError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("planned", "exported_nonloadable") else 2


if __name__ == "__main__":
    raise SystemExit(main())

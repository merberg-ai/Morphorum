"""Z2.13 read-only bounded evidence probes. Never authorizes loading."""
from __future__ import annotations
import json
import math
import struct
from pathlib import Path
from typing import Any

MAX_HEADER = 16 * 1024 * 1024
MAX_SCALARS = 8
SUFFIX = ".scale_weight"

# Reference: Comfy-Org/ComfyUI comfy/utils.py convert_old_quants;
# Comfy-Org/comfy-kitchen comfy_kitchen/backends/eager/quantization.py.
def _decode_e4m3fn_byte(raw: int) -> float | None:
    """Decode one finite E4M3FN sample; None denotes the reserved NaN code."""
    sign = -1.0 if raw & 0x80 else 1.0
    exponent = (raw >> 3) & 0x0F
    mantissa = raw & 0x07
    if exponent == 15 and mantissa == 7:
        return None
    if exponent == 0:
        return sign * mantissa * (2.0 ** -9)
    return sign * (1.0 + mantissa / 8.0) * (2.0 ** (exponent - 7))


def _bounded_json(path: Path, limit: int = 1024 * 1024) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        size = path.stat().st_size
        if size <= 1 or size > limit:
            return None
        with path.open("rb") as stream:
            value = json.loads(stream.read(limit + 1))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None



def probe_fp8_scalars(path: str | Path) -> dict[str, Any]:
    """Read at most one marker and eight scalar scales from a valid header.

    The whole file must first pass the independent safetensors structural
    inspector. This reads no FP8 matrix data, and never infers scale direction.
    """
    from .zimage_inspect import inspect_zimage_checkpoint
    file = Path(path)
    report: dict[str, Any] = {"status": "unverified", "marker": None,
                              "sample_scales": [], "scale_direction": "unverified",
                              "loadable": False}
    info = inspect_zimage_checkpoint(file)
    if info.get("status") == "unsupported" or file.is_symlink():
        report["reason"] = "Safetensors structural inspection rejected file."
        return report
    with file.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            return report
        size = struct.unpack("<Q", prefix)[0]
        if size < 2 or size > MAX_HEADER:
            return report
        header = json.loads(stream.read(size))
        header.pop("__metadata__", None)
        base = 8 + size
        def read_scalar(name: str) -> dict[str, Any] | None:
            spec = header.get(name)
            if not isinstance(spec, dict) or spec.get("shape") not in ([], [1]):
                return None
            offsets = spec.get("data_offsets", [])
            if not isinstance(offsets, list) or len(offsets) != 2:
                return None
            dtype = spec.get("dtype")
            fmt = {"F32": "<f", "F64": "<d", "F16": "<e"}.get(dtype)
            if fmt is None or offsets[1] - offsets[0] != struct.calcsize(fmt):
                return {"tensor": name, "dtype": dtype, "value": None,
                        "reason": "Unsupported scalar dtype"}
            stream.seek(base + offsets[0])
            data = stream.read(struct.calcsize(fmt))
            if len(data) != struct.calcsize(fmt):
                return None
            value = struct.unpack(fmt, data)[0]
            return {"tensor": name, "dtype": dtype,
                    "value": value if math.isfinite(value) else None,
                    "finite": math.isfinite(value), "positive": value > 0}
        marker = header.get("scaled_fp8")
        if isinstance(marker, dict):
            report["marker"] = {"dtype": marker.get("dtype"),
                                "shape": marker.get("shape"),
                                "scalar": read_scalar("scaled_fp8")}
        if isinstance(marker, dict):
            shape = marker.get("shape")
            dtype = marker.get("dtype")
            marker_report = report["marker"]
            # ComfyUI convert_old_quants: shape [2] requests FP32 matmul;
            # empty [0] marker does not. Marker *values* are not used.
            if dtype == "F8_E4M3" and shape in ([0], [2]):
                count = shape[0]
                offsets = marker["data_offsets"]
                stream.seek(base + offsets[0])
                raw = stream.read(count)
                marker_report["raw_hex"] = raw.hex()
                marker_report["decoded_values"] = [_decode_e4m3fn_byte(b) for b in raw]
                marker_report["comfyui_full_precision_matrix_mult"] = count == 2
                marker_report["interpretation"] = "reference_shape_semantics_only"
        names = sorted(k for k in header if k.endswith(SUFFIX))
        report["sample_scales"] = [v for name in names[:MAX_SCALARS]
                                    if (v := read_scalar(name)) is not None]
        report["scale_count"] = len(names)
        samples = []
        for name in names[:4]:
            scale = read_scalar(name)
            weight_name = name[:-len(SUFFIX)] + ".weight"
            spec = header.get(weight_name)
            if (not scale or scale.get("positive") is not True
                    or not isinstance(spec, dict) or spec.get("dtype") != "F8_E4M3"):
                continue
            start, end = spec["data_offsets"]
            count = min(4, end - start)
            stream.seek(base + start)
            raw = stream.read(count)
            if len(raw) != count:
                continue
            decoded = [_decode_e4m3fn_byte(b) for b in raw]
            samples.append({
                "weight": weight_name, "scale": name, "raw_fp8_hex": raw.hex(),
                "decoded_fp8": decoded, "scale_value": scale["value"],
                "reference_dequantized": [
                    v * scale["value"] if v is not None else None for v in decoded
                ],
            })
        report["numerical_samples"] = samples
        report["scale_reference"] = {
            "rule": "fp8_float_times_scale",
            "source": "Comfy-Org/comfy-kitchen/backends/eager/quantization.py",
            "runtime_verified": False,
        }
    report["status"] = "evidence_collected"
    return report


def inspect_managed_auxiliaries(destination: str | Path) -> dict[str, Any]:
    """Inspect official Diffusers component configuration without modifying files."""
    root = Path(destination)
    result: dict[str, Any] = {"status": "unverified", "components": {},
                              "compatible": False, "loadable": False}
    expected = {
        "tokenizer": ("tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json"),
        "vae": ("vae/config.json", "vae/diffusion_pytorch_model.safetensors"),
        "scheduler": ("scheduler/scheduler_config.json",),
    }
    for key, paths in expected.items():
        checks = []
        for part in paths:
            target = root / part
            try:
                present = not target.is_symlink() and target.is_file() and target.stat().st_size > 0
            except OSError:
                present = False
            checks.append({"file": part, "present": present})
        result["components"][key] = {"files": checks, "present": all(c["present"] for c in checks)}
    # Read small, bounded JSON configs only. Do not read tokenizer vocab/weights.
    configs = {
        "pipeline": ("model_index.json", ("_class_name", "scheduler", "text_encoder",
                                         "tokenizer", "vae", "transformer")),
        "tokenizer": ("tokenizer/tokenizer_config.json",
                      ("tokenizer_class", "model_max_length", "add_bos_token",
                       "add_eos_token")),
        "vae": ("vae/config.json", ("_class_name", "scaling_factor", "shift_factor",
                                    "latent_channels")),
        "scheduler": ("scheduler/scheduler_config.json",
                       ("_class_name", "num_train_timesteps", "shift")),
        "text_encoder": ("text_encoder/config.json",
                         ("model_type", "hidden_size", "num_hidden_layers",
                          "num_attention_heads", "intermediate_size")),
    }
    result["configuration"] = {}
    for name, (relative, fields) in configs.items():
        data = _bounded_json(root / relative)
        result["configuration"][name] = {
            "readable": data is not None,
            "summary": {key: data[key] for key in fields
                        if data is not None and key in data
                        and isinstance(data[key], (str, int, float, bool, list))}
        }
    result["status"] = "configurations_inspected"
    return result

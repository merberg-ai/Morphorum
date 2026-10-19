"""Z2.17.2 bounded, read-only legacy ComfyUI FP8 activation-scale evidence.

Input scales calibrate FP8 activations; they are not model parameters and are
not applied to dequantized BF16 weights. This module NEVER removes or rewrites
any tensor in the checkpoint. No runtime FP8 execution is approved.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from .zimage_inspect import MAX_HEADER_BYTES

MAX_INPUT_SCALES = 4096
MAX_EXAMPLES = 12
_DTYPES = {"F32": (4, "<f"), "F16": (2, "<e"), "BF16": (2, None)}


class InputScaleInspectionError(ValueError):
    pass


def _parse_scalar(raw: bytes, dtype: str) -> float:
    if dtype == "BF16":
        bits = struct.unpack("<H", raw)[0]
        return struct.unpack("<f", struct.pack("<I", bits << 16))[0]
    return float(struct.unpack(_DTYPES[dtype][1], raw)[0])


def inspect_input_scale_metadata(path: str | Path) -> dict[str, Any]:
    """Inspect ALL old .scale_input tensors as bounded scalar metadata.

    Any malformed, orphan, nonfinite or nonpositive scale fails closed.
    Reports totals and bounded examples, never a full tensor payload.
    """
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise InputScaleInspectionError("Unsafe or missing input-scale source.")
    initial = source.stat()
    with source.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise InputScaleInspectionError("Truncated input-scale header.")
        length = struct.unpack("<Q", prefix)[0]
        if length < 2 or length > MAX_HEADER_BYTES or length + 8 > initial.st_size:
            raise InputScaleInspectionError("Unsafe input-scale header length.")
        content = stream.read(length)
        if len(content) != length:
            raise InputScaleInspectionError("Truncated input-scale header payload.")
        try:
            header = json.loads(content)
        except (ValueError, UnicodeError) as exc:
            raise InputScaleInspectionError("Malformed input-scale header JSON.") from exc
        if not isinstance(header, dict):
            raise InputScaleInspectionError("Input-scale header must be an object.")
        header.pop("__metadata__", None)
        names = sorted(k for k in header if k.endswith(".scale_input"))
        if len(names) > MAX_INPUT_SCALES:
            raise InputScaleInspectionError("Input-scale count exceeds safety bound.")
        counts: dict[str, int] = {}
        samples: list[dict[str, Any]] = []
        unit_count = 0
        nonunit_count = 0
        minimum: float | None = None
        maximum: float | None = None
        nonunit_min: float | None = None
        nonunit_max: float | None = None
        for name in names:
            tensor = header.get(name)
            stem = name[:-len(".scale_input")]
            weight = header.get(stem + ".weight")
            weight_scale = header.get(stem + ".scale_weight")
            if (not isinstance(weight, dict) or weight.get("dtype") != "F8_E4M3"
                    or not isinstance(weight_scale, dict)
                    or not isinstance(tensor, dict)):
                raise InputScaleInspectionError("Orphan input scale without a paired FP8 weight and weight scale.")
            dtype = tensor.get("dtype")
            shape = tensor.get("shape")
            offsets = tensor.get("data_offsets")
            if (dtype not in _DTYPES or shape not in ([], [1])
                    or not isinstance(offsets, list) or len(offsets) != 2
                    or any(type(value) is not int for value in offsets)
                    or offsets[1] - offsets[0] != _DTYPES[dtype][0]
                    or offsets[0] < 0 or offsets[1] > initial.st_size - 8 - length):
                raise InputScaleInspectionError("Unsupported or malformed FP8 input-scale scalar.")
            stream.seek(8 + length + offsets[0])
            raw = stream.read(_DTYPES[dtype][0])
            if len(raw) != _DTYPES[dtype][0]:
                raise InputScaleInspectionError("Truncated input scale.")
            value = _parse_scalar(raw, dtype)
            if not math.isfinite(value) or value <= 0:
                raise InputScaleInspectionError("Nonfinite or nonpositive FP8 input scale.")
            counts[dtype] = counts.get(dtype, 0) + 1
            minimum = value if minimum is None else min(minimum, value)
            maximum = value if maximum is None else max(maximum, value)
            if value == 1.0:
                unit_count += 1
            else:
                nonunit_count += 1
                nonunit_min = value if nonunit_min is None else min(nonunit_min, value)
                nonunit_max = value if nonunit_max is None else max(nonunit_max, value)
            if len(samples) < MAX_EXAMPLES and (value != 1.0 or not samples):
                samples.append({"tensor": name, "dtype": dtype, "value": value, "unit": value == 1.0})
    after = source.stat()
    if initial.st_size != after.st_size or initial.st_mtime_ns != after.st_mtime_ns:
        raise InputScaleInspectionError("Input-scale source changed during inspection.")
    return {
        "status": "inspected", "count": len(names), "unit_count": unit_count,
        "nonunit_count": nonunit_count, "dtypes": counts,
        "min": minimum, "max": maximum,
        "nonunit_min": nonunit_min, "nonunit_max": nonunit_max,
        "examples": samples,
        "comfyui_rule": "scale_input_to_input_scale_except_unit",
        "role": "FP8_activation_calibration_not_weight_parameter",
        "parameter_schema_exclusion_verified": True,
        "bf16_weight_conversion_requires_input_scales": False,
        "fp8_runtime_scale_binding_verified": False,
        "ready": False, "loadable": False, "conversion_enabled": False,
    }

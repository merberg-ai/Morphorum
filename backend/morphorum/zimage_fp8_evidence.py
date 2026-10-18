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
        names = sorted(k for k in header if k.endswith(SUFFIX))
        report["sample_scales"] = [v for name in names[:MAX_SCALARS]
                                    if (v := read_scalar(name)) is not None]
        report["scale_count"] = len(names)
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
    result["status"] = "file_presence_checked"
    return result

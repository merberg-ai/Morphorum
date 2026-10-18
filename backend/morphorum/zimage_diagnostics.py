"""Z2.10 bounded read-only diagnostics for indexed standalone Z-Image assets."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .zimage_inspect import inspect_zimage_checkpoint
from .zimage_standalone import inspect_encoder_bundle, resolve_standalone_dependencies

MAX_CANDIDATES = 64


def diagnose_standalone_checkpoint(checkpoint: str | Path, components: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Collect local format evidence without copying weights, hashing payloads or loading GPU models."""
    source = Path(checkpoint)
    candidate_rows = [r for r in components
                      if r.get("family") == "zimage" and r.get("kind") == "components"][:MAX_CANDIDATES]
    inspection = inspect_zimage_checkpoint(source)
    resolution = resolve_standalone_dependencies(source, candidate_rows)
    encoders: list[dict[str, Any]] = []
    for row in candidate_rows:
        path = row.get("path")
        if not isinstance(path, str):
            continue
        probe = inspect_zimage_checkpoint(path)
        if probe.get("component_type") != "text_encoder":
            continue
        encoders.append({
            "id": row.get("id"),
            "filename": Path(path).name,
            "header": {
                "status": probe.get("status"),
                "tensor_count": probe.get("tensor_count"),
                "dtypes": probe.get("dtypes"),
                "sample_keys": probe.get("sample_keys"),
            },
            "bundle": inspect_encoder_bundle(path),
        })
    return {
        "diagnostic_version": "z2.10",
        "checkpoint": {
            "filename": source.name,
            "inspection": inspection,
        },
        "auxiliary_encoders": encoders,
        "candidate_count": len(encoders),
        "candidates_truncated": len(candidate_rows) == MAX_CANDIDATES,
        "dependencies": {
            "status": resolution["status"],
            "missing_components": resolution["missing_components"],
            "conversion_strategy": resolution["conversion_strategy"],
            "reason": resolution["reason"],
        },
        "limits": [
            "Header and local adjacent configuration inspection only; no tensor payload was read.",
            "Filename patterns and neighboring files do not prove model compatibility.",
            "A detected Qwen-style encoder is not proof of Qwen3-4B or matching tokenizer.",
            "FP8 scales, tensor dimensions and actual runtime loading require further verification.",
        ],
        "ready": False, "loadable": False, "conversion_enabled": False,
    }

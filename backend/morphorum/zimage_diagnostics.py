"""Z2.10 bounded read-only diagnostics for indexed standalone Z-Image assets."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .zimage_inspect import inspect_zimage_checkpoint
from .zimage_fp8_validation import (validate_fp8_single_file, assess_managed_component_candidates,
                                    plan_managed_auxiliary_binding)
from .zimage_fp8_prototype import plan_fp8_bf16_windows
from .zimage_schema_validation import validate_complete_tensor_schema
from .zimage_fp8_evidence import probe_fp8_scalars, inspect_managed_auxiliaries
from .settings import managed_model_location
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
    managed_root = managed_model_location("zimage") / "Z-Image-Turbo"
    managed_inventory = inspect_managed_auxiliaries(managed_root)
    for row in candidate_rows:
        path = row.get("path")
        if not isinstance(path, str):
            continue
        probe = inspect_zimage_checkpoint(path)
        if probe.get("component_type") != "text_encoder":
            continue
        encoder_validation = validate_fp8_single_file(path)
        encoders.append({
            "id": row.get("id"),
            "filename": Path(path).name,
            "header": {
                "status": probe.get("status"),
                "tensor_count": probe.get("tensor_count"),
                "dtypes": probe.get("dtypes"),
                "sample_keys": probe.get("sample_keys"),
                "encoder_evidence": probe.get("encoder_evidence"),
                "fp8_scalar_probe": probe_fp8_scalars(path),
                "fp8_validation": encoder_validation,
                "schema_validation": validate_complete_tensor_schema(
                    path, managed_root, family="encoder", validation=encoder_validation
                ),
                "experimental_bf16_plan": plan_fp8_bf16_windows(path, validated=encoder_validation),
                "quantization_evidence": probe.get("quantization_evidence"),
            },
            "bundle": inspect_encoder_bundle(path),
        })
    checkpoint_validation = validate_fp8_single_file(source)
    transformer_schema = validate_complete_tensor_schema(
        source, managed_root, family="transformer", validation=checkpoint_validation
    )
    encoder_evidence = (encoders[0]["header"].get("encoder_evidence") if len(encoders) == 1 else None)
    assessment = assess_managed_component_candidates(managed_inventory, encoder_evidence)
    return {
        "diagnostic_version": "z2.17.2",
        "checkpoint": {
            "filename": source.name,
            "inspection": inspection,
            "fp8_scalar_probe": probe_fp8_scalars(source),
            "fp8_validation": checkpoint_validation,
            "schema_validation": transformer_schema,
            "experimental_bf16_plan": plan_fp8_bf16_windows(source, validated=checkpoint_validation),
        },
        "auxiliary_encoders": encoders,
        "candidate_count": len(encoders),
        "candidates_truncated": len(candidate_rows) == MAX_CANDIDATES,
        "managed_auxiliary_inventory": managed_inventory,
        "managed_reuse_assessment": assessment,
        "managed_auxiliary_binding_plan": plan_managed_auxiliary_binding(managed_inventory, assessment),
        "dependencies": {
            "status": resolution["status"],
            "missing_components": resolution["missing_components"],
            "conversion_strategy": resolution["conversion_strategy"],
            "reason": resolution["reason"],
        },
        "limits": [
            "Bounded marker, scalar scale and up to four tiny FP8 samples per file; no full weight matrices loaded.",
            "Filename patterns and neighboring files do not prove model compatibility.",
            "A detected Qwen-style encoder is not proof of Qwen3-4B or matching tokenizer.",
            "Every FP8 scale is inspected, but only bounded weight samples are compared against CPU PyTorch.",
            "Matching component configs do not approve runtime reuse or standalone generation.",
            "The Z2.16 BF16 plan samples tensor windows only; no full weights are converted or published.",
            "Z2.17.2 separates parameters from validated FP8 activation-scale metadata; non-unit input scales still require a verified FP8 runtime.",
            "Even a complete parameter schema match does not enable standalone loading or model conversion.",
        ],
        "ready": False, "loadable": False, "conversion_enabled": False,
    }

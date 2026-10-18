"""Z2 standalone Z-Image dependency resolver (read-only, fail-closed).

A resolution plan is not a load authorization. Managed Z-Image remains separate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .zimage_inspect import inspect_zimage_checkpoint

REQUIRED_COMPONENTS = ("text_encoder", "tokenizer", "vae", "scheduler")


def resolve_standalone_dependencies(
    checkpoint: str | Path, indexed_components: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Inventory possible dependencies without loading tensors or selecting by filename.

    A detected Qwen-like encoder is a *candidate*, not a compatible encoder.
    No architecture or tokenizer compatibility is implied by directory proximity.
    """
    source = Path(checkpoint)
    inspection = inspect_zimage_checkpoint(source)
    result: dict[str, Any] = {
        "source": "external",
        "loader": "zimage-single-file",
        "checkpoint": str(source),
        "inspection": inspection,
        "status": "unsupported",
        "ready": False,
        "loadable": False,
        "missing_components": list(REQUIRED_COMPONENTS),
        "encoder_candidates": [],
        "reason": "",
    }
    if inspection["status"] not in ("candidate", "needs_components"):
        result["reason"] = inspection["reason"]
        return result

    candidates = []
    for row in indexed_components:
        if row.get("family") != "zimage" or row.get("kind") != "components":
            continue
        path = row.get("path")
        if not isinstance(path, str):
            continue
        probe = inspect_zimage_checkpoint(path)
        if probe.get("component_type") != "text_encoder":
            continue
        candidates.append({
            "id": row.get("id"),
            "path": str(Path(path)),
            "status": "unverified",
            "reason": "Encoder tensor pattern detected; model architecture and tokenizer pairing still require verification.",
        })
    result["encoder_candidates"] = candidates
    result["status"] = "needs_components"
    result["reason"] = (
        "Standalone Z-Image loader is not yet verified. "
        + ("Text encoder candidate(s) detected, but compatibility is unverified. "
           if candidates else "No recognized text encoder candidates were indexed. ")
        + "A matching tokenizer, VAE, scheduler and full transformer mapping are required."
    )
    return result


def require_verified_standalone(plan: dict[str, Any]) -> None:
    """Explicit guard for future standalone runtime integration."""
    if plan.get("source") != "external" or plan.get("loader") != "zimage-single-file":
        raise ValueError("Not a standalone Z-Image resolution plan.")
    # Intentionally fail closed until runtime verification is implemented.
    raise RuntimeError("Standalone Z-Image loader is not verified or enabled.")

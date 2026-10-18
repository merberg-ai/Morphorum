"""Z2.20 read-only isolated inference resource gate. No model initialization."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from .settings import managed_model_location
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024 ** 3
DEFAULT_VRAM_RESERVE_GIB = 3.0
DEFAULT_RAM_RESERVE_GIB = 8.0
COMPONENTS = ("tokenizer", "vae", "scheduler")


def plan_experimental_inference(
    transformer: str | Path, encoder: str | Path, *,
    managed_root: str | Path,
    ram_gib: float,
    vram_gib: float,
    verify_hashes: bool = True,
) -> dict[str, Any]:
    """Validate separate immutable scratch exports and conservative capacity.

    Results NEVER grant runtime loading; capacity figures are lower-bound budgets.
    """
    report: dict[str, Any] = {
        "milestone": "z2.20", "status": "blocked",
        "mode": "read_only_resource_preflight", "loadable": False,
        "runtime_verified": False, "managed_model_modified": False,
        "inference_attempted": False, "reasons": [],
    }
    try:
        if not all(math.isfinite(x) and x > 0 for x in (ram_gib, vram_gib)):
            raise ValueError("RAM and VRAM capacities must be positive finite GiB values.")
        folders = [Path(transformer), Path(encoder)]
        managed = Path(managed_root)
        if any(not p.is_dir() or p.is_symlink() for p in [*folders, managed]):
            raise ValueError("Scratch and managed package directories must exist and not be symlinks.")
        resolved = [p.resolve(strict=True) for p in [*folders, managed]]
        if len(set(resolved)) != 3:
            raise ValueError("Transformer, encoder and managed package paths must be distinct.")
        for scratch in resolved[:2]:
            if scratch in resolved[2].parents or resolved[2] in scratch.parents:
                raise ValueError("Scratch directory overlaps the managed package.")
        names = ["diffusion_pytorch_model.safetensors", "model.safetensors"]
        sizes = []
        for folder, name, family in zip(folders, names, ("transformer", "encoder")):
            manifest_path = folder / "manifest.json"
            if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 1024 * 1024:
                raise ValueError(f"{family}: missing or unsafe manifest.")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (manifest.get("family") != family or manifest.get("output_file") != name
                    or manifest.get("ready") is not False
                    or manifest.get("loadable") is not False
                    or manifest.get("runtime_verified") is not False):
                raise ValueError(f"{family}: manifest family or authorization flags invalid.")
            artifact = folder / name
            if artifact.is_symlink() or not artifact.is_file() or artifact.stat().st_size != manifest.get("output_bytes"):
                raise ValueError(f"{family}: missing or mismatched output artifact.")
            sizes.append(artifact.stat().st_size)
            if verify_hashes:
                verified = verify_fp8_stream_artifact(folder)
                if verified.get("status") != "verified_nonloadable":
                    raise ValueError(f"{family}: integrity verification failed.")
        for component in COMPONENTS:
            directory = managed / component
            if not directory.is_dir() or directory.is_symlink():
                raise ValueError(f"Managed {component} directory missing or unsafe.")
        weights_gib = [s / GIB for s in sizes]
        total = sum(weights_gib)
        report.update({
            "transformer_weight_gib": round(weights_gib[0], 3),
            "encoder_weight_gib": round(weights_gib[1], 3),
            "combined_weight_gib": round(total, 3),
            "available_ram_gib": ram_gib,
            "available_vram_gib": vram_gib,
            "minimum_vram_reserve_gib": DEFAULT_VRAM_RESERVE_GIB,
            "minimum_ram_reserve_gib": DEFAULT_RAM_RESERVE_GIB,
            "artifact_hashes_checked": verify_hashes,
            "managed_component_presence_checked": list(COMPONENTS),
            "managed_config_compatibility_verified": False,
            "recommended_strategy": "sequential_encoder_cpu_offload_then_transformer_cpu_offload",
        })
        if vram_gib - DEFAULT_VRAM_RESERVE_GIB < weights_gib[0]:
            report["reasons"].append(
                "Transformer BF16 weights plus reserved VRAM exceed specified GPU capacity; "
                "layerwise/group offload or quantization would be needed."
            )
        if ram_gib - DEFAULT_RAM_RESERVE_GIB < total:
            report["reasons"].append(
                "Combined weights plus reserved system RAM exceed specified capacity; "
                "disk offload or lower precision may be required."
            )
        if not report["reasons"]:
            report["status"] = "capacity_candidate_unverified"
            report["reasons"].append(
                "Only basic weights and fixed safety reserves were evaluated. Peak CPU/GPU "
                "activations, CUDA kernels, model initialization, tokenizer/config matching, "
                "VAE, paging and Windows memory pressure remain unverified."
            )
        else:
            report["status"] = "capacity_warning_unverified"
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        report["reasons"].append(str(exc)[:350])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Z2.20 read-only resource preflight (NEVER inference)")
    parser.add_argument("--transformer", required=True, help="Z2.19 transformer scratch directory")
    parser.add_argument("--encoder", required=True, help="Z2.19 encoder scratch directory")
    parser.add_argument("--managed-root", help="Managed Z-Image-Turbo directory (default: settings)")
    parser.add_argument("--ram-gib", type=float, required=True, help="Installed system RAM in GiB")
    parser.add_argument("--vram-gib", type=float, required=True, help="Total GPU VRAM in GiB")
    parser.add_argument("--skip-hashes", action="store_true", help="Fast size/manifest inspection only, NOT accepted integrity")
    args = parser.parse_args(argv)
    managed = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = plan_experimental_inference(
        args.transformer, args.encoder, managed_root=managed,
        ram_gib=args.ram_gib, vram_gib=args.vram_gib,
        verify_hashes=not args.skip_hashes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

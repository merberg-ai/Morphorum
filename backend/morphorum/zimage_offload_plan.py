"""Z2.20c3b1 conservative GPU/offload preflight; never initializes CUDA."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024 ** 3


def plan_offload(transformer, encoder, managed_root, *, vram_gib=16.0, free_vram_gib=None,
                 ram_gib=64.0, verify_hashes=True):
    result = {"milestone": "z2.20c3b1", "mode": "read_only_offload_plan",
              "status": "blocked", "cuda_initialized": False, "gpu_weights_loaded": False,
              "generation_attempted": False, "loadable": False, "runtime_verified": False,
              "warnings": []}
    try:
        if not (0 < vram_gib <= 1024 and 0 < ram_gib <= 8192):
            raise ValueError("Invalid total RAM/VRAM capacities.")
        if free_vram_gib is not None and not (0 < free_vram_gib <= vram_gib):
            raise ValueError("Free GPU capacity must be positive and no greater than total VRAM.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Schema/config gate blocked: " + "; ".join(check["reasons"]))
        if verify_hashes:
            for path in (transformer, encoder):
                if verify_fp8_stream_artifact(Path(path))["status"] != "verified_nonloadable":
                    raise ValueError("Scratch hash gate failed.")
        sizes = [
            (Path(transformer) / "diffusion_pytorch_model.safetensors").stat().st_size,
            (Path(encoder) / "model.safetensors").stat().st_size,
        ]
        transformer_gib, encoder_gib = [x / GIB for x in sizes]
        budget = (free_vram_gib if free_vram_gib is not None else vram_gib) - 3.0
        result.update({
            "status": "offload_plan_unverified",
            "transformer_weight_gib": round(transformer_gib, 3),
            "encoder_weight_gib": round(encoder_gib, 3),
            "combined_weight_gib": round(transformer_gib + encoder_gib, 3),
            "vram_budget_after_3gib_reserve": round(budget, 3),
            "vram_capacity_gib": vram_gib, "vram_free_input_gib": free_vram_gib,
            "ram_capacity_gib": ram_gib,
            "strategy": "sequential_component_cpu_offload",
            "full_pipeline_cuda_resident_safe": False,
            "transformer_only_weights_fit_budget": budget >= transformer_gib,
            "encoder_only_weights_fit_budget": budget >= encoder_gib,
            "hashes_verified": verify_hashes,
        })
        if budget < transformer_gib:
            result["warnings"].append("Full BF16 transformer weights exceed VRAM after fixed reserve: use layer/group offload.")
        if budget < encoder_gib:
            result["warnings"].append("Full BF16 encoder weights exceed VRAM after fixed reserve: use CPU encoder or group offload.")
        result["warnings"].append(
            "This is static weight accounting, not a GPU memory measurement or valid runtime offload configuration; "
            "CUDA allocator, attention activations, VAE, component hooks, transfer spikes and host memory remain unverified."
        )
    except Exception as exc:
        result["warnings"].append(type(exc).__name__ + ": " + str(exc)[:400])
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Z2.20c3b1 non-executing offload budget")
    p.add_argument("--transformer", required=True)
    p.add_argument("--encoder", required=True)
    p.add_argument("--managed-root")
    p.add_argument("--vram-gib", type=float, default=16)
    p.add_argument("--free-vram-gib", type=float)
    p.add_argument("--ram-gib", type=float, default=64)
    p.add_argument("--skip-hashes", action="store_true")
    a = p.parse_args(argv)
    root = a.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = plan_offload(a.transformer, a.encoder, root, vram_gib=a.vram_gib,
                          free_vram_gib=a.free_vram_gib, ram_gib=a.ram_gib,
                          verify_hashes=not a.skip_hashes)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "offload_plan_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())

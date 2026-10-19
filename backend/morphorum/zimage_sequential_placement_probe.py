"""Z2.20c3b5: gated sequential component GPU placement, NO forward/generation.

Experimental scratch-only weights. Run in a disposable child process.
"""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024 ** 3


def probe_sequential_placement(transformer, encoder, managed_root, *, execute=False,
                               reserve_gib=3.0):
    result = {
        "milestone": "z2.20c3b5",
        "mode": "isolated_sequential_component_cuda_placement",
        "status": "blocked",
        "placement_attempted": False,
        "encoder_gpu_verified": False,
        "encoder_evicted": False,
        "transformer_gpu_verified": False,
        "forward_attempted": False,
        "generation_attempted": False,
        "loadable": False,
        "runtime_verified": False,
        "details": [],
    }
    if not execute:
        result["status"] = "needs_explicit_execute"
        return result
    try:
        if not 3.0 <= reserve_gib <= 8.0:
            raise ValueError("Reserve must be in [3,8] GiB.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Schema/config gate failed: " + "; ".join(check["reasons"]))
        for folder in (transformer, encoder):
            if verify_fp8_stream_artifact(Path(folder))["status"] != "verified_nonloadable":
                raise ValueError("Scratch integrity gate failed.")
        import psutil
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable.")
        from transformers import Qwen3Config, Qwen3Model
        from diffusers import ZImageTransformer2DModel
        from accelerate import load_checkpoint_and_dispatch

        source_e = Path(encoder) / "model.safetensors"
        source_t = Path(transformer) / "diffusion_pytorch_model.safetensors"
        free_ram = psutil.virtual_memory().available
        # Both weights + extra 16GiB avoids obvious swapping risk.
        required_ram = source_e.stat().st_size + source_t.stat().st_size + 16 * GIB
        result["available_ram_gib"] = round(free_ram / GIB, 3)
        result["required_available_ram_gib"] = round(required_ram / GIB, 3)
        if free_ram < required_ram:
            raise ValueError("Available system RAM below combined weights plus reserve.")
        free_initial, total = torch.cuda.mem_get_info(0)
        needed_e = source_e.stat().st_size + int(reserve_gib * GIB)
        needed_t = source_t.stat().st_size + int(reserve_gib * GIB)
        result["free_vram_initial_gib"] = round(free_initial / GIB, 3)
        result["required_encoder_free_gib"] = round(needed_e / GIB, 3)
        result["required_transformer_free_gib"] = round(needed_t / GIB, 3)
        if free_initial < max(needed_e, needed_t):
            raise ValueError("Insufficient free VRAM for both sequential transfer stages.")

        root = Path(managed_root)
        cfg_e = Qwen3Config.from_pretrained(str(root / "text_encoder"), local_files_only=True)
        enc = Qwen3Model.from_pretrained(str(Path(encoder)), config=cfg_e,
                                         local_files_only=True, torch_dtype=torch.bfloat16,
                                         low_cpu_mem_usage=True).eval()
        try:
            pars = list(enc.parameters())
            if len(pars) != 398 or any(p.is_meta or p.device.type != "cpu" for p in pars):
                raise RuntimeError("Incomplete CPU encoder.")
            if torch.cuda.mem_get_info(0)[0] < needed_e:
                raise ValueError("VRAM fell below encoder transfer gate.")
            result["placement_attempted"] = True
            enc.to("cuda:0")
            torch.cuda.synchronize(0)
            if any(p.is_meta or p.device.type != "cuda" for p in pars):
                raise RuntimeError("Incomplete CUDA encoder.")
            result["encoder_gpu_verified"] = True
            result["details"].append({
                "stage": "encoder_cuda",
                "allocated_gib": round(torch.cuda.memory_allocated(0) / GIB, 3),
                "free_gib": round(torch.cuda.mem_get_info(0)[0] / GIB, 3),
            })
            # Evict full encoder before allocating any transformer GPU weights.
            enc.to("cpu")
            torch.cuda.synchronize(0)
            gc.collect()
            torch.cuda.empty_cache()
            if any(p.is_meta or p.device.type != "cpu" for p in pars):
                raise RuntimeError("Encoder did not return to CPU.")
            free_evicted, _ = torch.cuda.mem_get_info(0)
            result["details"].append({
                "stage": "encoder_evicted",
                "allocated_gib": round(torch.cuda.memory_allocated(0) / GIB, 3),
                "free_gib": round(free_evicted / GIB, 3),
            })
            if free_evicted < needed_t:
                raise ValueError("Insufficient GPU memory after encoder eviction for transformer.")
            result["encoder_evicted"] = True
            cfg_t = ZImageTransformer2DModel.load_config(
                str(root / "transformer"), local_files_only=True)
            with torch.device("meta"):
                trans = ZImageTransformer2DModel.from_config(cfg_t)
            trans = load_checkpoint_and_dispatch(
                trans, checkpoint=str(source_t), device_map={"": "cpu"},
                dtype=torch.bfloat16, strict=True).eval()
            try:
                pars_t = list(trans.parameters())
                if len(pars_t) != 521 or any(p.is_meta or p.device.type != "cpu" for p in pars_t):
                    raise RuntimeError("Incomplete CPU transformer.")
                if torch.cuda.mem_get_info(0)[0] < needed_t:
                    raise ValueError("VRAM declined before transformer transfer.")
                trans.to("cuda:0")
                torch.cuda.synchronize(0)
                if any(p.is_meta or p.device.type != "cuda" for p in pars_t):
                    raise RuntimeError("Incomplete CUDA transformer.")
                result["transformer_gpu_verified"] = True
                result["details"].append({
                    "stage": "transformer_cuda",
                    "allocated_gib": round(torch.cuda.memory_allocated(0) / GIB, 3),
                    "peak_allocated_gib": round(torch.cuda.max_memory_allocated(0) / GIB, 3),
                    "free_gib": round(torch.cuda.mem_get_info(0)[0] / GIB, 3),
                    "total_vram_gib": round(total / GIB, 3),
                })
                result["status"] = "sequential_cuda_placement_verified_nonloadable"
            finally:
                del trans
        finally:
            del enc
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:750])
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Z2.20c3b5 sequential CUDA placement (no forward)")
    p.add_argument("--transformer", required=True)
    p.add_argument("--encoder", required=True)
    p.add_argument("--managed-root")
    p.add_argument("--reserve-gib", type=float, default=3.0)
    p.add_argument("--execute-sequential-placement", action="store_true")
    a = p.parse_args(argv)
    root = a.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_sequential_placement(a.transformer, a.encoder, root,
                                        execute=a.execute_sequential_placement,
                                        reserve_gib=a.reserve_gib)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("needs_explicit_execute",
                "sequential_cuda_placement_verified_nonloadable") else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Z2.20c3b3 guarded standalone Qwen3 CPU→CUDA placement; no forward."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024**3

def probe_encoder_gpu(transformer, encoder, managed_root, *, execute=False, reserve_gib=3.0):
    report = {"milestone": "z2.20c3b3", "status": "blocked",
              "mode": "isolated_encoder_cuda_placement",
              "placement_attempted": False, "forward_attempted": False,
              "generation_attempted": False, "loadable": False,
              "runtime_verified": False, "details": []}
    if not execute:
        report["status"] = "needs_explicit_execute"
        return report
    try:
        if not 2 <= reserve_gib <= 8:
            raise ValueError("Reserve must be between 2 and 8 GiB.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Schema/config preflight failed: " + "; ".join(check["reasons"]))
        if verify_fp8_stream_artifact(Path(encoder))["status"] != "verified_nonloadable":
            raise ValueError("Encoder scratch hash verification failed.")
        import torch
        import psutil
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available.")
        free, total = torch.cuda.mem_get_info(0)
        source = Path(encoder) / "model.safetensors"
        required = source.stat().st_size + int(reserve_gib * GIB)
        report["free_vram_before_gib"] = round(free / GIB, 3)
        report["required_free_vram_gib"] = round(required / GIB, 3)
        if free < required:
            raise ValueError("Insufficient measured free VRAM for encoder placement and reserve.")
        available_ram = psutil.virtual_memory().available
        if available_ram < source.stat().st_size * 2 + 12 * GIB:
            raise ValueError("Insufficient available RAM for encoder CPU loading.")
        from transformers import Qwen3Config, Qwen3Model
        root = Path(managed_root)
        config = Qwen3Config.from_pretrained(str(root / "text_encoder"), local_files_only=True)
        model = Qwen3Model.from_pretrained(
            str(Path(encoder)), config=config, local_files_only=True,
            torch_dtype=torch.bfloat16, low_cpu_mem_usage=True,
        ).eval()
        try:
            params = list(model.parameters())
            if len(params) != 398 or any(p.is_meta or p.device.type != "cpu" for p in params):
                raise RuntimeError("CPU encoder binding incomplete.")
            # Repeat live VRAM gate immediately before the real allocation.
            free_now, _ = torch.cuda.mem_get_info(0)
            if free_now < required:
                raise ValueError("Free VRAM fell below reserve before transfer.")
            torch.cuda.reset_peak_memory_stats(0)
            report["placement_attempted"] = True
            model.to(device="cuda:0")
            torch.cuda.synchronize(0)
            if any(p.is_meta or p.device.type != "cuda" for p in model.parameters()):
                raise RuntimeError("Encoder parameters not fully on CUDA.")
            report["details"].append({
                "gpu": torch.cuda.get_device_name(0),
                "parameter_tensors": len(params),
                "memory_allocated_gib": round(torch.cuda.memory_allocated(0) / GIB, 3),
                "max_memory_allocated_gib": round(torch.cuda.max_memory_allocated(0) / GIB, 3),
                "free_vram_after_gib": round(torch.cuda.mem_get_info(0)[0] / GIB, 3),
                "total_vram_gib": round(total / GIB, 3),
            })
            report["status"] = "encoder_cuda_placement_verified_nonloadable"
        finally:
            model.to("cpu")
            del model
            torch.cuda.empty_cache()
    except Exception as exc:
        report["details"].append(type(exc).__name__ + ": " + str(exc)[:700])
    return report

def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c3b3 real Qwen3 GPU placement, no forward")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    parser.add_argument("--reserve-gib", type=float, default=3.0)
    parser.add_argument("--execute-encoder-gpu-placement", action="store_true")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_encoder_gpu(args.transformer, args.encoder, root,
                               execute=args.execute_encoder_gpu_placement,
                               reserve_gib=args.reserve_gib)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("needs_explicit_execute",
                                      "encoder_cuda_placement_verified_nonloadable") else 2

if __name__ == "__main__":
    raise SystemExit(main())

"""Z2.20c3b2: strictly bounded CUDA transfer and allocator telemetry.

No model weights, no full pipeline and no generation. Explicit opt-in required.
"""
from __future__ import annotations
import argparse
import json
import os


def probe_gpu_placement(*, execute=False, max_mib=16, reserve_gib=3.0):
    result = {
        "milestone": "z2.20c3b2", "mode": "bounded_cuda_tensor_transfer",
        "status": "blocked", "cuda_initialized": False,
        "model_weights_loaded": False, "generation_attempted": False,
        "loadable": False, "runtime_verified": False, "details": [],
    }
    try:
        if not execute:
            result["status"] = "needs_explicit_execute"
            return result
        if type(max_mib) is not int or not 1 <= max_mib <= 64:
            raise ValueError("Transfer budget must be 1..64 MiB.")
        if not 1 <= reserve_gib <= 12:
            raise ValueError("Reserve must be between 1 and 12 GiB.")
        if os.environ.get("CUDA_VISIBLE_DEVICES") == "-1":
            raise ValueError("CUDA is masked in this process.")
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("No available CUDA device.")
        result["cuda_initialized"] = True
        device = torch.device("cuda:0")
        properties = torch.cuda.get_device_properties(device)
        free_before, total = torch.cuda.mem_get_info(device)
        bytes_count = max_mib * 1024 * 1024
        if free_before < reserve_gib * 1024**3 + bytes_count * 4:
            raise RuntimeError("Insufficient free VRAM after the requested reserve.")
        cpu = torch.full((bytes_count // 2,), 0.125, dtype=torch.bfloat16, device="cpu")
        baseline = torch.cuda.memory_allocated(device)
        peak_before = torch.cuda.max_memory_allocated(device)
        gpu = cpu.to(device)
        gpu = (gpu + gpu)
        torch.cuda.synchronize(device)
        if not bool(torch.isfinite(gpu).all().item()):
            raise RuntimeError("Nonfinite CUDA arithmetic.")
        peak = torch.cuda.max_memory_allocated(device)
        free_during, _ = torch.cuda.mem_get_info(device)
        result["details"] = [{
            "gpu_name": properties.name,
            "total_vram_gib": round(total / 1024**3, 3),
            "free_vram_before_gib": round(free_before / 1024**3, 3),
            "free_vram_during_gib": round(free_during / 1024**3, 3),
            "transfer_mib": max_mib,
            "dtype": "torch.bfloat16",
            "finite": True,
            "allocator_baseline_mib": round(baseline / 1048576, 2),
            "allocator_peak_mib": round(peak / 1048576, 2),
            "previous_peak_mib": round(peak_before / 1048576, 2),
        }]
        del gpu, cpu
        torch.cuda.empty_cache()
        result["status"] = "bounded_gpu_transfer_verified_nonloadable"
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:650])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c3b2 bounded CUDA placement experiment")
    parser.add_argument("--execute-gpu-probe", action="store_true")
    parser.add_argument("--max-mib", type=int, default=16)
    parser.add_argument("--reserve-gib", type=float, default=3.0)
    args = parser.parse_args(argv)
    result = probe_gpu_placement(execute=args.execute_gpu_probe, max_mib=args.max_mib,
                                 reserve_gib=args.reserve_gib)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("needs_explicit_execute",
                                      "bounded_gpu_transfer_verified_nonloadable") else 2


if __name__ == "__main__":
    raise SystemExit(main())

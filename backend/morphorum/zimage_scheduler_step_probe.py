"""Z2.20c2a: isolated finite CPU scheduler step and memory telemetry.

This is not a transformer forward pass, VAE decode, or image generation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration


def probe_scheduler_math(transformer, encoder, managed_root):
    result = {
        "milestone": "z2.20c2a", "status": "blocked",
        "mode": "isolated_cpu_scheduler_numerical_probe",
        "loadable": False, "runtime_verified": False,
        "transformer_forward_attempted": False, "inference_attempted": False,
        "cuda_used": False, "details": [],
    }
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("CUDA_VISIBLE_DEVICES must be -1 before startup.")
        base = probe_configuration(transformer, encoder, managed_root)
        if base["status"] != "config_shape_candidate_unverified":
            raise ValueError("Config preflight blocked: " + "; ".join(base["reasons"]))
        import torch
        import psutil
        from diffusers import FlowMatchEulerDiscreteScheduler
        if torch.cuda.is_available():
            raise RuntimeError("CUDA isolation failed.")
        process = psutil.Process()
        rss_before = process.memory_info().rss
        scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
            str(Path(managed_root) / "scheduler"), local_files_only=True
        )
        scheduler.set_timesteps(2, device="cpu")
        sample = torch.full((1, 16, 8, 8), 0.25, dtype=torch.float32, device="cpu")
        prediction = torch.full_like(sample, 0.125)
        with torch.inference_mode():
            for timestep in scheduler.timesteps:
                response = scheduler.step(prediction, timestep, sample)
                sample = response.prev_sample
                if sample.shape != (1, 16, 8, 8) or not bool(torch.isfinite(sample).all()):
                    raise RuntimeError("Scheduler produced invalid sample shape or values.")
        rss_after = process.memory_info().rss
        result["details"] = [{
            "scheduler": type(scheduler).__name__,
            "steps": 2, "sample_shape": list(sample.shape),
            "sample_dtype": str(sample.dtype),
            "sample_finite": True,
            "rss_before_mib": round(rss_before / 1024**2, 2),
            "rss_after_mib": round(rss_after / 1024**2, 2),
            "rss_delta_mib": round((rss_after - rss_before) / 1024**2, 2),
        }]
        result["status"] = "cpu_scheduler_steps_verified"
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:500])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c2a CPU scheduler computation (no model inference)")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_scheduler_math(args.transformer, args.encoder, root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "cpu_scheduler_steps_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())

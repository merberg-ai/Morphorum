"""Z2.20c2b: isolated, explicitly gated CPU VAE decode smoke test.

Uses immutable managed VAE, never registers/loads a standalone generation pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration

GIB = 1024 ** 3
MIN_AVAILABLE_RAM_GIB = 12


def probe_vae_forward(transformer, encoder, managed_root, *, execute=False):
    result = {
        "milestone": "z2.20c2b", "status": "blocked",
        "mode": "isolated_cpu_vae_decode", "forward_attempted": False,
        "inference_attempted": False, "cuda_used": False,
        "runtime_verified": False, "loadable": False, "details": [],
    }
    try:
        if not execute:
            result["status"] = "needs_explicit_execute"
            return result
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("CUDA_VISIBLE_DEVICES=-1 is required before process start.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Scratch/config gate blocked: " + "; ".join(check["reasons"]))
        import psutil
        available = psutil.virtual_memory().available / GIB
        result["available_ram_gib"] = round(available, 2)
        if available < MIN_AVAILABLE_RAM_GIB:
            raise ValueError("Less than 12 GiB available RAM, refusing VAE load.")
        import torch
        from diffusers import AutoencoderKL
        if torch.cuda.is_available():
            raise RuntimeError("CUDA isolation did not hold.")
        root = Path(managed_root).resolve(strict=True)
        vae_dir = root / "vae"
        if vae_dir.is_symlink() or not vae_dir.is_dir():
            raise ValueError("Missing or unsafe managed VAE directory.")
        process = psutil.Process()
        rss_before = process.memory_info().rss
        vae = AutoencoderKL.from_pretrained(
            str(vae_dir), local_files_only=True, torch_dtype=torch.float32,
        ).eval().to("cpu")
        try:
            tensors = list(vae.parameters())
            if not tensors or any(p.device.type != "cpu" or p.is_meta for p in tensors):
                raise RuntimeError("VAE has unbound or non-CPU weights.")
            latent_channels = int(vae.config.latent_channels)
            if latent_channels < 1 or latent_channels > 32:
                raise ValueError("Unexpected latent channel count.")
            latent = torch.zeros((1, latent_channels, 8, 8), dtype=torch.float32, device="cpu")
            result["forward_attempted"] = True
            with torch.inference_mode():
                decoded = vae.decode(latent, return_dict=True).sample
                if decoded.device.type != "cpu" or decoded.ndim != 4:
                    raise RuntimeError("Invalid VAE output device or rank.")
                if decoded.shape[0] != 1 or decoded.shape[1] != 3:
                    raise RuntimeError("Unexpected VAE output channels.")
                if not bool(torch.isfinite(decoded).all().item()):
                    raise RuntimeError("Nonfinite VAE decode result.")
                result["details"] = [{
                    "input_shape": list(latent.shape),
                    "output_shape": list(decoded.shape),
                    "output_dtype": str(decoded.dtype),
                    "output_min": float(decoded.min().item()),
                    "output_max": float(decoded.max().item()),
                    "rss_before_mib": round(rss_before / 1024**2, 2),
                    "rss_after_mib": round(process.memory_info().rss / 1024**2, 2),
                    "parameter_tensors_bound": len(tensors),
                    "output_finite": True,
                }]
            result["status"] = "vae_cpu_forward_verified_nonloadable"
        finally:
            del vae
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:600])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c2b CPU-only managed VAE decoder probe")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    parser.add_argument("--execute-vae-forward", action="store_true")
    args = parser.parse_args(argv)
    managed = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_vae_forward(args.transformer, args.encoder, managed, execute=args.execute_vae_forward)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("needs_explicit_execute", "vae_cpu_forward_verified_nonloadable") else 2


if __name__ == "__main__":
    raise SystemExit(main())

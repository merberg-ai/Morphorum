"""Z2.20c1 isolated managed tokenizer, scheduler and VAE constructor diagnostics.

No checkpoint weights, GPU computation, pipeline registration or image generation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration


def probe_components(transformer, encoder, managed_root):
    report = {
        "milestone": "z2.20c1", "status": "blocked",
        "mode": "isolated_auxiliary_component_probe",
        "tokenizer_verified": False, "scheduler_initialized": False,
        "vae_meta_initialized": False, "vae_weights_loaded": False,
        "cuda_used": False, "inference_attempted": False,
        "loadable": False, "runtime_verified": False, "details": [],
    }
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("Set CUDA_VISIBLE_DEVICES=-1 before starting Python.")
        previous = probe_configuration(transformer, encoder, managed_root)
        if previous["status"] != "config_shape_candidate_unverified":
            raise ValueError("Configuration gate blocked: " + "; ".join(previous["reasons"]))
        import torch
        if torch.cuda.is_available():
            raise RuntimeError("CUDA isolation failed.")
        from transformers import Qwen2Tokenizer
        from diffusers import FlowMatchEulerDiscreteScheduler, AutoencoderKL
        root = Path(managed_root)
        tokenizer = Qwen2Tokenizer.from_pretrained(
            str(root / "tokenizer"), local_files_only=True
        )
        sample = "A dark castle under the moon"
        encoded = tokenizer(sample, return_tensors="pt")
        if "input_ids" not in encoded or encoded["input_ids"].device.type != "cpu":
            raise RuntimeError("Tokenizer output missing or non-CPU.")
        ids = encoded["input_ids"]
        if ids.numel() == 0 or ids.shape[1] > 512:
            raise RuntimeError("Unexpected tokenizer length.")
        decoded = tokenizer.decode(ids[0], skip_special_tokens=True)
        if not decoded.strip():
            raise RuntimeError("Tokenizer could not decode probe text.")
        report["tokenizer_verified"] = True
        report["details"].append({
            "component": "tokenizer", "class": type(tokenizer).__name__,
            "tokens": int(ids.numel()), "decoded_nonempty": True,
        })
        scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
            str(root / "scheduler"), local_files_only=True
        )
        scheduler.set_timesteps(2, device="cpu")
        timesteps = scheduler.timesteps
        if timesteps.device.type != "cpu" or timesteps.numel() != 2 or not bool(torch.isfinite(timesteps).all()):
            raise RuntimeError("Scheduler timesteps invalid.")
        report["scheduler_initialized"] = True
        report["details"].append({
            "component": "scheduler", "class": type(scheduler).__name__,
            "timesteps": [float(x) for x in timesteps],
        })
        config = AutoencoderKL.load_config(str(root / "vae"), local_files_only=True)
        with torch.device("meta"):
            vae = AutoencoderKL.from_config(config)
        try:
            parameters = list(vae.parameters())
            buffers = list(vae.buffers())
            if not parameters or any(x.device.type != "meta" for x in (*parameters, *buffers)):
                raise RuntimeError("VAE escaped meta-device.")
            report["vae_meta_initialized"] = True
            report["details"].append({
                "component": "vae", "class": type(vae).__name__,
                "parameter_tensors": len(parameters),
                "parameter_elements": sum(p.numel() for p in parameters),
            })
        finally:
            del vae
        report["status"] = "auxiliary_components_structurally_verified"
    except Exception as exc:
        report["details"].append(type(exc).__name__ + ": " + str(exc)[:500])
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description="Z2.20c1 CPU tokenizer/scheduler and meta VAE probe")
    p.add_argument("--transformer", required=True)
    p.add_argument("--encoder", required=True)
    p.add_argument("--managed-root")
    a = p.parse_args(argv)
    root = a.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    outcome = probe_components(a.transformer, a.encoder, root)
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0 if outcome["status"] == "auxiliary_components_structurally_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())

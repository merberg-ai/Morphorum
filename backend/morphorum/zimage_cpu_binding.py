"""Z2.20b4 isolated, explicitly gated, single-family CPU weight binding.

No GPU, generation, model registration or managed-file mutation. Runs one family
per process to bound peak resident memory and catch loader/config incompatibilities.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024 ** 3
SAFETY_FREE_GIB = 12


def run_cpu_binding(transformer, encoder, managed_root, *, family, execute=False):
    result = {
        "milestone": "z2.20b4", "status": "blocked",
        "family": family, "mode": "isolated_cpu_full_weight_binding",
        "loadable": False, "runtime_verified": False,
        "inference_attempted": False, "cuda_used": False,
        "binding_attempted": False, "reasons": [],
    }
    try:
        if family not in ("transformer", "encoder"):
            raise ValueError("Specify transformer or encoder.")
        if not execute:
            result["status"] = "needs_explicit_execute"
            result["reasons"].append("No model loaded. Supply --execute-cpu-binding to authorize this RAM-intensive experiment.")
            return result
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("Run as a separate process with CUDA_VISIBLE_DEVICES=-1.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Config/schema validation failed: " + "; ".join(check["reasons"]))
        folder = Path(transformer if family == "transformer" else encoder)
        verified = verify_fp8_stream_artifact(folder)
        if verified["status"] != "verified_nonloadable":
            raise ValueError("Scratch full SHA-256 failed.")
        import psutil
        available = psutil.virtual_memory().available
        weight_bytes = (folder / ("diffusion_pytorch_model.safetensors" if family == "transformer" else "model.safetensors")).stat().st_size
        min_free = weight_bytes * 2 + SAFETY_FREE_GIB * GIB
        result["available_ram_gib"] = round(available / GIB, 2)
        result["required_available_ram_gib"] = round(min_free / GIB, 2)
        if available < min_free:
            raise ValueError("Insufficient available RAM for conservative sequential CPU experiment.")
        import torch
        if torch.cuda.is_available():
            raise ValueError("CUDA was not successfully masked; refusing weight load.")
        root = Path(managed_root)
        if family == "transformer":
            from diffusers import ZImageTransformer2DModel
            config = ZImageTransformer2DModel.load_config(root / "transformer", local_files_only=True)
            cls = ZImageTransformer2DModel
        else:
            from transformers import Qwen3Config, Qwen3Model
            config = Qwen3Config.from_pretrained(root / "text_encoder", local_files_only=True)
            cls = Qwen3Model
        result["binding_attempted"] = True
        # Explicit config and explicit scratch path: no implicit HF downloads.
        model = cls.from_pretrained(
            str(folder), config=config, local_files_only=True,
            torch_dtype=torch.bfloat16, low_cpu_mem_usage=True,
        )
        try:
            params = list(model.named_parameters())
            buffers = list(model.named_buffers())
            if not params or any(t.device.type != "cpu" or t.is_meta for _, t in (*params, *buffers)):
                raise RuntimeError("Unbound/meta/non-CPU parameters or buffers after load.")
            result["parameter_tensors_bound"] = len(params)
            result["parameter_elements_bound"] = sum(t.numel() for _, t in params)
            result["status"] = "cpu_weights_bound_unverified"
            result["reasons"].append("Single-family CPU load succeeded; no forward pass, numerical output validation or GPU inference.")
        finally:
            del model
    except Exception as exc:
        result["reasons"].append(type(exc).__name__ + ": " + str(exc)[:500])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gated Z2.20b4 single-family CPU model binding")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    parser.add_argument("--family", choices=("transformer", "encoder"), required=True)
    parser.add_argument("--execute-cpu-binding", action="store_true")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = run_cpu_binding(args.transformer, args.encoder, root,
                             family=args.family, execute=args.execute_cpu_binding)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("cpu_weights_bound_unverified", "needs_explicit_execute") else 2


if __name__ == "__main__":
    raise SystemExit(main())

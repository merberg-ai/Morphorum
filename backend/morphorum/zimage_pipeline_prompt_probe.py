"""Z2.20c3c1: real ZImagePipeline prompt formatting with scratch Qwen3 on CPU.

No transformer or VAE loaded, no diffusion steps, no generated images.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024**3
EXPECTED_STATUS = "pipeline_prompt_encoding_cpu_verified_nonloadable"


def probe_pipeline_prompt_encoding(transformer, encoder, managed_root, *, execute=False):
    result = {
        "milestone": "z2.20c3c1",
        "mode": "isolated_pipeline_native_prompt_encoding_cpu",
        "status": "blocked",
        "prompt_encoding_attempted": False,
        "transformer_forward_attempted": False,
        "generation_attempted": False,
        "cuda_used": False,
        "loadable": False,
        "runtime_verified": False,
        "details": [],
    }
    if not execute:
        result["status"] = "needs_explicit_execute"
        return result
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("Start Python with CUDA_VISIBLE_DEVICES=-1.")
        gate = probe_configuration(transformer, encoder, managed_root)
        if gate["status"] != "config_shape_candidate_unverified":
            raise ValueError("Schema gate: " + "; ".join(gate["reasons"]))
        if verify_fp8_stream_artifact(Path(encoder))["status"] != "verified_nonloadable":
            raise ValueError("Standalone encoder SHA-256 check failed.")

        import psutil
        source = Path(encoder) / "model.safetensors"
        available = psutil.virtual_memory().available
        required = 2 * source.stat().st_size + 12 * GIB
        result["available_ram_gib"] = round(available / GIB, 3)
        result["required_available_ram_gib"] = round(required / GIB, 3)
        if available < required:
            raise ValueError("Not enough free RAM for CPU encoder plus reserve.")

        import torch
        from transformers import Qwen3Config, Qwen3Model, Qwen2Tokenizer
        from diffusers import ZImagePipeline, FlowMatchEulerDiscreteScheduler
        if torch.cuda.is_available():
            raise RuntimeError("CUDA still visible in isolated process.")
        root = Path(managed_root)
        tok = Qwen2Tokenizer.from_pretrained(str(root / "tokenizer"), local_files_only=True)
        config = Qwen3Config.from_pretrained(str(root / "text_encoder"), local_files_only=True)
        enc = Qwen3Model.from_pretrained(
            str(Path(encoder)), config=config, local_files_only=True,
            torch_dtype=torch.bfloat16, low_cpu_mem_usage=True,
        ).eval()
        try:
            parameters = list(enc.parameters())
            if len(parameters) != 398 or any(p.is_meta or p.device.type != "cpu" for p in parameters):
                raise RuntimeError("External text encoder weights were not completely bound to CPU.")
            scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
                str(root / "scheduler"), local_files_only=True
            )
            # The pipeline's own prompt formatting, without loading the huge
            # transformer or VAE. Neither missing component is invoked.
            pipe = ZImagePipeline(
                tokenizer=tok, text_encoder=enc,
                transformer=None, vae=None, scheduler=scheduler,
            )
            result["prompt_encoding_attempted"] = True
            with torch.inference_mode():
                positive, negative = pipe.encode_prompt(
                    prompt=["A dark castle under the moon"],
                    device=torch.device("cpu"),
                    do_classifier_free_guidance=False,
                    max_sequence_length=32,
                )
            if not isinstance(positive, (tuple, list)) or len(positive) != 1:
                raise RuntimeError("Pipeline did not return one per-image embedding.")
            tensor = positive[0]
            if tensor.ndim != 2 or tensor.shape[-1] != 2560 or tensor.shape[0] < 1:
                raise RuntimeError("Unexpected native prompt embedding shape.")
            if tensor.shape[0] > 32 or tensor.device.type != "cpu":
                raise RuntimeError("Unexpected native prompt token count or device.")
            if not bool(torch.isfinite(tensor).all().item()):
                raise RuntimeError("Nonfinite native prompt embedding.")
            if negative:
                raise RuntimeError("Unexpected negative prompt embeddings with guidance disabled.")
            result["details"] = [{
                "prompt_embedding_shape": list(tensor.shape),
                "dtype": str(tensor.dtype),
                "finite": True,
                "parameter_tensors_bound": len(parameters),
                "negative_embeddings_count": len(negative),
                "process_rss_mib": round(psutil.Process().memory_info().rss / 1048576, 2),
            }]
            result["status"] = EXPECTED_STATUS
        finally:
            del enc
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:950])
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Z2.20c3c1 genuine pipeline prompt formatting, CPU-only")
    p.add_argument("--transformer", required=True)
    p.add_argument("--encoder", required=True)
    p.add_argument("--managed-root")
    p.add_argument("--execute-pipeline-prompt-encoding", action="store_true")
    a = p.parse_args(argv)
    root = a.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    r = probe_pipeline_prompt_encoding(
        a.transformer, a.encoder, root, execute=a.execute_pipeline_prompt_encoding
    )
    print(json.dumps(r, indent=2, sort_keys=True))
    return 0 if r["status"] in ("needs_explicit_execute", EXPECTED_STATUS) else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Z2.20c3a experimental CPU-only standalone pipeline assembly. No generation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024 ** 3
RESERVE_GIB = 18


def probe_pipeline_assembly(transformer, encoder, managed_root, *, execute=False):
    result = {
        "milestone": "z2.20c3a", "mode": "isolated_cpu_pipeline_assembly",
        "status": "blocked", "assembly_attempted": False,
        "generation_attempted": False, "cuda_used": False,
        "loadable": False, "runtime_verified": False, "details": [],
    }
    if not execute:
        result["status"] = "needs_explicit_execute"
        return result
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("Start a fresh process with CUDA_VISIBLE_DEVICES=-1.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Config/schema gate failed: " + "; ".join(check["reasons"]))
        for folder in (transformer, encoder):
            verified = verify_fp8_stream_artifact(Path(folder))
            if verified["status"] != "verified_nonloadable":
                raise ValueError("Standalone converted weight verification failed.")
        import psutil
        process = psutil.Process()
        available = psutil.virtual_memory().available
        weight_bytes = sum((Path(folder) / filename).stat().st_size for folder, filename in (
            (transformer, "diffusion_pytorch_model.safetensors"),
            (encoder, "model.safetensors"),
        ))
        required = weight_bytes + RESERVE_GIB * GIB
        result["available_ram_gib"] = round(available / GIB, 2)
        result["required_available_ram_gib"] = round(required / GIB, 2)
        if available < required:
            raise ValueError("Insufficient available RAM for combined model assembly.")
        import torch
        if torch.cuda.is_available():
            raise RuntimeError("CUDA masking failed.")
        from accelerate import load_checkpoint_and_dispatch
        from diffusers import (
            AutoencoderKL, FlowMatchEulerDiscreteScheduler,
            ZImagePipeline, ZImageTransformer2DModel,
        )
        from transformers import Qwen2Tokenizer, Qwen3Config, Qwen3Model
        root = Path(managed_root).resolve(strict=True)
        before = process.memory_info().rss
        tokenizer = Qwen2Tokenizer.from_pretrained(str(root / "tokenizer"), local_files_only=True)
        scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(str(root / "scheduler"), local_files_only=True)
        vae = AutoencoderKL.from_pretrained(str(root / "vae"), local_files_only=True,
                                            torch_dtype=torch.float32).eval().to("cpu")
        encoder_config = Qwen3Config.from_pretrained(str(root / "text_encoder"), local_files_only=True)
        text_encoder = Qwen3Model.from_pretrained(str(Path(encoder)), config=encoder_config,
                                                  local_files_only=True, torch_dtype=torch.bfloat16,
                                                  low_cpu_mem_usage=True).eval()
        transformer_config = ZImageTransformer2DModel.load_config(
            str(root / "transformer"), local_files_only=True
        )
        with torch.device("meta"):
            model = ZImageTransformer2DModel.from_config(transformer_config)
        model = load_checkpoint_and_dispatch(
            model, checkpoint=str(Path(transformer) / "diffusion_pytorch_model.safetensors"),
            device_map={"": "cpu"}, dtype=torch.bfloat16, strict=True,
        ).eval()
        for name, module, expected in (
            ("text_encoder", text_encoder, 398), ("transformer", model, 521),
            ("vae", vae, 244),
        ):
            parameters = list(module.parameters())
            if len(parameters) != expected or any(p.is_meta or p.device.type != "cpu" for p in parameters):
                raise RuntimeError(f"{name}: model weights are incomplete or not CPU-resident.")
        result["assembly_attempted"] = True
        pipeline = ZImagePipeline(
            tokenizer=tokenizer, text_encoder=text_encoder, transformer=model,
            vae=vae, scheduler=scheduler,
        )
        components = {
            "tokenizer": pipeline.tokenizer, "scheduler": pipeline.scheduler,
            "text_encoder": pipeline.text_encoder, "transformer": pipeline.transformer,
            "vae": pipeline.vae,
        }
        if any(value is None for value in components.values()):
            raise RuntimeError("Pipeline is missing components.")
        result["details"].append({
            "components": {name: type(value).__name__ for name, value in components.items()},
            "rss_before_mib": round(before / 1048576, 2),
            "rss_after_assembly_mib": round(process.memory_info().rss / 1048576, 2),
            "weight_tensors_bound": {"transformer": 521, "text_encoder": 398, "vae": 244},
        })
        result["status"] = "pipeline_assembled_nonloadable"
        del pipeline
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:750])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c3a isolated CPU pipeline assembly, no generation")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    parser.add_argument("--execute-pipeline-assembly", action="store_true")
    args = parser.parse_args(argv)
    managed = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_pipeline_assembly(args.transformer, args.encoder, managed,
                                     execute=args.execute_pipeline_assembly)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("needs_explicit_execute", "pipeline_assembled_nonloadable") else 2


if __name__ == "__main__":
    raise SystemExit(main())

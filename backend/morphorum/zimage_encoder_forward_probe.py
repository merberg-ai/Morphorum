"""Z2.20c2c: guarded standalone Qwen3 encoder CPU forward, no image pipeline."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024 ** 3


def probe_encoder_forward(transformer, encoder, managed_root, *, execute=False):
    result = {"milestone": "z2.20c2c", "status": "blocked",
              "mode": "isolated_standalone_encoder_cpu_forward",
              "forward_attempted": False, "cuda_used": False, "inference_attempted": False,
              "loadable": False, "runtime_verified": False, "details": []}
    try:
        if not execute:
            result["status"] = "needs_explicit_execute"
            return result
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("Set CUDA_VISIBLE_DEVICES=-1 before starting Python.")
        preflight = probe_configuration(transformer, encoder, managed_root)
        if preflight["status"] != "config_shape_candidate_unverified":
            raise ValueError("Config/schema preflight blocked: " + "; ".join(preflight["reasons"]))
        integrity = verify_fp8_stream_artifact(Path(encoder))
        if integrity["status"] != "verified_nonloadable":
            raise ValueError("Standalone encoder integrity check failed.")
        import psutil
        process = psutil.Process()
        available = psutil.virtual_memory().available
        file = Path(encoder) / "model.safetensors"
        required = file.stat().st_size * 2 + 12 * GIB
        result["available_ram_gib"] = round(available / GIB, 2)
        result["required_available_ram_gib"] = round(required / GIB, 2)
        if available < required:
            raise ValueError("Insufficient free RAM for encoder CPU experiment.")
        import torch
        from transformers import Qwen3Model, Qwen3Config, Qwen2Tokenizer
        if torch.cuda.is_available():
            raise RuntimeError("CUDA still visible.")
        root = Path(managed_root)
        tokenizer = Qwen2Tokenizer.from_pretrained(str(root / "tokenizer"), local_files_only=True)
        encoded = tokenizer("A dark castle under the moon", return_tensors="pt",
                            add_special_tokens=False)
        ids = encoded["input_ids"]
        if ids.shape[1] < 1 or ids.shape[1] > 16:
            raise RuntimeError("Tokenizer output outside short prompt bounds.")
        config = Qwen3Config.from_pretrained(str(root / "text_encoder"), local_files_only=True)
        rss_before = process.memory_info().rss
        model = Qwen3Model.from_pretrained(str(Path(encoder)), config=config,
                                           local_files_only=True, torch_dtype=torch.bfloat16,
                                           low_cpu_mem_usage=True).eval()
        try:
            parameters = list(model.parameters())
            if len(parameters) != 398 or any(p.is_meta or p.device.type != "cpu" for p in parameters):
                raise RuntimeError("Encoder parameter binding mismatch.")
            rss_loaded = process.memory_info().rss
            result["forward_attempted"] = True
            with torch.inference_mode():
                output = model(input_ids=ids, attention_mask=encoded.get("attention_mask"),
                               use_cache=False, return_dict=True)
                hidden = output.last_hidden_state
                if hidden.device.type != "cpu" or hidden.ndim != 3 or hidden.shape[0] != 1 or hidden.shape[1] != ids.shape[1]:
                    raise RuntimeError("Encoder produced invalid hidden-state shape/device.")
                if not bool(torch.isfinite(hidden).all().item()):
                    raise RuntimeError("Encoder output contains nonfinite values.")
                result["details"] = [{
                    "tokens": int(ids.shape[1]),
                    "hidden_shape": list(hidden.shape),
                    "output_dtype": str(hidden.dtype),
                    "finite": True,
                    "parameter_tensors_bound": len(parameters),
                    "rss_before_load_mib": round(rss_before / 1048576, 2),
                    "rss_after_load_mib": round(rss_loaded / 1048576, 2),
                    "rss_after_forward_mib": round(process.memory_info().rss / 1048576, 2),
                }]
            result["status"] = "encoder_cpu_forward_verified_nonloadable"
        finally:
            del model
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:700])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c2c standalone Qwen3 CPU forward")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    parser.add_argument("--execute-encoder-forward", action="store_true")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_encoder_forward(args.transformer, args.encoder, root,
                                   execute=args.execute_encoder_forward)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("needs_explicit_execute",
                                     "encoder_cpu_forward_verified_nonloadable") else 2


if __name__ == "__main__":
    raise SystemExit(main())

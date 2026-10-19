"""Z2.20c2d2: experimental, CPU-only, full standalone transformer forward.

Runs in a fresh process; no generated image, no production model registration.
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
MIN_RESERVE_GIB = 16


def probe_transformer_forward(transformer, encoder, managed_root, *, execute=False):
    report = {"milestone": "z2.20c2d2", "status": "blocked",
              "mode": "standalone_transformer_cpu_forward",
              "forward_attempted": False, "cuda_used": False,
              "inference_attempted": False, "loadable": False,
              "runtime_verified": False, "details": []}
    try:
        if not execute:
            report["status"] = "needs_explicit_execute"
            return report
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("CUDA_VISIBLE_DEVICES must be -1 before Python starts.")
        gate = probe_configuration(transformer, encoder, managed_root)
        if gate["status"] != "config_shape_candidate_unverified":
            raise ValueError("Schema/config preflight blocked: " + "; ".join(gate["reasons"]))
        folder = Path(transformer)
        verified = verify_fp8_stream_artifact(folder)
        if verified["status"] != "verified_nonloadable":
            raise ValueError("Transformer scratch integrity failed.")
        import psutil
        process = psutil.Process()
        available = psutil.virtual_memory().available
        size = (folder / "diffusion_pytorch_model.safetensors").stat().st_size
        required = size * 2 + MIN_RESERVE_GIB * GIB
        report["available_ram_gib"] = round(available / GIB, 2)
        report["required_available_ram_gib"] = round(required / GIB, 2)
        if available < required:
            raise ValueError("Insufficient available RAM for guarded full transformer forward.")
        import torch
        from diffusers import ZImageTransformer2DModel
        from accelerate import load_checkpoint_and_dispatch
        if torch.cuda.is_available():
            raise RuntimeError("CUDA isolation failed.")
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        root = Path(managed_root)
        config = ZImageTransformer2DModel.load_config(str(root / "transformer"), local_files_only=True)
        if int(config.get("in_channels", -1)) != 16 or int(config.get("cap_feat_dim", -1)) != 2560:
            raise ValueError("Unexpected transformer input or caption dimensions.")
        rss_before = process.memory_info().rss
        with torch.device("meta"):
            model = ZImageTransformer2DModel.from_config(config)
        model = load_checkpoint_and_dispatch(
            model, checkpoint=str(folder / "diffusion_pytorch_model.safetensors"),
            device_map={"": "cpu"}, dtype=torch.bfloat16, strict=True,
        ).eval()
        try:
            params = list(model.parameters())
            if len(params) != 521 or any(p.is_meta or p.device.type != "cpu" for p in params):
                raise RuntimeError("Transformer weights incomplete/non-CPU.")
            rss_after_load = process.memory_info().rss
            # One image, one frame, four by four pixels = four 2x2 image patches.
            # Caption padded internally by model; no text encoder loaded here.
            latents = [torch.zeros((16, 1, 4, 4), dtype=torch.bfloat16, device="cpu")]
            captions = [torch.zeros((1, 2560), dtype=torch.bfloat16, device="cpu")]
            t = torch.tensor([0.5], dtype=torch.float32, device="cpu")
            report["forward_attempted"] = True
            with torch.inference_mode():
                output = model(x=latents, t=t, cap_feats=captions, return_dict=False)
                samples = output[0]
                if not isinstance(samples, (list, tuple)) or len(samples) != 1:
                    raise RuntimeError("Unexpected model output container.")
                value = samples[0]
                if value.device.type != "cpu" or tuple(value.shape) != tuple(latents[0].shape):
                    raise RuntimeError("Unexpected output tensor shape/device.")
                if not bool(torch.isfinite(value).all().item()):
                    raise RuntimeError("Nonfinite transformer output.")
                report["details"].append({
                    "input_shape": list(latents[0].shape),
                    "caption_shape": list(captions[0].shape),
                    "timestep": float(t.item()),
                    "output_shape": list(value.shape),
                    "output_dtype": str(value.dtype),
                    "output_finite": True,
                    "parameter_tensors_bound": len(params),
                    "rss_before_load_mib": round(rss_before / 1048576, 2),
                    "rss_after_load_mib": round(rss_after_load / 1048576, 2),
                    "rss_after_forward_mib": round(process.memory_info().rss / 1048576, 2),
                })
            report["status"] = "transformer_cpu_forward_verified_nonloadable"
        finally:
            del model
    except Exception as exc:
        report["details"].append(type(exc).__name__ + ": " + str(exc)[:700])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c2d2 full standalone transformer CPU forward")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    parser.add_argument("--execute-transformer-forward", action="store_true")
    args = parser.parse_args(argv)
    managed = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_transformer_forward(args.transformer, args.encoder, managed,
                                      execute=args.execute_transformer_forward)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("needs_explicit_execute",
              "transformer_cpu_forward_verified_nonloadable") else 2


if __name__ == "__main__":
    raise SystemExit(main())

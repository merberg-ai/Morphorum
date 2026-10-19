"""Z2.20b2: explicit experimental meta-device class initialization.

Never loads checkpoint bytes or creates CUDA tensors. Independent of production loader.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration, _json


def probe_meta_initialization(transformer: str | Path, encoder: str | Path,
                              managed_root: str | Path) -> dict:
    report = {
        "milestone": "z2.20b2", "mode": "explicit_meta_device_initialization",
        "status": "blocked", "transformer_initialized": False,
        "encoder_initialized": False, "weights_loaded": False,
        "cuda_used": False, "inference_attempted": False,
        "loadable": False, "runtime_verified": False, "details": [],
    }
    base = probe_configuration(transformer, encoder, managed_root)
    if base["status"] != "config_shape_candidate_unverified":
        report["details"] = ["Z2.20b1 validation failed", *base["reasons"]]
        return report
    try:
        import torch
        from diffusers import ZImageTransformer2DModel
        from transformers import Qwen3Model, Qwen3Config
        from diffusers.configuration_utils import ConfigMixin

        root = Path(managed_root)
        configs = [
            ("transformer", ZImageTransformer2DModel, _json(root / "transformer" / "config.json")),
            ("encoder", Qwen3Model, _json(root / "text_encoder" / "config.json")),
        ]
        for family, cls, data in configs:
            if family == "transformer":
                # Use the existing Diffusers config machinery; initialize parameters on meta.
                with torch.device("meta"):
                    model = cls.from_config(data)
            else:
                config = Qwen3Config.from_dict(data)
                with torch.device("meta"):
                    model = cls(config)
            try:
                parameters = list(model.parameters())
                buffers = list(model.buffers())
                if not parameters or any(x.device.type != "meta" for x in (*parameters, *buffers)):
                    raise RuntimeError(f"{family} initialization escaped the meta device.")
                report[family + "_initialized"] = True
                report["details"].append({
                    "family": family, "parameters": len(parameters),
                    "parameter_elements": sum(p.numel() for p in parameters),
                    "all_parameters_and_buffers_meta": True,
                })
            finally:
                del model
        report["status"] = "meta_initialized_unverified"
    except Exception as exc:
        report["details"].append(type(exc).__name__ + ": " + str(exc)[:350])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20b2 isolated meta initialization, no weights/GPU")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_meta_initialization(args.transformer, args.encoder, root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "meta_initialized_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())

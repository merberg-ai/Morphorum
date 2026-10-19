"""Z2.20c2d1: isolated transformer-forward contract inventory, no weights/forward."""
from __future__ import annotations
import argparse
import inspect
import json
import os
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration, _json


def probe_transformer_contract(transformer, encoder, managed_root):
    result = {"milestone": "z2.20c2d1", "status": "blocked",
              "mode": "transformer_forward_contract_inventory",
              "forward_attempted": False, "weights_loaded": False, "cuda_used": False,
              "loadable": False, "runtime_verified": False, "details": []}
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("CUDA_VISIBLE_DEVICES=-1 required.")
        gate = probe_configuration(transformer, encoder, managed_root)
        if gate["status"] != "config_shape_candidate_unverified":
            raise ValueError("Configuration gate blocked: " + "; ".join(gate["reasons"]))
        import torch
        from diffusers import ZImageTransformer2DModel
        if torch.cuda.is_available():
            raise RuntimeError("CUDA isolation failed.")
        config = _json(Path(managed_root) / "transformer" / "config.json")
        with torch.device("meta"):
            model = ZImageTransformer2DModel.from_config(config)
        try:
            sig = inspect.signature(model.forward)
            args = []
            for name, param in sig.parameters.items():
                if name == "self":
                    continue
                args.append({
                    "name": name,
                    "kind": str(param.kind),
                    "required": param.default is inspect.Parameter.empty,
                    "default_repr": None if param.default is inspect.Parameter.empty else repr(param.default)[:100],
                })
            if not all(p.device.type == "meta" for p in model.parameters()):
                raise RuntimeError("Model did not remain on meta device.")
            result["details"] = [{
                "forward_parameters": args,
                "config_fields": {
                    k: config.get(k) for k in (
                        "in_channels", "out_channels", "patch_size", "num_layers",
                        "num_attention_heads", "attention_head_dim", "axes_dims_rope",
                        "all_patch_size", "caption_channels", "hidden_size"
                    ) if k in config
                },
                "parameter_count": sum(p.numel() for p in model.parameters()),
                "parameter_tensors": sum(1 for _ in model.parameters()),
            }]
            result["status"] = "transformer_forward_contract_inspected"
        finally:
            del model
    except Exception as exc:
        result["details"].append(type(exc).__name__ + ": " + str(exc)[:600])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c2d1 no-weight forward API inspection")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    output = probe_transformer_contract(args.transformer, args.encoder, root)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "transformer_forward_contract_inspected" else 2


if __name__ == "__main__":
    raise SystemExit(main())

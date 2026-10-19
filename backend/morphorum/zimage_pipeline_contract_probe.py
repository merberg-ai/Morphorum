"""Z2.20c3c0: inspect installed managed pipeline contracts, no weights loaded."""
from __future__ import annotations
import argparse
import inspect
import json
import os
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration

TARGET_METHODS = (
    "encode_prompt", "prepare_latents", "__call__",
    "get_timesteps", "_get_t5_prompt_embeds", "_get_qwen3_prompt_embeds",
)
SEARCH_TERMS = (
    "apply_chat_template", "encode_prompt(", "set_timesteps(",
    "scheduler.step(", "prepare_latents(", "latents =", "cap_feats",
    "prompt_embeds", "negative_prompt", "guidance_scale",
    "scheduler.sigmas", "scheduler.timesteps", "vae.decode(",
)

def inspect_pipeline_contract(transformer, encoder, managed_root):
    result = {"milestone": "z2.20c3c0", "mode": "read_only_pipeline_source_contract",
              "status": "blocked", "cuda_initialized": False,
              "model_weights_loaded": False, "forward_attempted": False,
              "generation_attempted": False, "loadable": False,
              "runtime_verified": False, "methods": {}, "notes": []}
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("CUDA_VISIBLE_DEVICES=-1 required for diagnostic process.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Config/schema gate failed: " + "; ".join(check["reasons"]))
        from diffusers import ZImagePipeline
        result["pipeline_class"] = ZImagePipeline.__name__
        result["pipeline_module"] = ZImagePipeline.__module__
        import diffusers
        result["diffusers_version"] = diffusers.__version__
        for name in TARGET_METHODS:
            method = getattr(ZImagePipeline, name, None)
            if method is None:
                continue
            record = {"signature": str(inspect.signature(method))[:2400]}
            try:
                lines, start = inspect.getsourcelines(method)
                matches = [
                    {"line": start + index, "code": line.strip()[:260]}
                    for index, line in enumerate(lines)
                    if any(term in line for term in SEARCH_TERMS)
                ][:55]
                record["relevant_source_lines"] = matches
            except (OSError, TypeError):
                record["source_available"] = False
            result["methods"][name] = record
        if "__call__" not in result["methods"]:
            raise ValueError("Installed pipeline has no discoverable call interface.")
        result["notes"] = [
            "Source inspection alone does not verify actual prompt semantics or full pipeline execution.",
            "No model files loaded, CUDA initialized, or image generated."
        ]
        result["status"] = "pipeline_source_contract_inspected_nonloadable"
    except Exception as exc:
        result["notes"].append(type(exc).__name__ + ": " + str(exc)[:700])
    return result

def main(argv=None):
    parser = argparse.ArgumentParser(description="Z2.20c3c0 inspect managed pipeline source contracts")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    output = inspect_pipeline_contract(args.transformer, args.encoder, root)
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0 if output["status"] == "pipeline_source_contract_inspected_nonloadable" else 2

if __name__ == "__main__":
    raise SystemExit(main())

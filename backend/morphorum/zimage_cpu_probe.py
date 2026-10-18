"""Z2.20b3: bounded CPU-only sample materialization from verified BF16 scratch.

Explicit CLI only. Never constructs a production pipeline or enables external models.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact, _load_header

MAX_SAMPLE_BYTES = 64 * 1024 * 1024
FAMILIES = (("transformer", "diffusion_pytorch_model.safetensors"),
            ("encoder", "model.safetensors"))


def probe_cpu_samples(transformer: str | Path, encoder: str | Path,
                      managed_root: str | Path, *, sample_mib: int = 16,
                      verify_hashes: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {
        "milestone": "z2.20b3", "mode": "bounded_cpu_tensor_materialization",
        "status": "blocked", "weights_fully_loaded": False, "gpu_used": False,
        "inference_attempted": False, "runtime_verified": False,
        "loadable": False, "sample_results": [], "reasons": [],
    }
    try:
        if type(sample_mib) is not int or not 1 <= sample_mib <= 64:
            raise ValueError("Sample budget must be an integer from 1 to 64 MiB.")
        check = probe_configuration(transformer, encoder, managed_root)
        if check["status"] != "config_shape_candidate_unverified":
            raise ValueError("Configuration probe blocked: " + "; ".join(check["reasons"]))
        # Full artifact verification is the default; no accepted materialization without it.
        if verify_hashes:
            for folder in (transformer, encoder):
                verified = verify_fp8_stream_artifact(folder)
                if verified.get("status") != "verified_nonloadable":
                    raise ValueError("Scratch integrity check did not pass.")
        import torch
        from safetensors import safe_open
        budget = sample_mib * 1024 * 1024
        for (family, filename), folder in zip(FAMILIES, (transformer, encoder)):
            path = Path(folder) / filename
            header, _ = _load_header(path)
            selected = sorted(
                ((name, obj) for name, obj in header.items()
                 if obj.get("dtype") in ("BF16", "F16", "F32")
                 and math.prod(obj.get("shape", [])) *
                    {"BF16": 2, "F16": 2, "F32": 4}[obj["dtype"]] <= budget),
                key=lambda item: (-math.prod(item[1]["shape"]), item[0]),
            )
            if not selected:
                raise ValueError(f"{family}: no suitable tensors within sample budget.")
            # Reopen independently and materialize only one tensor at a time.
            name, spec = selected[0]
            with safe_open(str(path), framework="pt", device="cpu") as handle:
                tensor = handle.get_tensor(name)
                try:
                    if tensor.device.type != "cpu" or tuple(tensor.shape) != tuple(spec["shape"]):
                        raise ValueError(f"{family}: CPU tensor materialization mismatch.")
                    if not bool(torch.isfinite(tensor).all().item()):
                        raise ValueError(f"{family}: nonfinite sample tensor.")
                    report["sample_results"].append({
                        "family": family, "tensor": name, "dtype": str(tensor.dtype),
                        "shape": list(tensor.shape), "materialized_bytes": tensor.numel() * tensor.element_size(),
                        "finite": True,
                    })
                finally:
                    del tensor
        report["status"] = "cpu_samples_verified_nonloadable"
        report["reasons"].append(
            "Only one bounded tensor per family was loaded on CPU; this is not full-model "
            "weight binding, numerical parity proof, or inference compatibility."
        )
    except Exception as exc:
        report["reasons"].append(type(exc).__name__ + ": " + str(exc)[:350])
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Z2.20b3 isolated CPU tensor sample probe")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    parser.add_argument("--sample-mib", type=int, default=16)
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_cpu_samples(args.transformer, args.encoder, root, sample_mib=args.sample_mib)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "cpu_samples_verified_nonloadable" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Z2.20b isolated, read-only config and schema compatibility probe.

No torch, Diffusers model initialization, or weights are imported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .settings import managed_model_location
from .zimage_fp8_stream import _load_header
from .zimage_schema_validation import read_managed_component_schema

MAX_JSON = 1024 * 1024
COMPONENTS = ("transformer", "text_encoder", "tokenizer", "vae", "scheduler")


def _json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_JSON:
        raise ValueError("Missing or unsafe configuration: " + str(path))
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Configuration must be a JSON object: " + str(path))
    return obj


def probe_configuration(
    transformer: str | Path, encoder: str | Path, managed_root: str | Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "milestone": "z2.20b", "mode": "read_only_configuration_probe",
        "status": "blocked", "config_compatible_candidate": False,
        "model_initialized": False, "inference_attempted": False,
        "runtime_verified": False, "loadable": False, "reasons": [],
    }
    try:
        root = Path(managed_root)
        scratch = [Path(transformer), Path(encoder)]
        if any(p.is_symlink() or not p.is_dir() for p in (root, *scratch)):
            raise ValueError("Missing or unsafe managed/scratch directory.")
        paths = [p.resolve(strict=True) for p in (root, *scratch)]
        if len(set(paths)) != 3:
            raise ValueError("Managed and scratch paths must be distinct.")
        for path in paths[1:]:
            if path in paths[0].parents or paths[0] in path.parents:
                raise ValueError("Scratch overlaps managed installation.")
        model_index = _json(root / "model_index.json")
        configurations = {}
        for name in COMPONENTS:
            directory = root / name
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Missing managed component: " + name)
            configurations[name] = _json(directory / ("tokenizer_config.json" if name == "tokenizer" else "config.json"))
        for family, scratch_dir, filename in zip(
            ("transformer", "encoder"), scratch,
            ("diffusion_pytorch_model.safetensors", "model.safetensors"),
        ):
            manifest = _json(scratch_dir / "manifest.json")
            if (manifest.get("family") != family or manifest.get("output_file") != filename
                    or any(manifest.get(flag) is not False
                           for flag in ("loadable", "runtime_verified", "ready", "conversion_enabled"))):
                raise ValueError(f"{family} scratch manifest does not meet isolation contract.")
            output = scratch_dir / filename
            if output.is_symlink() or not output.is_file() or output.stat().st_size != manifest.get("output_bytes"):
                raise ValueError(f"{family} scratch file missing or size mismatched.")
            observed, _ = _load_header(output)
            expected = read_managed_component_schema(root, family)
            if set(observed) != set(expected):
                raise ValueError(f"{family} scratch tensor names do not match managed schema.")
            for key, shape in expected.items():
                if tuple(observed[key]["shape"]) != shape or observed[key]["dtype"] not in ("F16", "BF16", "F32"):
                    raise ValueError(f"{family} scratch tensor shape/dtype mismatch: {key[:100]}")
            result[family + "_tensor_count"] = len(expected)
        index_components = {}
        for name in COMPONENTS:
            item = model_index.get(name)
            if not isinstance(item, list) or len(item) != 2 or not all(isinstance(x, str) for x in item):
                raise ValueError("Managed model_index.json lacks component binding: " + name)
            index_components[name] = item
        result["managed_pipeline_class"] = model_index.get("_class_name")
        result["component_classes"] = index_components
        result["config_classes"] = {
            name: config.get("_class_name", config.get("model_type", config.get("tokenizer_class")))
            for name, config in configurations.items()
        }
        result["status"] = "config_shape_candidate_unverified"
        result["config_compatible_candidate"] = True
        result["reasons"].append(
            "Managed config files and converted tensor names/shapes are structurally present. "
            "No runtime initialization, class import, tokenizer semantics, CPU load, "
            "activation memory, numerical forward pass, or full export SHA-256 check occurred."
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["reasons"].append(str(exc)[:350])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Z2.20b strictly read-only config/schema probe")
    parser.add_argument("--transformer", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--managed-root")
    args = parser.parse_args(argv)
    root = args.managed_root or managed_model_location("zimage") / "Z-Image-Turbo"
    result = probe_configuration(args.transformer, args.encoder, root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

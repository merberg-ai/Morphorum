"""Z2.15 isolated, read-only FP8 validation against CPU PyTorch.

No conversion files, GPU loading, model activation or managed-package mutations.
The checker intentionally supports only the observed ComfyUI scaled E4M3 layout.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from .zimage_fp8_evidence import _decode_e4m3fn_byte
from .zimage_inspect import MAX_HEADER_BYTES, inspect_zimage_checkpoint

MAX_SCALE_PAIRS = 4096
MAX_SAMPLE_PAIRS = 8
MAX_VALUES_PER_PAIR = 16


def _result(status: str, reason: str) -> dict[str, Any]:
    return {
        "status": status, "reason": reason,
        "format": "comfyui_scaled_fp8_e4m3_probe",
        "ready": False, "loadable": False, "conversion_enabled": False,
    }


def validate_fp8_single_file(path: str | Path) -> dict[str, Any]:
    """Examine every scalar scale and bounded weight samples; fail closed.

    The safetensors inspector first verifies all offsets and payload coverage.
    Reference comparisons use CPU PyTorch float8_e4m3fn, not a model loader.
    """
    file = Path(path)
    info = inspect_zimage_checkpoint(file)
    if info.get("status") not in {"needs_components", "auxiliary"}:
        return _result("rejected", "Structural inspector did not recognize the checkpoint.")
    if file.is_symlink() or not file.is_file():
        return _result("rejected", "Source file is missing or a symlink.")
    stat_before = file.stat()
    with file.open("rb") as stream:
        raw_header_len = stream.read(8)
        if len(raw_header_len) != 8:
            return _result("rejected", "Truncated header prefix.")
        header_size = struct.unpack("<Q", raw_header_len)[0]
        if header_size < 2 or header_size > MAX_HEADER_BYTES:
            return _result("rejected", "Invalid header size.")
        header = json.loads(stream.read(header_size))
        header.pop("__metadata__", None)
        payload_start = 8 + header_size
        fp8 = {k: v for k, v in header.items() if v["dtype"].startswith("F8_")}
        weights = {k: v for k, v in fp8.items() if k.endswith(".weight")}
        unexpected_fp8 = sorted(set(fp8) - set(weights) - {"scaled_fp8"})
        marker = fp8.get("scaled_fp8")
        if unexpected_fp8 or marker is None:
            return _result("rejected", "Unrecognized FP8 tensors or missing scaled_fp8 marker.")
        if marker["dtype"] != "F8_E4M3" or marker["shape"] not in ([0], [2]):
            return _result("rejected", "Unsupported FP8 marker dtype or shape.")
        if not weights or len(weights) > MAX_SCALE_PAIRS:
            return _result("rejected", "Missing or excessive FP8 weight count.")
        if any(spec["dtype"] != "F8_E4M3" for spec in weights.values()):
            return _result("rejected", "Only F8_E4M3 weights are supported by this validator.")
        names = sorted(k for k in header if k.endswith(".scale_weight"))
        expected_scales = {k[:-len(".weight")] + ".scale_weight" for k in weights}
        if len(names) != len(weights) or set(names) != expected_scales:
            return _result("rejected", "Incomplete or extra FP8 weight/scale pairs.")
        scales = {}
        for key in names:
            spec = header[key]
            offsets = spec["data_offsets"]
            if (spec["dtype"] != "F32" or spec["shape"] not in ([], [1])
                    or offsets[1] - offsets[0] != 4):
                return _result("rejected", "Scale tensor must be an FP32 scalar.")
            stream.seek(payload_start + offsets[0])
            buf = stream.read(4)
            if len(buf) != 4:
                return _result("rejected", "Truncated scale tensor.")
            scalar = struct.unpack("<f", buf)[0]
            if not math.isfinite(scalar) or scalar <= 0:
                return _result("rejected", "Invalid nonfinite or nonpositive FP8 scale.")
            scales[key] = scalar
        # Actual marker contents are not interpreted by the ComfyUI reference;
        # its element count is the pertinent flag.
        marker_count = marker["shape"][0]
        indices = sorted({i * (len(names) - 1) // max(1, min(MAX_SAMPLE_PAIRS, len(names)) - 1)
                          for i in range(min(MAX_SAMPLE_PAIRS, len(names)))})
        samples = []
        for index in indices:
            scale_key = names[index]
            weight_key = scale_key[:-len(".scale_weight")] + ".weight"
            start, end = weights[weight_key]["data_offsets"]
            count = min(MAX_VALUES_PER_PAIR, end - start)
            stream.seek(payload_start + start)
            raw = stream.read(count)
            if len(raw) != count:
                return _result("rejected", "Truncated FP8 sample.")
            decoded = [_decode_e4m3fn_byte(b) for b in raw]
            samples.append({"tensor": weight_key, "scale": scales[scale_key],
                            "raw_fp8_hex": raw.hex(), "decoded_fp8": decoded,
                            "dequantized": [v * scales[scale_key] if v is not None else None
                                            for v in decoded]})
    if (file.stat().st_size != stat_before.st_size or
            file.stat().st_mtime_ns != stat_before.st_mtime_ns):
        return _result("rejected", "Source checkpoint changed during validation.")

    comparison = {"engine": "torch_cpu_float8_e4m3fn", "available": False,
                  "values_compared": 0, "mismatches": 0}
    try:
        import torch
        comparison["available"] = True
        for sample in samples:
            raw = bytes.fromhex(sample["raw_fp8_hex"])
            # bytearray avoids PyTorch's non-writable buffer warning.
            fp8_torch = torch.frombuffer(bytearray(raw), dtype=torch.uint8).view(
                torch.float8_e4m3fn
            ).to(dtype=torch.float32)
            dequant = fp8_torch * torch.tensor(sample["scale"], dtype=torch.float32)
            for actual, expected in zip(dequant.tolist(), sample["dequantized"]):
                comparison["values_compared"] += 1
                if expected is None:
                    equal = math.isnan(actual)
                else:
                    equal = math.isfinite(actual) and math.isclose(
                        actual, expected, rel_tol=2e-6, abs_tol=1e-7
                    )
                if not equal:
                    comparison["mismatches"] += 1
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError) as exc:
        comparison["available"] = False
        comparison["error"] = type(exc).__name__
    status = ("reference_matched" if comparison["available"] and
              comparison["mismatches"] == 0 else
              "reference_mismatch" if comparison["available"] else "reference_unavailable")
    return {
        **_result(status, "Full FP8 pairing and scalar checks completed; runtime is not verified."),
        "fp8_weight_count": len(weights),
        "fp8_scale_count": len(scales),
        "scale_values_checked": len(scales),
        "marker_shape": marker["shape"],
        "comfyui_full_precision_matrix_mult": marker_count == 2,
        "reference": comparison,
        "samples": samples,
    }


def assess_managed_component_candidates(inventory: dict[str, Any],
                                        encoder: dict[str, Any] | None) -> dict[str, Any]:
    """Compare only read-only configurations and encoder structure, not live objects."""
    components = inventory.get("components", {})
    role_evidence = inventory.get("reference_role_evidence", {})
    conf = inventory.get("configuration", {})
    encoder = encoder or {}
    text_config = conf.get("text_encoder", {}).get("summary", {})
    layer_count = encoder.get("layer_count")
    dims = encoder.get("tensor_dimensions") or {}
    hidden = text_config.get("hidden_size")
    intermediate = text_config.get("intermediate_size")
    vocab = text_config.get("vocab_size")
    embedding = dims.get("model.embed_tokens.weight")
    up = dims.get("model.layers.0.mlp.up_proj.weight")
    down = dims.get("model.layers.0.mlp.down_proj.weight")
    qkv = [dims.get("model.layers.0.self_attn." + suffix + ".weight")
           for suffix in ("q_proj", "k_proj", "v_proj")]
    observations = {
        "tokenizer": bool(components.get("tokenizer", {}).get("present")) and
                     role_evidence.get("tokenizer", {}).get("matches") is True,
        "vae": bool(components.get("vae", {}).get("present")) and
               role_evidence.get("vae", {}).get("matches") is True,
        "scheduler": bool(components.get("scheduler", {}).get("present")) and
                     role_evidence.get("scheduler", {}).get("matches") is True,
        "encoder_layers": type(layer_count) is int and
                          layer_count == text_config.get("num_hidden_layers"),
        "encoder_model_type": text_config.get("model_type") == "qwen3",
        "encoder_embedding_hidden": type(hidden) is int and hidden > 0 and
                                    isinstance(embedding, list) and len(embedding) == 2 and
                                    embedding[1] == hidden,
        "encoder_vocab": type(vocab) is int and vocab > 0 and
                         isinstance(embedding, list) and len(embedding) == 2 and
                         embedding[0] == vocab,
        "encoder_feedforward": type(hidden) is int and type(intermediate) is int and
                               up == [intermediate, hidden] and
                               down == [hidden, intermediate],
        "encoder_attention_input": type(hidden) is int and
                                   all(isinstance(shape, list) and len(shape) == 2
                                       and shape[1] == hidden and shape[0] > 0
                                       for shape in qkv),
    }
    return {
        "status": "config_evidence_matches" if all(observations.values()) else
                  "incomplete_or_mismatched",
        "checks": observations,
        "compatible": False, "reuse_enabled": False, "loadable": False,
        "reason": "Config and layer matching alone do not establish runtime compatibility.",
    }


def plan_managed_auxiliary_binding(inventory: dict[str, Any],
                                   assessment: dict[str, Any]) -> dict[str, Any]:
    """Read-only source-role proposal; never binds or imports runtime objects."""
    checks = assessment.get("checks", {})
    roles = ("tokenizer", "vae", "scheduler")
    planned: dict[str, dict[str, Any]] = {}
    for role in roles:
        approved_evidence = (inventory.get("components", {}).get(role, {})
                             .get("present") is True and checks.get(role) is True)
        planned[role] = {
            "source": "managed:zimage-turbo",
            "relative_directory": role,
            "status": "candidate_only" if approved_evidence else "unverified",
            "binding_enabled": False,
        }
    planned["text_encoder"] = {
        "source": "external_fp8_candidate",
        "status": "mapping_and_runtime_unverified",
        "binding_enabled": False,
    }
    planned["transformer"] = {
        "source": "external_fp8_checkpoint",
        "status": "mapping_and_runtime_unverified",
        "binding_enabled": False,
    }
    return {
        "status": "candidates_identified" if all(
            planned[r]["status"] == "candidate_only" for r in roles
        ) else "requires_more_evidence",
        "components": planned, "runtime_binding_enabled": False,
        "loadable": False, "ready": False,
        "reason": "Path and configuration evidence cannot establish inference compatibility.",
    }

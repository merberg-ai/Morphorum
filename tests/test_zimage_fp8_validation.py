"""Z2.15 isolated FP8 validation regression tests."""
import json
import math
import struct

import pytest

from morphorum.zimage_fp8_validation import (
    assess_managed_component_candidates, validate_fp8_single_file,
)


def write_fp8(tmp_path, *, scale_overrides=None, missing_scale=None,
              extra_scale=False, marker_shape=(2,), weight_dtype="F8_E4M3"):
    path = tmp_path / "sample.safetensors"
    weights = [
        "x_embedder.weight", "final_layer.weight", "cap_embedder.0.weight",
        "noise_refiner.0.weight", "context_refiner.0.weight",
        "layers.0.attention.qkv.weight",
    ]
    header = {}
    payload = bytearray()

    def append(name, dtype, shape, data):
        start = len(payload)
        payload.extend(data)
        header[name] = {"dtype": dtype, "shape": list(shape),
                        "data_offsets": [start, len(payload)]}

    for name in weights:
        append(name, weight_dtype, (4,), bytes([0x38, 0x40, 0xB8, 0x00]))
        scale_key = name[:-len(".weight")] + ".scale_weight"
        if scale_key != missing_scale:
            value = (scale_overrides or {}).get(scale_key, 2.0)
            append(scale_key, "F32", (1,), struct.pack("<f", value))
    if extra_scale:
        append("unexpected.scale_weight", "F32", (1,), struct.pack("<f", 1.0))
    append("scaled_fp8", "F8_E4M3", marker_shape, bytes([0] * marker_shape[0]))
    encoded = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + payload)
    return path


def test_z215_complete_fp8_pairs_match_torch_cpu_reference(tmp_path):
    pytest.importorskip("torch")
    path = write_fp8(tmp_path)
    original = path.read_bytes()
    result = validate_fp8_single_file(path)
    assert result["status"] == "reference_matched"
    assert result["fp8_weight_count"] == 6
    assert result["fp8_scale_count"] == 6
    assert result["scale_values_checked"] == 6
    assert result["reference"]["available"] is True
    assert result["reference"]["mismatches"] == 0
    assert result["reference"]["values_compared"] == 24
    assert result["samples"][0]["dequantized"] == [2.0, 4.0, -2.0, 0.0]
    assert result["comfyui_full_precision_matrix_mult"] is True
    assert result["ready"] is False and result["loadable"] is False
    assert result["conversion_enabled"] is False
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sample.safetensors"]


def test_z215_missing_and_unpaired_scales_rejected(tmp_path):
    missing = write_fp8(tmp_path, missing_scale="layers.0.attention.qkv.scale_weight")
    assert validate_fp8_single_file(missing)["status"] == "rejected"
    extra = write_fp8(tmp_path, extra_scale=True)
    assert validate_fp8_single_file(extra)["status"] == "rejected"


@pytest.mark.parametrize("bad_scale", [0.0, -1.0, float("nan"), float("inf")])
def test_z215_rejects_invalid_scale_values(tmp_path, bad_scale):
    file = write_fp8(tmp_path, scale_overrides={"x_embedder.scale_weight": bad_scale})
    result = validate_fp8_single_file(file)
    assert result["status"] == "rejected"
    assert "nonfinite or nonpositive" in result["reason"]


def test_z215_rejects_unverified_fp8_dtype(tmp_path):
    file = write_fp8(tmp_path, weight_dtype="F8_E5M2")
    assert validate_fp8_single_file(file)["status"] == "rejected"


def test_z215_empty_comfy_marker_is_explicitly_not_full_precision(tmp_path):
    pytest.importorskip("torch")
    file = write_fp8(tmp_path, marker_shape=(0,))
    result = validate_fp8_single_file(file)
    assert result["status"] == "reference_matched"
    assert result["comfyui_full_precision_matrix_mult"] is False


def test_z215_managed_component_candidate_is_not_loader_approval():
    inventory = {
        "components": {k: {"present": True} for k in ("tokenizer", "vae", "scheduler")},
        "reference_role_evidence": {k: {"matches": True}
                                     for k in ("tokenizer", "vae", "scheduler")},
        "configuration": {"text_encoder": {
            "summary": {"model_type": "qwen3", "num_hidden_layers": 36, "hidden_size": 2560, "intermediate_size": 9728, "vocab_size": 151936}
        }},
    }
    evidence = {"layer_count": 36, "tensor_dimensions": {"model.embed_tokens.weight": [151936, 2560], "model.layers.0.mlp.up_proj.weight": [9728, 2560], "model.layers.0.mlp.down_proj.weight": [2560, 9728], "model.layers.0.self_attn.q_proj.weight": [4096, 2560], "model.layers.0.self_attn.k_proj.weight": [1024, 2560], "model.layers.0.self_attn.v_proj.weight": [1024, 2560]}}
    result = assess_managed_component_candidates(inventory, evidence)
    assert result["status"] == "config_evidence_matches"
    assert all(result["checks"].values())
    assert result["compatible"] is False and result["reuse_enabled"] is False
    mismatched = assess_managed_component_candidates(inventory, {**evidence, "layer_count": 35})
    assert mismatched["status"] == "incomplete_or_mismatched"
    assert not mismatched["checks"]["encoder_layers"]

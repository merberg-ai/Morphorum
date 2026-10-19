from __future__ import annotations

import json
import struct

from morphorum.zimage_inspect import inspect_zimage_checkpoint


def _write(path, tensors, payload=b""):
    header = json.dumps(tensors).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)


def test_transformer_only_needs_components(tmp_path):
    file = tmp_path / "anything.safetensors"
    _write(file, {"transformer.layers.0.weight": {
        "dtype": "F8_E4M3FN", "shape": [2],
        "data_offsets": [0, 2]}}, b"ab")
    result = inspect_zimage_checkpoint(file)
    assert result["status"] == "needs_components"
    assert result["ready"] is False
    assert result["loadable"] is False
    assert "F8_E4M3FN" in result["dtypes"]


def test_multicomponent_candidate_is_not_loadable(tmp_path):
    file = tmp_path / "checkpoint.safetensors"
    _write(file, {
        "transformer.weight": {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]},
        "vae.weight": {"dtype": "F16", "shape": [1], "data_offsets": [2, 4]},
    }, b"abcd")
    result = inspect_zimage_checkpoint(file)
    assert result["status"] == "candidate"
    assert not result["loadable"]


def test_invalid_offsets_and_malformed_header(tmp_path):
    file = tmp_path / "bad.safetensors"
    _write(file, {"transformer.weight": {
        "dtype": "F32", "shape": [2], "data_offsets": [0, 4]}}, b"abcd")
    assert inspect_zimage_checkpoint(file)["status"] == "unsupported"
    file.write_bytes(struct.pack("<Q", 999_999_999))
    assert inspect_zimage_checkpoint(file)["status"] == "unsupported"


def test_pickle_files_never_inspected(tmp_path):
    file = tmp_path / "model.ckpt"
    file.write_bytes(b"pickle contents")
    result = inspect_zimage_checkpoint(file)
    assert result["status"] == "unsupported"
    assert not result["loadable"]


def test_symlink_rejected(tmp_path):
    target = tmp_path / "target.safetensors"
    _write(target, {"tensor": {
        "dtype": "F16", "shape": [1], "data_offsets": [0, 2]}}, b"ab")
    link = tmp_path / "link.safetensors"
    link.symlink_to(target)
    assert inspect_zimage_checkpoint(link)["status"] == "unsupported"


def test_zimage_original_transformer_signature_is_not_load_authorization(tmp_path):
    path = tmp_path / "unrelated_filename.safetensors"
    names = [
        "model.diffusion_model.x_embedder.weight",
        "model.diffusion_model.final_layer.weight",
        "model.diffusion_model.cap_embedder.1.weight",
        "model.diffusion_model.noise_refiner.0.attention.qkv.weight",
        "model.diffusion_model.context_refiner.0.attention.qkv.weight",
        "model.diffusion_model.layers.0.attention.qkv.weight",
    ]
    header = {}
    for index, name in enumerate(names):
        header[name] = {"dtype": "F16", "shape": [1], "data_offsets": [2*index, 2*index+2]}
    _write(path, header, b"ab"*len(names))
    result = inspect_zimage_checkpoint(path)
    assert result["architecture"] == "zimage_original_transformer"
    assert result["status"] == "needs_components"
    assert result["loadable"] is False
    assert result["ready"] is False


def test_partial_zimage_signature_not_verified(tmp_path):
    path = tmp_path / "looks_like_zimage.safetensors"
    _write(path, {"model.diffusion_model.x_embedder.weight":
                  {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]}}, b"ab")
    result = inspect_zimage_checkpoint(path)
    assert result["architecture"] == "unverified"
    assert result["loadable"] is False


def test_z23_fp8_structural_diagnostics_are_not_load_authorization(tmp_path):
    path = tmp_path / "quantized.safetensors"
    names = [
        "model.diffusion_model.x_embedder.weight",
        "model.diffusion_model.final_layer.weight",
        "model.diffusion_model.cap_embedder.weight",
        "model.diffusion_model.noise_refiner.0.weight",
        "model.diffusion_model.context_refiner.0.weight",
        "model.diffusion_model.layers.0.weight",
        "model.diffusion_model.layers.1.weight",
        "model.diffusion_model.layers.0.weight_scale_inv",
    ]
    header = {name: {"dtype": "F8_E4M3FN", "shape": [1], "data_offsets": [i, i+1]}
              for i, name in enumerate(names)}
    _write(path, header, b"a" * len(names))
    result = inspect_zimage_checkpoint(path)
    assert result["architecture"] == "zimage_original_transformer"
    assert result["tensor_validation"]["blocks"]["layers"]["count"] == 2
    assert result["tensor_validation"]["blocks"]["layers"]["contiguous"]
    assert result["tensor_validation"]["quantization_convention"] == "unverified"
    assert result["tensor_validation"]["scale_tensor_count"] == 1
    assert result["ready"] is False and result["loadable"] is False


def test_z23_rejects_noncontiguous_transformer_layer_numbers(tmp_path):
    path = tmp_path / "incomplete.safetensors"
    names = [
        "transformer.x_embedder.weight", "transformer.final_layer.weight",
        "transformer.cap_embedder.weight", "transformer.noise_refiner.0.weight",
        "transformer.context_refiner.0.weight", "transformer.layers.0.weight",
        "transformer.layers.2.weight",
    ]
    header = {name: {"dtype": "F16", "shape": [1], "data_offsets": [2*i, 2*i+2]}
              for i, name in enumerate(names)}
    _write(path, header, b"ab" * len(names))
    result = inspect_zimage_checkpoint(path)
    assert result["architecture"] == "zimage_original_transformer"
    assert result["status"] == "unsupported"
    assert "layers" in result["reason"]


def test_z211_real_world_scale_weight_pairing(tmp_path):
    file = tmp_path / "actual_style.safetensors"
    names = ["x_embedder.weight", "final_layer.weight", "cap_embedder.weight",
             "noise_refiner.0.weight", "context_refiner.0.weight",
             "layers.0.attention.qkv.weight", "layers.0.attention.qkv.scale_weight"]
    header = {}
    offset = 0
    for name in names:
        dtype = "F32" if name.endswith(".scale_weight") else "F8_E4M3"
        width = 4 if dtype == "F32" else 1
        header[name] = {"dtype": dtype, "shape": [1],
                        "data_offsets": [offset, offset + width]}
        offset += width
    _write(file, header, b"x" * offset)
    result = inspect_zimage_checkpoint(file)
    assert result["quantization_evidence"]["scale_tensor_count"] == 1
    assert result["quantization_evidence"]["paired_fp8_scale_count"] == 1
    assert result["tensor_validation"]["scale_tensor_count"] == 1
    assert result["quantization_evidence"]["convention"] == "unverified"
    assert not result["loadable"]


def test_z211_qwen_like_encoder_evidence_without_config(tmp_path):
    file = tmp_path / "encoder.safetensors"
    names = ["model.embed_tokens.weight", "model.layers.0.self_attn.q_proj.weight",
             "model.layers.0.mlp.gate_proj.weight"]
    _write(file, {key: {"dtype": "BF16", "shape": [1],
                       "data_offsets": [2*i, 2*i+2]}
                  for i, key in enumerate(names)}, b"ab"*len(names))
    result = inspect_zimage_checkpoint(file)
    assert result["status"] == "auxiliary"
    assert result["encoder_evidence"]["layer_count"] == 1
    assert result["encoder_evidence"]["architecture"] == "qwen_like_unverified"


def test_z212_identifies_fp8_non_weight_tensor(tmp_path):
    path = tmp_path / "fp8.safetensors"
    names = ["x_embedder.weight", "final_layer.weight", "cap_embedder.weight",
             "noise_refiner.0.weight", "context_refiner.0.weight",
             "layers.0.weight", "cap_pad_token"]
    header = {name: {"dtype": "F8_E4M3", "shape": [1],
                     "data_offsets": [i, i + 1]} for i, name in enumerate(names)}
    _write(path, header, b"a" * len(names))
    result = inspect_zimage_checkpoint(path)
    evidence = result["quantization_evidence"]
    assert evidence["unclassified_fp8_tensor_count"] == 1
    assert evidence["unclassified_fp8_tensor_keys"] == ["cap_pad_token"]
    assert not result["loadable"]

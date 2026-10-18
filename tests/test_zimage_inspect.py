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

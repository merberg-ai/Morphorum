from __future__ import annotations

import json
import struct

from morphorum.zimage_diagnostics import diagnose_standalone_checkpoint


def _write(path, names):
    tensors = {}
    data = bytearray()
    for name in names:
        start = len(data)
        data.extend(b"ab")
        tensors[name] = {"dtype": "F16", "shape": [1], "data_offsets": [start, len(data)]}
    header = json.dumps(tensors).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header + data)


def test_z210_report_is_read_only_and_remains_unloadable(tmp_path):
    checkpoint = tmp_path / "z_image.safetensors"
    encoder = tmp_path / "encoder.safetensors"
    _write(checkpoint, ["model.diffusion_model.x_embedder.weight",
        "model.diffusion_model.final_layer.weight", "model.diffusion_model.cap_embedder.weight",
        "model.diffusion_model.noise_refiner.0.weight",
        "model.diffusion_model.context_refiner.0.weight",
        "model.diffusion_model.layers.0.weight"])
    _write(encoder, ["model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.0.mlp.gate_proj.weight"])
    original = checkpoint.read_bytes()
    result = diagnose_standalone_checkpoint(checkpoint, [
        {"family": "zimage", "kind": "components", "path": str(encoder), "id": "aux-1"},
        {"family": "sdxl", "kind": "components", "path": str(encoder), "id": "wrong-family"},
    ])
    assert result["checkpoint"]["inspection"]["architecture"] == "zimage_original_transformer"
    assert result["candidate_count"] == 1
    assert result["auxiliary_encoders"][0]["bundle"]["loadable"] is False
    assert result["ready"] is False and result["conversion_enabled"] is False
    assert checkpoint.read_bytes() == original
    assert not (tmp_path / "cache").exists()


def test_z210_bad_checkpoint_cannot_become_ready(tmp_path):
    checkpoint = tmp_path / "invalid.ckpt"
    checkpoint.write_bytes(b"invalid")
    result = diagnose_standalone_checkpoint(checkpoint, [])
    assert result["checkpoint"]["inspection"]["status"] == "unsupported"
    assert result["dependencies"]["status"] == "unsupported"
    assert result["loadable"] is False

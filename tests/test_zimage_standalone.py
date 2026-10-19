from __future__ import annotations

import json
import struct

import pytest

from morphorum.zimage_standalone import (
    require_verified_standalone,
    inspect_encoder_bundle,
    resolve_standalone_dependencies,
)


def write_file(path, names):
    contents = {}
    payload = bytearray()
    for name in names:
        start = len(payload)
        payload.extend(b"ab")
        contents[name] = {"dtype": "F16", "shape": [1], "data_offsets": [start, start + 2]}
    header = json.dumps(contents).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)


def test_resolver_discovers_auxiliary_encoder_without_claiming_ready(tmp_path):
    checkpoint = tmp_path / "checkpoint.safetensors"
    encoder = tmp_path / "text_encoder.safetensors"
    write_file(checkpoint, ["transformer.layers.0.weight"])
    write_file(encoder, [
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.0.mlp.gate_proj.weight",
    ])
    plan = resolve_standalone_dependencies(checkpoint, [
        {"id": "encoder-id", "family": "zimage", "kind": "components", "path": str(encoder)},
        {"id": "unrelated", "family": "sdxl", "kind": "components", "path": str(encoder)},
    ])
    assert plan["status"] == "needs_components"
    assert plan["ready"] is False
    assert plan["loadable"] is False
    assert len(plan["encoder_candidates"]) == 1
    assert plan["encoder_candidates"][0]["status"] == "unverified"
    assert "tokenizer" in plan["missing_components"]
    with pytest.raises(RuntimeError, match="not verified"):
        require_verified_standalone(plan)


def test_resolver_rejects_invalid_checkpoint_and_unrecognized_encoder(tmp_path):
    checkpoint = tmp_path / "bad.ckpt"
    checkpoint.write_bytes(b"pickle")
    plan = resolve_standalone_dependencies(checkpoint, [])
    assert plan["status"] == "unsupported"
    assert not plan["loadable"]
    with pytest.raises(ValueError, match="Not a standalone"):
        require_verified_standalone({"source": "managed", "loader": "zimage-single-file"})


def test_z24_encoder_bundle_requires_qwen3_config_and_tokenizer(tmp_path):
    encoder = tmp_path / "encoder.safetensors"
    write_file(encoder, [
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.0.mlp.gate_proj.weight",
    ])
    assert inspect_encoder_bundle(encoder)["status"] == "unverified"
    config = {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"],
              "hidden_size": 2560, "num_hidden_layers": 36,
              "num_attention_heads": 32, "vocab_size": 151936}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    result = inspect_encoder_bundle(encoder)
    assert result["encoder_family"] == "qwen3"
    assert result["status"] == "component_evidence_present"
    assert result["loadable"] is False


def test_z24_rejects_other_encoder_architecture(tmp_path):
    encoder = tmp_path / "encoder.safetensors"
    write_file(encoder, [
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.0.mlp.gate_proj.weight",
    ])
    (tmp_path / "config.json").write_text(json.dumps({
        "model_type": "llama", "architectures": ["LlamaForCausalLM"],
        "hidden_size": 2560, "num_hidden_layers": 36,
        "num_attention_heads": 32, "vocab_size": 128000}), encoding="utf-8")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    result = inspect_encoder_bundle(encoder)
    assert result["encoder_family"] == "unknown"
    assert result["status"] == "unverified"

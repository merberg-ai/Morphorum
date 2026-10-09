from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
from safetensors.torch import save_file

import morphorum.lora_inspector as inspector


def fake_record(path: Path) -> dict:
    return {
        "id": "inspector-id", "name": path.stem, "filename": path.name,
        "path": str(path), "kind": "loras", "family": "sdxl",
    }


def test_inspector_reads_kohya_headers_and_sidecar_without_loading_tensors(
    tmp_path: Path, monkeypatch
) -> None:
    file = tmp_path / "chalk.safetensors"
    prefix = "lora_unet_input_blocks_7_1_transformer_blocks_3_attn1_to_q"
    save_file(
        {
            prefix + ".lora_down.weight": torch.ones(8, 10),
            prefix + ".lora_up.weight": torch.ones(10, 8),
            "lora_te1_text_model_encoder_layers_0_self_attn_q_proj.lora_down.weight": torch.ones(8, 8),
        }, str(file),
        metadata={
            "ss_base_model_version": "sdxl_base_v1-0",
            "ss_network_dim": "8",
            "ss_tag_frequency": json.dumps({"folder": {"chalk sketch": 30, "blue background": 6}}),
        },
    )
    file.with_suffix(".civitai.info").write_text(json.dumps({
        "trainedWords": ["chalkdust", "chalk pastel"],
        "baseModel": "SDXL 1.0",
        "modelVersionId": 1212,
    }), encoding="utf-8")
    file.with_suffix(".html").write_text(
        '<html><body><script>bad script</script><h1>Chalk Dust Style</h1>'
        '<a href="https://civitai.com/models/1234?modelVersionId=1212">model</a></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(inspector, "get_model", lambda _model_id: fake_record(file))
    result = inspector.inspect_lora("inspector-id")
    assert result["adapter_format"] == "kohya/sgm"
    assert result["trigger_words"] == ["chalkdust", "chalk pastel"]
    assert result["trigger_source"].startswith("sidecar")
    assert result["metadata_base_model"] == "sdxl_base_v1-0"
    assert result["components"]["unet"] == 2
    assert result["components"]["text_encoder"] == 1
    assert result["ranks"] == [{"rank": 8, "modules": 2}]
    assert result["top_training_tags"][0]["tag"] == "chalk sketch"
    assert result["html_sidecar"]["civitai_model_id"] == 1234
    assert "bad script" not in result["html_sidecar"]["text_excerpt"]
    assert result["inspection"].startswith("static header")
    assert any("text-encoder" in warning for warning in result["warnings"])


def test_inspector_nested_civitai_sidecar_and_no_metadata(tmp_path, monkeypatch):
    file = tmp_path / "other.safetensors"
    save_file({"transformer.block.lora_A.weight": torch.ones(2, 4)}, str(file))
    file.with_suffix(".json").write_text(
        json.dumps({"modelVersion": {"trainedWords": ["sunshine"], "baseModel": "FLUX.1 D"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(inspector, "get_model", lambda _: fake_record(file))
    result = inspector.inspect_lora("inspector-id")
    assert result["trigger_words"] == ["sunshine"]
    assert result["base_model_hint_family"] == "flux"
    assert any("indexed under sdxl" in warning for warning in result["warnings"])


def test_inspector_rejects_unindexed_and_never_unpickles(tmp_path, monkeypatch):
    file = tmp_path / "legacy.ckpt"
    file.write_bytes(b"pickle is dangerous")
    monkeypatch.setattr(inspector, "get_model", lambda _: fake_record(file))
    result = inspector.inspect_lora("inspector-id")
    assert result["tensor_count"] == 0
    assert result["adapter_format"] == "not-inspected"
    assert any("pickle execution is disabled" in error for error in result["errors"])
    monkeypatch.setattr(inspector, "get_model", lambda _: {"kind": "checkpoints"})
    with pytest.raises(inspector.LoRAInspectionError):
        inspector.inspect_lora("inspector-id")

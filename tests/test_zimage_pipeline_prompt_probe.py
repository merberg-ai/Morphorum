from unittest.mock import patch

from morphorum.zimage_pipeline_prompt_probe import probe_pipeline_prompt_encoding


def test_disabled_by_default(tmp_path):
    result = probe_pipeline_prompt_encoding(tmp_path, tmp_path, tmp_path)
    assert result["status"] == "needs_explicit_execute"
    assert not result["prompt_encoding_attempted"]
    assert not result["generation_attempted"]


def test_rejects_unmasked_cuda(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    result = probe_pipeline_prompt_encoding(tmp_path, tmp_path, tmp_path, execute=True)
    assert result["status"] == "blocked"
    assert not result["prompt_encoding_attempted"]


def test_bad_schema_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_pipeline_prompt_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["bad"]}):
        result = probe_pipeline_prompt_encoding(tmp_path, tmp_path, tmp_path, execute=True)
    assert result["status"] == "blocked"
    assert not result["transformer_forward_attempted"]
    assert result["loadable"] is False

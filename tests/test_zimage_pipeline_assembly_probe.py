from unittest.mock import patch
from morphorum.zimage_pipeline_assembly_probe import probe_pipeline_assembly


def test_requires_opt_in(tmp_path):
    result = probe_pipeline_assembly(tmp_path, tmp_path, tmp_path)
    assert result["status"] == "needs_explicit_execute"
    assert result["assembly_attempted"] is False
    assert result["generation_attempted"] is False


def test_cuda_mask_required(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    result = probe_pipeline_assembly(tmp_path, tmp_path, tmp_path, execute=True)
    assert result["status"] == "blocked"
    assert result["assembly_attempted"] is False


def test_failed_schema_blocks(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_pipeline_assembly_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["invalid schema"]}):
        result = probe_pipeline_assembly(tmp_path, tmp_path, tmp_path, execute=True)
    assert result["status"] == "blocked"
    assert result["generation_attempted"] is False
    assert result["loadable"] is False

from unittest.mock import patch
from morphorum.zimage_pipeline_contract_probe import inspect_pipeline_contract

def test_cuda_mask_required(tmp_path,monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES",raising=False)
    r=inspect_pipeline_contract(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="blocked"
    assert not r["generation_attempted"]

def test_schema_failure_blocks_before_pipeline_import(tmp_path,monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES","-1")
    with patch("morphorum.zimage_pipeline_contract_probe.probe_configuration",
               return_value={"status":"blocked","reasons":["invalid"]}):
        r=inspect_pipeline_contract(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="blocked"
    assert not r["model_weights_loaded"]

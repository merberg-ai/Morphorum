from unittest.mock import patch
from morphorum.zimage_transformer_contract_probe import probe_transformer_contract

def test_refuses_unmasked_cuda(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    result = probe_transformer_contract(tmp_path, tmp_path, tmp_path)
    assert result["status"] == "blocked"
    assert not result["weights_loaded"]
    assert not result["forward_attempted"]

def test_refuses_bad_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_transformer_contract_probe.probe_configuration",
               return_value={"status":"blocked","reasons":["bad schema"]}):
        result = probe_transformer_contract(tmp_path, tmp_path, tmp_path)
    assert result["status"] == "blocked"
    assert result["loadable"] is False

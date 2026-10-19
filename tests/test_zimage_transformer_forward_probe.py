from unittest.mock import patch
from morphorum.zimage_transformer_forward_probe import probe_transformer_forward

def test_explicit_flag_required(tmp_path):
    r = probe_transformer_forward(tmp_path, tmp_path, tmp_path)
    assert r["status"] == "needs_explicit_execute"
    assert r["forward_attempted"] is False
    assert r["loadable"] is False

def test_cuda_mask_required(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    r = probe_transformer_forward(tmp_path, tmp_path, tmp_path, execute=True)
    assert r["status"] == "blocked"
    assert r["forward_attempted"] is False

def test_config_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_transformer_forward_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["bad schema"]}):
        r = probe_transformer_forward(tmp_path, tmp_path, tmp_path, execute=True)
    assert r["status"] == "blocked"
    assert not r["inference_attempted"]

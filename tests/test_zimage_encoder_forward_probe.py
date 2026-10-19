from unittest.mock import patch
from morphorum.zimage_encoder_forward_probe import probe_encoder_forward

def test_not_enabled_without_explicit_flag(tmp_path):
    r = probe_encoder_forward(tmp_path, tmp_path, tmp_path)
    assert r["status"] == "needs_explicit_execute"
    assert not r["forward_attempted"]
    assert not r["loadable"]

def test_requires_cpu_mask(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    r = probe_encoder_forward(tmp_path, tmp_path, tmp_path, execute=True)
    assert r["status"] == "blocked"
    assert not r["forward_attempted"]

def test_rejects_bad_preflight(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_encoder_forward_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["invalid"]}):
        r = probe_encoder_forward(tmp_path, tmp_path, tmp_path, execute=True)
    assert r["status"] == "blocked"
    assert not r["forward_attempted"]

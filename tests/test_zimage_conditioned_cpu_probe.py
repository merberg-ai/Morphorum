from unittest.mock import patch
from morphorum.zimage_conditioned_cpu_probe import probe_conditioned_cpu

def test_default_inert(tmp_path):
    r=probe_conditioned_cpu(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert not r["encoder_forward_attempted"]
    assert not r["generation_attempted"]

def test_cuda_isolation_required(tmp_path,monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES",raising=False)
    r=probe_conditioned_cpu(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert not r["transformer_forward_attempted"]

def test_schema_guard(tmp_path,monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES","-1")
    with patch("morphorum.zimage_conditioned_cpu_probe.probe_configuration",return_value={"status":"blocked","reasons":["invalid"]}):
        r=probe_conditioned_cpu(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert not r["encoder_forward_attempted"]

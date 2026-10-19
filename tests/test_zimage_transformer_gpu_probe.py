from unittest.mock import patch
from morphorum.zimage_transformer_gpu_probe import probe_transformer_gpu

def test_opt_in(tmp_path):
    r=probe_transformer_gpu(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert not r["placement_attempted"]

def test_reserve_validation(tmp_path):
    r=probe_transformer_gpu(tmp_path,tmp_path,tmp_path,execute=True,reserve_gib=1)
    assert r["status"]=="blocked"

def test_config_gate(tmp_path):
    with patch("morphorum.zimage_transformer_gpu_probe.probe_configuration",return_value={"status":"blocked","reasons":["bad"]}):
        r=probe_transformer_gpu(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert r["generation_attempted"] is False

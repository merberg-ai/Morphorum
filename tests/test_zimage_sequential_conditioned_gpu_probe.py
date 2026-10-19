from unittest.mock import patch
from morphorum.zimage_sequential_conditioned_gpu_probe import probe_sequential_conditioned_gpu

def test_default_inert(tmp_path):
    r=probe_sequential_conditioned_gpu(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert not r["encoder_forward_attempted"]
    assert not r["generation_attempted"]

def test_minimum_reserve_enforced(tmp_path):
    r=probe_sequential_conditioned_gpu(tmp_path,tmp_path,tmp_path,execute=True,reserve_gib=1)
    assert r["status"]=="blocked"
    assert not r["transformer_forward_attempted"]

def test_schema_rejected_before_cuda(tmp_path):
    with patch("morphorum.zimage_sequential_conditioned_gpu_probe.probe_configuration",return_value={"status":"blocked","reasons":["bad"]}):
        r=probe_sequential_conditioned_gpu(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert not r["encoder_forward_attempted"]

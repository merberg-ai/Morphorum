from unittest.mock import patch
from morphorum.zimage_transformer_cuda_forward_probe import probe_transformer_cuda_forward

def test_inert_by_default(tmp_path):
    r=probe_transformer_cuda_forward(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert not r["forward_attempted"]

def test_minimum_headroom_cannot_be_reduced(tmp_path):
    r=probe_transformer_cuda_forward(tmp_path,tmp_path,tmp_path,execute=True,forward_headroom_gib=0.25)
    assert r["status"]=="blocked"
    assert not r["generation_attempted"]

def test_schema_failure_blocks(tmp_path):
    with patch("morphorum.zimage_transformer_cuda_forward_probe.probe_configuration",
               return_value={"status":"blocked","reasons":["bad"]}):
        r=probe_transformer_cuda_forward(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert not r["forward_attempted"]

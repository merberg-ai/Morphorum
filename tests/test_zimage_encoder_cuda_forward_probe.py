from unittest.mock import patch
from morphorum.zimage_encoder_cuda_forward_probe import probe_encoder_cuda_forward

def test_default_inert(tmp_path):
    r=probe_encoder_cuda_forward(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert not r["forward_attempted"]

def test_invalid_reserve(tmp_path):
    r=probe_encoder_cuda_forward(tmp_path,tmp_path,tmp_path,execute=True,reserve_gib=1)
    assert r["status"]=="blocked"
    assert not r["generation_attempted"]

def test_schema_block(tmp_path):
    with patch("morphorum.zimage_encoder_cuda_forward_probe.probe_configuration",
               return_value={"status":"blocked","reasons":["bad"]}):
        r=probe_encoder_cuda_forward(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert not r["forward_attempted"]

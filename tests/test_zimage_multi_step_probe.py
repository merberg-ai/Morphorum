from unittest.mock import patch
from morphorum.zimage_multi_step_probe import probe_multi_step

def test_opt_in_required(tmp_path):
    r=probe_multi_step(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert not r["generation_attempted"]

def test_step_count_bounded(tmp_path):
    for n in (0,1,4,100):
        r=probe_multi_step(tmp_path,tmp_path,tmp_path,execute=True,steps=n)
        assert r["status"]=="blocked"
        assert not r["transformer_forward_attempted"]

def test_failed_schema_prevents_execution(tmp_path):
    with patch("morphorum.zimage_multi_step_probe.probe_configuration",
               return_value={"status":"blocked","reasons":["bad"]}):
        r=probe_multi_step(tmp_path,tmp_path,tmp_path,execute=True,steps=2)
    assert r["status"]=="blocked"
    assert not r["scheduler_step_attempted"]

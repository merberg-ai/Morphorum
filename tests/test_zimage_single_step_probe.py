from unittest.mock import patch
from morphorum.zimage_single_step_probe import probe_one_step

def test_opt_in_required(tmp_path):
    r=probe_one_step(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert not r["scheduler_step_attempted"]
    assert not r["generation_attempted"]

def test_reserve_not_lowerable(tmp_path):
    r=probe_one_step(tmp_path,tmp_path,tmp_path,execute=True,reserve_gib=1)
    assert r["status"]=="blocked"
    assert not r["transformer_forward_attempted"]

def test_invalid_schema_blocks(tmp_path):
    with patch("morphorum.zimage_single_step_probe.probe_configuration",
               return_value={"status":"blocked","reasons":["invalid"]}):
        r=probe_one_step(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert not r["prompt_encoding_attempted"]

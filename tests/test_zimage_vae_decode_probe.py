from unittest.mock import patch
from morphorum.zimage_vae_decode_probe import probe_vae_decode

def test_opt_in_required(tmp_path):
    r=probe_vae_decode(tmp_path,tmp_path,tmp_path)
    assert r["status"]=="needs_explicit_execute"
    assert r["vae_decode_attempted"] is False
    assert r["image_file_saved"] is False

def test_steps_are_bounded(tmp_path):
    for steps in (1,4):
        r=probe_vae_decode(tmp_path,tmp_path,tmp_path,execute=True,steps=steps)
        assert r["status"]=="blocked"
        assert not r["vae_decode_attempted"]

def test_schema_blocks_before_loading(tmp_path):
    with patch("morphorum.zimage_vae_decode_probe.probe_configuration",
               return_value={"status":"blocked","reasons":["invalid"]}):
        r=probe_vae_decode(tmp_path,tmp_path,tmp_path,execute=True)
    assert r["status"]=="blocked"
    assert not r["transformer_forward_attempted"]
    assert not r["image_file_saved"]

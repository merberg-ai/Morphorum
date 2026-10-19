from unittest.mock import patch
from morphorum.zimage_encoder_gpu_probe import probe_encoder_gpu

def test_default_requires_explicit_opt_in(tmp_path):
    r = probe_encoder_gpu(tmp_path, tmp_path, tmp_path)
    assert r["status"] == "needs_explicit_execute"
    assert not r["placement_attempted"]

def test_invalid_reserve_blocks_early(tmp_path):
    r = probe_encoder_gpu(tmp_path, tmp_path, tmp_path, execute=True, reserve_gib=0)
    assert r["status"] == "blocked"
    assert not r["placement_attempted"]

def test_schema_failure_blocks_gpu(monkeypatch, tmp_path):
    with patch("morphorum.zimage_encoder_gpu_probe.probe_configuration", return_value={"status":"blocked", "reasons":["bad schema"]}):
        r = probe_encoder_gpu(tmp_path, tmp_path, tmp_path, execute=True)
    assert r["status"] == "blocked"
    assert not r["generation_attempted"]

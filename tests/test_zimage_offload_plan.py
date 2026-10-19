from unittest.mock import patch
from morphorum.zimage_offload_plan import plan_offload

def test_invalid_budget_blocks_before_disk(tmp_path):
    r = plan_offload(tmp_path, tmp_path, tmp_path, vram_gib=0)
    assert r["status"] == "blocked"
    assert r["cuda_initialized"] is False

def test_schema_rejection(monkeypatch, tmp_path):
    with patch("morphorum.zimage_offload_plan.probe_configuration",
               return_value={"status":"blocked", "reasons":["bad source"]}):
        r = plan_offload(tmp_path, tmp_path, tmp_path)
    assert r["status"] == "blocked"
    assert not r["generation_attempted"]

def test_free_capacity_invalid(tmp_path):
    r = plan_offload(tmp_path, tmp_path, tmp_path, vram_gib=16, free_vram_gib=17)
    assert r["status"] == "blocked"

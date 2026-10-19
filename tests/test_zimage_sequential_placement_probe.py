from unittest.mock import patch

from morphorum.zimage_sequential_placement_probe import probe_sequential_placement


def test_default_is_inert(tmp_path):
    result = probe_sequential_placement(tmp_path, tmp_path, tmp_path)
    assert result["status"] == "needs_explicit_execute"
    assert not result["placement_attempted"]
    assert not result["generation_attempted"]


def test_reserve_restrictions(tmp_path):
    result = probe_sequential_placement(tmp_path, tmp_path, tmp_path, execute=True, reserve_gib=1)
    assert result["status"] == "blocked"
    assert not result["encoder_gpu_verified"]


def test_bad_schema_blocks_before_load(tmp_path):
    with patch("morphorum.zimage_sequential_placement_probe.probe_configuration", return_value={"status": "blocked", "reasons": ["bad"]}):
        result = probe_sequential_placement(tmp_path, tmp_path, tmp_path, execute=True)
    assert result["status"] == "blocked"
    assert not result["placement_attempted"]
    assert not result["transformer_gpu_verified"]

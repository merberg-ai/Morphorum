"""Z2.20b3 fail-closed safety tests."""
from unittest.mock import patch
from morphorum.zimage_cpu_probe import probe_cpu_samples


def test_invalid_budget_blocks_before_loading(tmp_path):
    result = probe_cpu_samples(tmp_path, tmp_path, tmp_path, sample_mib=0)
    assert result["status"] == "blocked"
    assert result["gpu_used"] is False
    assert result["weights_fully_loaded"] is False


def test_configuration_failure_blocks_before_torch_import(tmp_path):
    with patch("morphorum.zimage_cpu_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["invalid manifest"]}):
        result = probe_cpu_samples(tmp_path, tmp_path, tmp_path)
    assert result["status"] == "blocked"
    assert result["sample_results"] == []
    assert result["inference_attempted"] is False
    assert result["loadable"] is False

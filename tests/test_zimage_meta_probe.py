"""Z2.20b2 safeguards: fail before model imports on invalid inputs."""
from unittest.mock import patch
from morphorum.zimage_meta_probe import probe_meta_initialization


def test_invalid_paths_fail_closed(tmp_path):
    with patch("morphorum.zimage_meta_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["bad manifest"]}):
        result = probe_meta_initialization(tmp_path / "a", tmp_path / "b", tmp_path / "c")
    assert result["status"] == "blocked"
    assert result["weights_loaded"] is False
    assert result["cuda_used"] is False
    assert result["inference_attempted"] is False
    assert result["loadable"] is False
    assert result["transformer_initialized"] is False

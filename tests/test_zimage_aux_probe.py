"""Z2.20c1 isolation guards."""
from unittest.mock import patch

from morphorum.zimage_aux_probe import probe_components


def test_requires_masked_cuda(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    report = probe_components(tmp_path, tmp_path, tmp_path)
    assert report["status"] == "blocked"
    assert not report["inference_attempted"]
    assert not report["vae_weights_loaded"]


def test_preflight_failure_stops_imports(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_aux_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["bad source"]}):
        report = probe_components(tmp_path, tmp_path, tmp_path)
    assert report["status"] == "blocked"
    assert not report["tokenizer_verified"]
    assert not report["scheduler_initialized"]
    assert not report["vae_meta_initialized"]
    assert not report["loadable"]

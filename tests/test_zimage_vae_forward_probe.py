"""Fail-closed guards for the Z2.20c2b CPU VAE forward probe."""
from unittest.mock import patch

from morphorum.zimage_vae_forward_probe import probe_vae_forward


def test_default_does_not_execute(tmp_path):
    result = probe_vae_forward(tmp_path, tmp_path, tmp_path)
    assert result["status"] == "needs_explicit_execute"
    assert result["forward_attempted"] is False
    assert result["loadable"] is False


def test_requires_cuda_mask(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    result = probe_vae_forward(tmp_path, tmp_path, tmp_path, execute=True)
    assert result["status"] == "blocked"
    assert result["forward_attempted"] is False


def test_refuses_failed_config_probe(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_vae_forward_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["bad schema"]}):
        result = probe_vae_forward(tmp_path, tmp_path, tmp_path, execute=True)
    assert result["status"] == "blocked"
    assert result["forward_attempted"] is False
    assert result["runtime_verified"] is False

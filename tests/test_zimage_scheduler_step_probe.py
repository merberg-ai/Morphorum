from unittest.mock import patch
from morphorum.zimage_scheduler_step_probe import probe_scheduler_math


def test_cuda_mask_required(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    report = probe_scheduler_math(tmp_path, tmp_path, tmp_path)
    assert report["status"] == "blocked"
    assert report["inference_attempted"] is False
    assert report["transformer_forward_attempted"] is False


def test_previous_gate_required(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    with patch("morphorum.zimage_scheduler_step_probe.probe_configuration",
               return_value={"status": "blocked", "reasons": ["invalid source"]}):
        report = probe_scheduler_math(tmp_path, tmp_path, tmp_path)
    assert report["status"] == "blocked"
    assert report["cuda_used"] is False

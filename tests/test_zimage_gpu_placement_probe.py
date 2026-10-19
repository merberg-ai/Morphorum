from morphorum.zimage_gpu_placement_probe import probe_gpu_placement

def test_opt_in_required():
    r = probe_gpu_placement()
    assert r["status"] == "needs_explicit_execute"
    assert r["cuda_initialized"] is False

def test_transfer_bounds_precede_cuda():
    r = probe_gpu_placement(execute=True, max_mib=1000)
    assert r["status"] == "blocked"
    assert r["cuda_initialized"] is False

def test_cuda_mask_rejected(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    r = probe_gpu_placement(execute=True)
    assert r["status"] == "blocked"
    assert r["model_weights_loaded"] is False
    assert r["generation_attempted"] is False

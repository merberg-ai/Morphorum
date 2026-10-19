"""No-authorization and CUDA isolation regression tests for b4."""
from morphorum.zimage_cpu_binding import run_cpu_binding


def test_no_execute_loads_nothing(tmp_path):
    r = run_cpu_binding(tmp_path, tmp_path, tmp_path, family="transformer")
    assert r["status"] == "needs_explicit_execute"
    assert r["binding_attempted"] is False
    assert r["loadable"] is False


def test_cuda_not_masked_blocks(monkeypatch, tmp_path):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    r = run_cpu_binding(tmp_path, tmp_path, tmp_path, family="encoder", execute=True)
    assert r["status"] == "blocked"
    assert r["binding_attempted"] is False


def test_unknown_family_blocks(tmp_path):
    r = run_cpu_binding(tmp_path, tmp_path, tmp_path, family="both", execute=True)
    assert r["status"] == "blocked"

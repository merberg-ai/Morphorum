import pytest
from morphorum.civitai_download import _safe_file, start_download
from morphorum.civitai_detail import _readable

def test_safe_filename():
    assert _safe_file("portrait.safetensors") == "portrait.safetensors"
    with pytest.raises(ValueError):
        _safe_file("portrait.ckpt")
    with pytest.raises(ValueError):
        _safe_file("../escape.safetensors")
    with pytest.raises(ValueError):
        _safe_file("evil?.safetensors")

def test_hub_disabled_never_reads_remote(monkeypatch):
    monkeypatch.setattr("morphorum.civitai_download.load_settings", lambda: {"civitai": {"enabled": False}})
    with pytest.raises(ValueError, match="disabled"):
        start_download(1, 2, "model.safetensors")

def test_description_preserves_paragraph_and_list_lines():
    text = _readable("<h2>About</h2><p>First paragraph.</p><ul><li>One</li><li>Two</li></ul><script>bad()</script>")
    assert "About\n" in text
    assert "• One" in text
    assert "• Two" in text
    assert "bad()" not in text

def test_disk_preflight_rejects_insufficient_space(monkeypatch, tmp_path):
    from morphorum import civitai_download as dl
    class Usage:
        free = 10
    monkeypatch.setattr(dl.shutil, "disk_usage", lambda _: Usage())
    job = {"destination": str(tmp_path / "model.safetensors"), "total_bytes": 1024}
    with pytest.raises(ValueError, match="disk space"):
        dl._check_space(job)

def test_resume_only_interrupted_or_failed(monkeypatch, tmp_path):
    from morphorum import civitai_download as dl
    monkeypatch.setattr(dl, "_initialize", lambda: None)
    monkeypatch.setattr(dl, "_save", lambda: None)
    monkeypatch.setattr(dl, "_dispatch", lambda: None)
    monkeypatch.setattr(dl, "_check_space", lambda job, existing=0: None)
    identifier = "a" * 32
    job = {"id": identifier, "name": "model.safetensors",
           "destination": str(tmp_path / "model.safetensors"),
           "status": "interrupted", "error": "network", "bytes": 0}
    monkeypatch.setattr(dl, "_JOBS", {identifier: job})
    result = dl.resume_download(identifier)
    assert result["status"] == "queued"
    assert result["error"] is None
    with pytest.raises(ValueError, match="Only interrupted"):
        dl.resume_download(identifier)

def test_cancel_interrupted_removes_partial(monkeypatch, tmp_path):
    from morphorum import civitai_download as dl
    monkeypatch.setattr(dl, "_initialize", lambda: None)
    monkeypatch.setattr(dl, "_save", lambda: None)
    identifier = "b" * 32
    job = {"id": identifier, "name": "model.safetensors",
           "destination": str(tmp_path / "model.safetensors"), "status": "interrupted"}
    partial = dl._part(job)
    partial.write_bytes(b"partial")
    monkeypatch.setattr(dl, "_JOBS", {identifier: job})
    assert dl.cancel_download(identifier)["status"] == "cancelled"
    assert not partial.exists()

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

@pytest.mark.parametrize("status", ["completed", "failed", "interrupted", "cancelled"])
def test_remove_queue_entry_never_deletes_downloaded_model(monkeypatch, tmp_path, status):
    from morphorum import civitai_download as dl
    monkeypatch.setattr(dl, "_initialize", lambda: None)
    writes = []
    monkeypatch.setattr(dl, "_save", lambda: writes.append(True))
    ident = "c" * 32
    target = tmp_path / "model.safetensors"
    target.write_bytes(b"keep downloaded weights")
    job = {"id": ident, "name": target.name, "destination": str(target), "status": status}
    part = dl._part(job)
    part.write_bytes(b"discard partial")
    monkeypatch.setattr(dl, "_JOBS", {ident: job})
    monkeypatch.setattr(dl, "_RUNNING", set())
    assert dl.remove_download(ident) == {"removed": True, "id": ident}
    assert ident not in dl._JOBS
    assert target.read_bytes() == b"keep downloaded weights"
    assert part.exists() == (status == "completed")
    assert writes

@pytest.mark.parametrize("status", ["queued", "downloading"])
def test_remove_rejects_active_jobs(monkeypatch, tmp_path, status):
    from morphorum import civitai_download as dl
    monkeypatch.setattr(dl, "_initialize", lambda: None)
    ident = "d" * 32
    job = {"id": ident, "destination": str(tmp_path / "model.safetensors"), "status": status}
    monkeypatch.setattr(dl, "_JOBS", {ident: job})
    monkeypatch.setattr(dl, "_RUNNING", set())
    with pytest.raises(ValueError, match="Cancel"):
        dl.remove_download(ident)
    assert ident in dl._JOBS

def test_remove_rejects_still_running_cancelled_job(monkeypatch, tmp_path):
    from morphorum import civitai_download as dl
    monkeypatch.setattr(dl, "_initialize", lambda: None)
    ident = "e" * 32
    job = {"id": ident, "destination": str(tmp_path / "model.safetensors"), "status": "cancelled"}
    monkeypatch.setattr(dl, "_JOBS", {ident: job})
    monkeypatch.setattr(dl, "_RUNNING", {ident})
    with pytest.raises(ValueError, match="wait"):
        dl.remove_download(ident)

def test_zimage_civitai_destination_defaults_to_separate_managed_subfolder(monkeypatch, tmp_path):
    from morphorum import civitai_download as dl
    import hashlib
    import threading
    monkeypatch.setattr(dl, "_initialize", lambda: None)
    monkeypatch.setattr(dl, "_save", lambda: None)
    monkeypatch.setattr(dl, "_dispatch", lambda: None)
    monkeypatch.setattr(dl, "_check_space", lambda job, existing=0: None)
    monkeypatch.setattr(dl, "_JOBS", {})
    monkeypatch.setattr(dl, "_RUNNING", set())
    monkeypatch.setattr(dl, "managed_model_location", lambda family, cfg: tmp_path / "managed-zimage")
    monkeypatch.setattr(dl, "load_settings", lambda: {"civitai": {"enabled": True}, "models": {"zimage": {"checkpoints": []}}})
    monkeypatch.setattr(dl, "model_details", lambda _: {"type": "Checkpoint", "versions": [{
        "id": 12, "base_model": "ZImageTurbo", "files": [{
            "id": 17, "name": "civitai-zimage.safetensors", "size_kb": 1024,
            "sha256": "f" * 64
        }]
    }]})
    job = dl.start_download(10, 12, "civitai-zimage.safetensors")
    assert job["status"] == "queued"
    full = dl._JOBS[job["id"]]
    assert full["destination"] == str(tmp_path / "managed-zimage" / "civitai-checkpoints" / "civitai-zimage.safetensors")
    assert (tmp_path / "managed-zimage" / "civitai-checkpoints").is_dir()

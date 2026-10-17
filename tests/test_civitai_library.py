import json
import pytest
from morphorum import civitai_library as lib
from morphorum.civitai_search import CivitaiSearchError

def test_disabled_read_guard(monkeypatch):
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {"enabled": False}})
    with pytest.raises(CivitaiSearchError) as exc:
        lib.cached_metadata("abc")
    assert exc.value.status == 403

def test_cache_read_invalidates_replaced_local_file(monkeypatch, tmp_path):
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"weights")
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda model_id: {"path": str(model)})
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {"enabled": True, "load_previews": True}})
    stat = model.stat()
    lib._atomic_json(lib._directory("abc") / "metadata.json", {
        "synced": True, "model_id": "abc", "name": "Test", "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns, "preview": "preview.jpg"})
    assert lib.cached_metadata("abc")["synced"]
    model.write_bytes(b"replaced weights")
    assert lib.cached_metadata("abc")["stale"]

def test_preview_policy_applies_after_caching(monkeypatch, tmp_path):
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"weights")
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda model_id: {"path": str(model)})
    stat = model.stat()
    lib._atomic_json(lib._directory("abc") / "metadata.json", {
        "synced": True, "model_id": "abc", "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns, "preview": "preview.jpg",
        "preview_allowed_mature": True})
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {
        "enabled": True, "load_previews": True, "allow_mature": False}})
    assert "preview" not in lib.cached_metadata("abc")
    with pytest.raises(CivitaiSearchError):
        lib.preview_path("abc")

def test_invalid_id_rejected(tmp_path):
    with pytest.raises(CivitaiSearchError):
        lib._directory("../outside")

def test_invalid_cache_shape_ignored(monkeypatch, tmp_path):
    model = tmp_path / "weights.safetensors"
    model.write_bytes(b"weights")
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda _: {"path": str(model)})
    directory = lib._directory("abc")
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text('[]', encoding="utf-8")
    assert not lib._read("abc")["synced"]

def test_missing_cached_image_is_not_served(monkeypatch, tmp_path):
    model = tmp_path / "weights.safetensors"
    model.write_bytes(b"weights")
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda _: {"path": str(model)})
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {"enabled": True, "load_previews": True}})
    stat = model.stat()
    lib._atomic_json(lib._directory("abc") / "metadata.json", {
        "synced": True, "model_id": "abc", "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns, "preview": "preview.jpg"})
    with pytest.raises(CivitaiSearchError):
        lib.preview_path("abc")

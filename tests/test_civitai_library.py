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


def test_cached_catalog_batches_only_valid_local_metadata(monkeypatch, tmp_path):
    model = tmp_path / "adapter.safetensors"
    model.write_bytes(b"weights")
    stat = model.stat()
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda mid: {"path": str(model)} if mid == "adapter1" else None)
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {
        "enabled": True, "load_previews": True, "allow_mature": False,
    }})
    lib._atomic_json(lib._directory("adapter1") / "metadata.json", {
        "synced": True, "model_id": "adapter1", "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "preview": "preview.webp", "preview_allowed_mature": False,
        "name": "Verified Adapter", "description": "Too long to include in list",
        "trained_words": ["word"], "version": "V1",
    })
    found = lib.cached_catalog(["adapter1", "missing", "adapter1"])
    assert list(found["entries"]) == ["adapter1"]
    assert found["entries"]["adapter1"]["preview"] == "preview.webp"
    assert found["entries"]["adapter1"]["trained_words"] == ["word"]
    assert "description" not in found["entries"]["adapter1"]
    assert "path" not in found["entries"]["adapter1"]


def test_cached_catalog_obeys_preview_settings_and_invalidates(monkeypatch, tmp_path):
    model = tmp_path / "checkpoint.safetensors"
    model.write_bytes(b"weights")
    stat = model.stat()
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda _: {"path": str(model)})
    cfg = {"enabled": True, "load_previews": False, "allow_mature": False}
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": cfg})
    lib._atomic_json(lib._directory("ckpt") / "metadata.json", {
        "synced": True, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "preview": "preview.jpg", "preview_allowed_mature": True,
    })
    assert lib.cached_catalog(["ckpt"])["entries"]["ckpt"]["preview"] is None
    cfg["load_previews"] = True
    assert lib.cached_catalog(["ckpt"])["entries"]["ckpt"]["preview"] is None
    cfg["allow_mature"] = True
    assert lib.cached_catalog(["ckpt"])["entries"]["ckpt"]["preview"] == "preview.jpg"
    model.write_bytes(b"replaced model file")
    assert lib.cached_catalog(["ckpt"])["entries"] == {}


def test_cached_catalog_rejects_unbounded_bad_ids_and_disabled_hub(monkeypatch):
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {"enabled": True}})
    for ids in (None, ["../escape"], ["x"] * 121, ["abc", None]):
        with pytest.raises(CivitaiSearchError) as exc:
            lib.cached_catalog(ids)
        assert exc.value.status == 422
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {"enabled": False}})
    with pytest.raises(CivitaiSearchError) as exc:
        lib.cached_catalog(["ok"])
    assert exc.value.status == 403

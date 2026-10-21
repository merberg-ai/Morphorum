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
    image_path = lib._directory("adapter1") / "preview.webp"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"RIFF" + bytes(4) + b"WEBP" + b"preview")
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
    image_path = lib._directory("ckpt") / "preview.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"test jpg")
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


def test_sync_downloads_valid_image_after_other_preview_is_unavailable(monkeypatch, tmp_path):
    import httpx
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"weights")
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda _: {"path": str(model)})
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {
        "enabled": True, "load_previews": True, "allow_mature": True,
    }})
    monkeypatch.setattr(lib, "identify_model", lambda _: {
        "found": True, "sha256": "e" * 64,
        "civitai_model_id": 6, "version_id": 12,
        "url": "https://civitai.com/models/6?modelVersionId=12",
    })
    monkeypatch.setattr(lib, "model_details", lambda _: {
        "name": "Demo", "creator": "Creator", "mature": False,
        "description": "Description", "versions": [{
            "id": 12, "name": "V1", "base_model": "SDXL 1.0",
            "trained_words": ["paint"], "images": [
                {"url": "https://image.civitai.com/not-an-image.jpg", "mature": False},
                {"url": "https://image.civitai.com/real.webp", "mature": False},
            ],
        }],
    })
    called = []
    def handler(request):
        called.append(str(request.url))
        if request.url.path.endswith("not-an-image.jpg"):
            return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"broken")
        return httpx.Response(200, headers={"content-type": "image/webp"},
                              content=b"RIFF" + b"\x00" * 4 + b"WEBP" + b"payload")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = lib.sync_metadata("verified", client=client)
    assert len(called) == 2
    assert result["synced"] and result["preview"] == "preview.webp"
    assert result["preview_allowed_mature"] is False
    assert lib.preview_path("verified").read_bytes().startswith(b"RIFF")
    assert lib.cached_catalog(["verified"])["entries"]["verified"]["preview"] == "preview.webp"


def test_sync_retains_previous_image_when_remote_unavailable(monkeypatch, tmp_path):
    import httpx
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"weights")
    stat = model.stat()
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda _: {"path": str(model)})
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {
        "enabled": True, "load_previews": True, "allow_mature": False,
    }})
    monkeypatch.setattr(lib, "identify_model", lambda _: {
        "found": True, "sha256": "a" * 64, "civitai_model_id": 8,
        "version_id": 5, "url": "https://civitai.com/models/8?modelVersionId=5",
    })
    monkeypatch.setattr(lib, "model_details", lambda _: {
        "name": "Demo", "creator": "Creator", "mature": False,
        "versions": [{"id": 5, "name": "V1", "base_model": "SDXL 1.0",
                      "trained_words": [], "images": [
                          {"url": "https://image.civitai.com/missing.jpg", "mature": False}]}],
    })
    folder = lib._directory("local")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "preview.jpg").write_bytes(b"\xff\xd8\xffOld preview")
    lib._atomic_json(folder / "metadata.json", {
        "synced": True, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "sha256": "a" * 64, "version_id": 5, "preview": "preview.jpg",
        "preview_allowed_mature": False,
    })
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        new = lib.sync_metadata("local", client=client)
    assert new["preview"] == "preview.jpg"
    assert lib.preview_path("local").read_bytes().endswith(b"Old preview")
    assert "preview_warning" not in new or isinstance(new["preview_warning"], str)


def test_preview_diagnostic_distinguishes_disabled_missing_and_filtered(monkeypatch, tmp_path):
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"weights")
    stat = model.stat()
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda _: {"path": str(model)})
    cfg = {"enabled": True, "load_previews": True, "allow_mature": False}
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": cfg})
    lib._atomic_json(lib._directory("id") / "metadata.json", {
        "synced": True, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "preview": "preview.jpg", "preview_allowed_mature": False})
    data = lib.cached_metadata("id")
    assert data["preview_status"] == "missing"
    assert "thumbnail" in data["preview_warning"].lower()
    cfg["load_previews"] = False
    assert lib.cached_metadata("id")["preview_status"] == "disabled"
    cfg["load_previews"] = True
    (lib._directory("id") / "preview.jpg").write_bytes(b"placeholder")
    manifest = lib._directory("id") / "metadata.json"
    record = json.loads(manifest.read_text())
    record["preview_allowed_mature"] = True
    lib._atomic_json(manifest, record)
    assert lib.cached_metadata("id")["preview_status"] == "filtered"
    cfg["allow_mature"] = True
    assert lib.cached_metadata("id")["preview_status"] == "ready"


def test_preview_uses_other_version_of_same_verified_model(monkeypatch, tmp_path):
    import httpx
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"weights")
    monkeypatch.setattr(lib, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(lib, "get_model", lambda _: {"path": str(model)})
    monkeypatch.setattr(lib, "load_settings", lambda: {"civitai": {
        "enabled": True, "load_previews": True, "allow_mature": False}})
    monkeypatch.setattr(lib, "identify_model", lambda _: {
        "found": True, "sha256": "a" * 64, "civitai_model_id": 9,
        "version_id": 99, "url": "https://civitai.com/models/9?modelVersionId=99"})
    monkeypatch.setattr(lib, "model_details", lambda _: {
        "name": "Demo", "creator": "Maker", "mature": False,
        "versions": [
            {"id": 99, "name": "Old", "base_model": "SDXL 1.0",
             "trained_words": [], "images": []},
            {"id": 100, "name": "New", "images": [
                {"url": "https://image.civitai.com/new.jpg", "mature": False}]}],
    })
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, headers={"Content-Type": "image/jpeg"},
                              content=bytes.fromhex("ffd8ff") + b"fake-preview")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data = lib.sync_metadata("id", client=client)
    assert len(calls) == 1
    assert data["preview"] == "preview.jpg"
    assert data["preview_source"] == "same_model_other_version"
    assert data["preview_status"] == "ready"


def test_preview_redirect_must_remain_on_civitai(monkeypatch):
    import httpx
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://evil.example/take"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CivitaiSearchError, match="untrusted host"):
            lib._fetch_preview_image(client, "https://image.civitai.com/redirect")
    assert not lib._trusted_preview_url("http://image.civitai.com/test")
    assert not lib._trusted_preview_url("https://image.civitai.com.evil.example/test")
    assert not lib._trusted_preview_url("https://evil.example@image.civitai.com/path")

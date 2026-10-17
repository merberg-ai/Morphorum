import hashlib
import httpx
import pytest
from morphorum import civitai_identify as module
from morphorum.civitai_search import CivitaiSearchError

def test_disabled_never_contacts_remote(monkeypatch):
    monkeypatch.setattr(module, "load_settings", lambda: {"civitai": {"enabled": False}})
    with pytest.raises(CivitaiSearchError) as error:
        module.identify_model("abc")
    assert error.value.status == 403

def test_exact_match_and_cached_digest(monkeypatch, tmp_path):
    path = tmp_path / "sample.safetensors"
    path.write_bytes(b"sample weights")
    monkeypatch.setattr(module, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(module, "load_settings", lambda: {"civitai": {"enabled": True, "allow_mature": False}})
    monkeypatch.setattr(module, "get_model", lambda model_id: {"kind": "loras", "path": str(path)})
    monkeypatch.setattr(module, "get_token", lambda: "")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": 8, "modelId": 17,
                  "name": "Version", "baseModel": "SDXL 1.0", "model": {"name": "Portrait"}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = module.identify_model("opaque-id", client=client)
        second = module.identify_model("opaque-id", client=client)
    assert first["found"] and second["found"]
    assert first["confidence"] == "Exact SHA-256 file match"
    assert calls[0].url.path.endswith(hashlib.sha256(path.read_bytes()).hexdigest().upper())
    assert not any(str(path) in str(item) for item in (first, second))

def test_unmatched_hash(monkeypatch, tmp_path):
    path = tmp_path / "sample.safetensors"
    path.write_bytes(b"data")
    monkeypatch.setattr(module, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(module, "load_settings", lambda: {"civitai": {"enabled": True}})
    monkeypatch.setattr(module, "get_model", lambda model_id: {"kind": "checkpoints", "path": str(path)})
    monkeypatch.setattr(module, "get_token", lambda: "")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
        assert not module.identify_model("ckpt-id", client=client)["found"]

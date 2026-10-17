from morphorum import civitai_installed as installed
from morphorum.civitai_search import CivitaiSearchError
import pytest

def test_disabled_hub_does_not_scan(monkeypatch):
    monkeypatch.setattr(installed, "load_settings", lambda: {"civitai": {"enabled": False}})
    monkeypatch.setattr(installed, "list_models", lambda **kwargs: (_ for _ in ()).throw(AssertionError("No scan")))
    with pytest.raises(CivitaiSearchError) as exc:
        installed.installed_versions(123)
    assert exc.value.status == 403

def test_matches_only_verified_cached_version(monkeypatch):
    monkeypatch.setattr(installed, "load_settings", lambda: {"civitai": {"enabled": True}})
    monkeypatch.setattr(installed, "list_models", lambda **kwargs: [
        {"id": "a", "name": "A", "family": "sdxl", "kind": "loras"},
        {"id": "b", "name": "B", "family": "flux", "kind": "checkpoints"},
        {"id": "c", "name": "C", "family": "sdxl", "kind": "loras"},
    ])
    cache = {
        "a": {"synced": True, "civitai_model_id": 71, "version_id": 5, "trained_words": ["trigger"]},
        "b": {"synced": True, "civitai_model_id": 72, "version_id": 7},
        "c": {"synced": False, "civitai_model_id": 71, "version_id": 5},
    }
    monkeypatch.setattr(installed, "_read", lambda model_id: cache[model_id])
    result = installed.installed_versions(71)
    assert [item["id"] for item in result["installed"]] == ["a"]
    assert result["installed"][0]["trained_words"] == ["trigger"]
    assert "path" not in str(result)

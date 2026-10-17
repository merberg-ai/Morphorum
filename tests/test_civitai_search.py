import json

import httpx
import pytest

from morphorum.civitai_search import CivitaiSearchError, search_models


def _client(capture):
    def handle(request):
        capture.append(request)
        return httpx.Response(200, json={"items": [
            {"id": 123, "name": "Example", "type": "LORA", "nsfw": False,
             "creator": {"username": "tester"}, "stats": {"downloadCount": 100},
             "modelVersions": [{"id": 42, "name": "v1", "baseModel": "SDXL 1.0",
                                 "images": [{"url": "https://example.com/preview.jpg"}]}]},
            {"id": 124, "name": "Hidden", "type": "LORA", "nsfw": True}
        ], "metadata": {"nextCursor": "opaque|42"}})
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_disabled_hub_never_calls_network(monkeypatch):
    monkeypatch.setattr("morphorum.settings.load_settings", lambda: {"civitai": {"enabled": False}})
    calls = []
    with _client(calls) as client:
        with pytest.raises(CivitaiSearchError) as exc:
            search_models(query="cat", client=client)
    assert exc.value.status == 403
    assert not calls


def test_search_uses_filters_cursor_and_sanitizes(monkeypatch):
    monkeypatch.setattr("morphorum.settings.load_settings", lambda: {"civitai": {
        "enabled": True, "allow_mature": False, "load_previews": True}})
    monkeypatch.delenv("CIVITAI_API_TOKEN", raising=False)
    calls = []
    with _client(calls) as client:
        result = search_models(query="skull", model_type="LORA", base_model="SDXL 1.0",
                               sort="Newest", cursor="opaque|24", client=client)
    assert len(calls) == 1
    assert calls[0].url.params["cursor"] == "opaque|24"
    assert calls[0].url.params["query"] == "skull"
    assert calls[0].url.params["types"] == "LORA"
    assert calls[0].url.params["baseModels"] == "SDXL 1.0"
    assert calls[0].url.params["nsfw"] == "false"
    assert result["count"] == 1
    assert result["next_cursor"] == "opaque|42"
    assert result["items"][0]["thumbnail_url"] == "https://example.com/preview.jpg"
    assert "modelVersions" not in result["items"][0]


def test_invalid_filter_does_not_contact_upstream(monkeypatch):
    monkeypatch.setattr("morphorum.settings.load_settings", lambda: {"civitai": {"enabled": True}})
    calls = []
    with _client(calls) as client:
        with pytest.raises(CivitaiSearchError) as exc:
            search_models(model_type="Arbitrary", client=client)
    assert exc.value.status == 422
    assert not calls


def test_mature_requires_saved_permission(monkeypatch):
    monkeypatch.setattr("morphorum.settings.load_settings", lambda: {"civitai": {
        "enabled": True, "allow_mature": False, "load_previews": False}})
    calls = []
    with _client(calls) as client:
        response = search_models(allow_mature=True, client=client)
    assert calls[0].url.params["nsfw"] == "false"
    assert response["items"][0]["thumbnail_url"] is None

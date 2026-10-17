import httpx
import pytest

from morphorum.civitai_detail import model_details
from morphorum.civitai_search import CivitaiSearchError


def client_for(payload, calls):
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_disabled_details_do_not_use_network(monkeypatch):
    monkeypatch.setattr("morphorum.civitai_detail.load_settings", lambda: {"civitai": {"enabled": False}})
    calls = []
    with client_for({"id": 123}, calls) as client:
        with pytest.raises(CivitaiSearchError) as exc:
            model_details(123, client=client)
    assert exc.value.status == 403
    assert calls == []


def test_normalized_versions_and_examples(monkeypatch):
    monkeypatch.setattr("morphorum.civitai_detail.load_settings", lambda: {"civitai": {
        "enabled": True, "load_previews": True, "allow_mature": False}})
    calls = []
    data = {"id": 123, "name": "Example", "type": "LORA", "nsfw": False,
            "creator": {"username": "Author"}, "tags": ["portrait"],
            "modelVersions": [{"id": 8, "name": "XL", "baseModel": "SDXL 1.0",
                               "trainedWords": ["detail"], "images": [
                                  {"url": "https://example.com/a.jpg", "nsfw": "None"},
                                  {"url": "https://example.com/b.jpg", "nsfw": "Explicit"}],
                               "files": [{"name": "weights.safetensors", "sizeKB": 512,
                                          "metadata": {"format": "SafeTensor"}}]}]}
    with client_for(data, calls) as client:
        output = model_details(123, client=client)
    assert output["versions"][0]["trained_words"] == ["detail"]
    assert len(output["versions"][0]["images"]) == 1
    assert output["versions"][0]["files"][0]["name"] == "weights.safetensors"
    assert calls[0].url.path.endswith("/models/123")


def test_mature_model_blocked(monkeypatch):
    monkeypatch.setattr("morphorum.civitai_detail.load_settings", lambda: {"civitai": {
        "enabled": True, "allow_mature": False}})
    with client_for({"id": 123, "nsfw": True}, []) as client:
        with pytest.raises(CivitaiSearchError) as exc:
            model_details(123, client=client)
    assert exc.value.status == 403

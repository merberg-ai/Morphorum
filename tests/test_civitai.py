from __future__ import annotations

import hashlib
import json

import httpx

import morphorum.civitai as civitai


def test_civitai_hash_lookup_uses_exact_sha256_and_normalized_fields(tmp_path, monkeypatch):
    file = tmp_path / "lo.safetensors"
    file.write_bytes(b"synthetic-lora")
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    monkeypatch.setattr(civitai, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(civitai, "get_model", lambda _: {
        "kind": "loras", "path": str(file),
    })
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.url.path == "/api/v1/model-versions/by-hash/" + digest.upper()
        return httpx.Response(200, json={
            "id": 9001, "modelId": 123, "name": "v2",
            "baseModel": "SDXL 1.0", "trainedWords": ["chalkdust"],
            "description": "<p>Hand-drawn chalk <b>style</b>.</p>",
            "model": {"name": "Chalkdust", "type": "LORA", "nsfw": False},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = civitai.lookup_civitai("fake-id", client=client)
    assert result["found"] is True
    assert result["source"] == "sha256"
    assert result["sha256"] == digest
    assert result["trained_words"] == ["chalkdust"]
    assert result["base_model"] == "SDXL 1.0"
    assert result["url"] == "https://civitai.com/models/123?modelVersionId=9001"
    assert result["description_text"] == "Hand-drawn chalk style."
    assert len(calls) == 1
    assert (tmp_path / "cache" / "lora-civitai" / "hash-fake-id.json").is_file()


def test_civitai_sidecar_id_fallback_is_explicitly_unverified(tmp_path, monkeypatch):
    file = tmp_path / "lora.safetensors"
    file.write_bytes(b"unmatched-file")
    file.with_suffix(".civitai.info").write_text(
        json.dumps({"modelVersionId": 777}), encoding="utf-8",
    )
    monkeypatch.setattr(civitai, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(civitai, "get_model", lambda _: {"kind": "loras", "path": str(file)})
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if "/by-hash/" in request.url.path:
            return httpx.Response(404)
        assert request.url.path == "/api/v1/model-versions/777"
        return httpx.Response(200, json={
            "id": 777, "modelId": 33, "name": "version", "trainedWords": ["trigger"],
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = civitai.lookup_civitai("fake-id", client=client)
    assert len(calls) == 2
    assert result["source"] == "sidecar_version_id"
    assert "not hash-verified" in result["confidence"]


def test_civitai_missing_and_error_handling(tmp_path, monkeypatch):
    file = tmp_path / "missing.safetensors"
    file.write_bytes(b"no remote version")
    monkeypatch.setattr(civitai, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(civitai, "get_model", lambda _: {"kind": "loras", "path": str(file)})
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client:
        result = civitai.lookup_civitai("fake-id", client=client)
    assert result["found"] is False

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        try:
            civitai.lookup_civitai("fake-id", client=client)
        except civitai.CivitaiLookupError as exc:
            assert "503" in str(exc)
        else:
            raise AssertionError("Expected remote 503 to become a safe lookup error")

    monkeypatch.setattr(civitai, "get_model", lambda _: {"kind": "checkpoints"})
    try:
        civitai.lookup_civitai("fake-id")
    except civitai.CivitaiLookupError:
        pass
    else:
        raise AssertionError("Checkpoint cannot be looked up as LoRA")

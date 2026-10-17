from morphorum import civitai_updates as updates

def test_detects_newer_matching_and_cross_base_versions(monkeypatch):
    monkeypatch.setattr(updates, "identify_model", lambda _: {"found": True, "name": "Sample", "version": "v1", "version_id": 10, "civitai_model_id": 99, "confidence": "Exact SHA-256 file match"})
    monkeypatch.setattr(updates, "get_model", lambda _: {"kind": "loras"})
    monkeypatch.setattr(updates, "model_details", lambda _: {"type": "LORA", "versions": [
        {"id": 10, "name": "v1", "base_model": "SDXL 1.0", "created_at": "2026-01-01T00:00:00Z"},
        {"id": 11, "name": "v2", "base_model": "SDXL 1.0", "created_at": "2026-02-01T00:00:00Z"},
        {"id": 12, "name": "Flux", "base_model": "Flux.1 D", "created_at": "2026-03-01T00:00:00Z"},
        {"id": 8, "name": "older", "base_model": "SDXL 1.0", "created_at": "2025-01-01T00:00:00Z"},
    ]})
    result = updates.check_model_update("local")
    assert result["status"] == "newer_available"
    assert [v["version_id"] for v in result["candidates"]] == [12, 11]
    assert not result["candidates"][0]["potentially_compatible"]
    assert result["candidates"][1]["potentially_compatible"]

def test_unidentified_does_not_load_remote_model_details(monkeypatch):
    monkeypatch.setattr(updates, "identify_model", lambda _: {"found": False, "message": "No exact match"})
    monkeypatch.setattr(updates, "model_details", lambda _: (_ for _ in ()).throw(AssertionError("Must not fetch details")))
    assert updates.check_model_update("missing")["status"] == "unidentified"

def test_missing_date_does_not_claim_newer(monkeypatch):
    monkeypatch.setattr(updates, "identify_model", lambda _: {"found": True, "name": "Sample", "version": "v1", "version_id": 1, "civitai_model_id": 2, "confidence": "Exact SHA-256 file match"})
    monkeypatch.setattr(updates, "get_model", lambda _: {"kind": "checkpoints"})
    monkeypatch.setattr(updates, "model_details", lambda _: {"type": "Checkpoint", "versions": [
        {"id": 1, "name": "v1", "base_model": "SDXL 1.0", "created_at": ""},
        {"id": 2, "name": "v2", "base_model": "SDXL 1.0", "created_at": "2026-03-01T00:00:00"},
    ]})
    assert updates.check_model_update("local")["status"] == "up_to_date"

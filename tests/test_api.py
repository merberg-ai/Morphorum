from __future__ import annotations

from fastapi.testclient import TestClient

import morphorum.settings as settings_module
from morphorum.app import app
from morphorum.console import clear_console, emit_console


def test_frontend_and_health() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        frontend = client.get("/")
        assert frontend.status_code == 200
        assert "Morphorum" in frontend.text
        assert "Settings" in frontend.text
        assert "Console" in frontend.text


def test_settings_round_trip_and_path_validation(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "config.yaml"
    checkpoint_dir = tmp_path / "sdxl-checkpoints"
    lora_dir = tmp_path / "sdxl-loras"
    checkpoint_dir.mkdir()
    lora_dir.mkdir()

    monkeypatch.setattr(settings_module, "USER_CONFIG", user_config)

    payload = {
        "models": {
            "sdxl": {
                "checkpoints": [str(checkpoint_dir)],
                "loras": [str(lora_dir)],
            }
        },
        "ui": {"image_preview_limit": 7},
        "performance": {"unload_after_generation": True},
    }

    with TestClient(app) as client:
        saved = client.put("/api/settings", json=payload)
        assert saved.status_code == 200
        assert saved.json()["status"] == "saved"

        loaded = client.get("/api/settings")
        assert loaded.status_code == 200
        settings = loaded.json()["settings"]
        assert settings["models"]["sdxl"]["checkpoints"] == [str(checkpoint_dir)]
        assert settings["models"]["sdxl"]["loras"] == [str(lora_dir)]
        assert settings["ui"]["image_preview_limit"] == 7
        assert settings["performance"]["unload_after_generation"] is True

        # Enabled modern families must remain present even when only one family is saved.
        for family in ("sdxl", "flux", "zimage"):
            assert family in settings["models"]
        assert "sd15" not in settings["models"]
        assert "sd2" not in settings["models"]

        checked = client.post("/api/settings/validate-path", json={"path": str(checkpoint_dir)})
        assert checked.status_code == 200
        assert checked.json()["exists"] is True
        assert checked.json()["is_directory"] is True
        assert checked.json()["readable"] is True

    assert user_config.exists()


def test_console_snapshot_api() -> None:
    clear_console()
    event = emit_console("warning", "model", "test model message")

    with TestClient(app) as client:
        response = client.get("/api/console?limit=100")
        assert response.status_code == 200
        events = response.json()["events"]

    match = next(item for item in events if item["id"] == event.id)
    assert match["level"] == "warning"
    assert match["category"] == "model"
    assert match["message"] == "test model message"


def test_model_lifecycle_api_when_nothing_is_loaded() -> None:
    with TestClient(app) as client:
        status = client.get("/api/generation/model")
        assert status.status_code == 200
        assert "loaded" in status.json()

        unloaded = client.post("/api/generation/model/unload", json={})
        assert unloaded.status_code == 200
        assert unloaded.json()["loaded"] is False

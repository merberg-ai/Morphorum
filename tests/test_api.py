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
        asset_version = health.json()["frontend_asset_version"]
        assert len(asset_version) == 12

        frontend = client.get("/")
        assert frontend.status_code == 200
        assert "Morphorum" in frontend.text
        assert "Settings" in frontend.text
        assert "Console" in frontend.text
        assert "__MORPHORUM_ASSET_VERSION__" not in frontend.text
        assert f"/assets/app.css?v={asset_version}" in frontend.text
        assert f"/assets/app.js?v={asset_version}" in frontend.text
        assert "no-cache" in frontend.headers.get("cache-control", "")

        css = client.get("/assets/app.css")
        assert css.status_code == 200
        assert "no-cache" in css.headers.get("cache-control", "")


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
        "ui": {
            "theme": "midnight-glass",
            "font_style": "technical",
            "mono_font_style": "cascadia",
            "ui_scale": "compact",
            "image_preview_limit": 7,
        },
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
        assert settings["ui"]["theme"] == "midnight-glass"
        assert settings["ui"]["font_style"] == "technical"
        assert settings["ui"]["mono_font_style"] == "cascadia"
        assert settings["ui"]["ui_scale"] == "compact"
        assert settings["ui"]["image_preview_limit"] == 7
        assert settings["performance"]["unload_after_generation"] is True

        # Only external model families receive scan-path settings.
        for family in ("sdxl", "flux"):
            assert family in settings["models"]
        assert "zimage" not in settings["models"]
        assert "sd15" not in settings["models"]
        assert "sd2" not in settings["models"]
        assert settings["managed_models"]["locations"]["zimage"] == r".\ckpts\z-image"

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


def test_legacy_zimage_paths_are_preserved_but_not_recreated(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "config.yaml"
    monkeypatch.setattr(settings_module, "USER_CONFIG", user_config)

    legacy_path = str(tmp_path / "old-zimage")
    saved = settings_module.save_settings(
        {
            "models": {
                "zimage": {
                    "checkpoints": [legacy_path],
                    "loras": [],
                }
            }
        }
    )
    assert saved["models"]["zimage"]["checkpoints"] == [legacy_path]
    assert saved["managed_models"]["locations"]["zimage"] == r".\ckpts\z-image"


def test_managed_model_catalog_api_lists_zimage_turbo(tmp_path, monkeypatch) -> None:
    import morphorum.managed_models as managed_models

    monkeypatch.setattr(
        managed_models,
        "managed_model_location",
        lambda family: tmp_path / family,
    )

    with TestClient(app) as client:
        response = client.get("/api/managed-models")

    assert response.status_code == 200
    models = response.json()["models"]
    zimage = next(item for item in models if item["id"] == "zimage-turbo")
    assert zimage["family"] == "zimage"
    assert zimage["repo_id"] == "Tongyi-MAI/Z-Image-Turbo"
    assert zimage["installed"] is False
    assert zimage["status"] == "not_installed"


def test_invalid_appearance_values_fall_back_to_defaults(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "config.yaml"
    monkeypatch.setattr(settings_module, "USER_CONFIG", user_config)

    saved = settings_module.save_settings(
        {
            "ui": {
                "theme": "future-theme-that-does-not-exist",
                "font_style": "papyrus-but-worse",
                "mono_font_style": "typewriter-from-hell",
                "ui_scale": "microscopic",
            }
        }
    )

    assert saved["ui"]["theme"] == "midnight-glass"
    assert saved["ui"]["font_style"] == "modern"
    assert saved["ui"]["mono_font_style"] == "modern-mono"
    assert saved["ui"]["ui_scale"] == "compact"

from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient
from PIL import Image

import morphorum.animation_motion as animation_motion
import morphorum.animation_projects as animation_projects
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
        assert "Animation" in frontend.text
        assert 'id="view-animation"' in frontend.text
        assert '<select id="animation-sampler"' in frontend.text
        assert 'id="copy-console-view"' in frontend.text
        assert 'id="copy-console-buffer"' in frontend.text
        assert "__MORPHORUM_ASSET_VERSION__" not in frontend.text
        assert f"/assets/app.css?v={asset_version}" in frontend.text
        assert f"/assets/app.js?v={asset_version}" in frontend.text
        assert f"/assets/animation.css?v={asset_version}" in frontend.text
        assert f"/assets/animation.js?v={asset_version}" in frontend.text
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


def test_console_api_can_return_full_server_buffer() -> None:
    clear_console()
    for index in range(1105):
        emit_console("info", "runtime", f"bulk-{index:04d}")

    with TestClient(app) as client:
        response = client.get("/api/console?limit=1500")
        assert response.status_code == 200
        events = response.json()["events"]

    bulk = [item for item in events if item["message"].startswith("bulk-")]
    assert len(bulk) == 1105
    assert bulk[0]["message"] == "bulk-0000"
    assert bulk[-1]["message"] == "bulk-1104"


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


def test_animation_project_api_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(animation_motion, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_motion, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_motion, "PREVIEW_MAX_CAPTURE_FRAMES", 8)

    with TestClient(app) as client:
        created = client.post(
            "/api/animation/projects",
            json={"name": "API Animation"},
        )
        assert created.status_code == 201
        project = created.json()["project"]
        project_id = project["id"]
        assert project["name"] == "API Animation"

        listing = client.get("/api/animation/projects")
        assert listing.status_code == 200
        assert any(item["id"] == project_id for item in listing.json()["projects"])

        project["animation"]["max_frames"] = 48
        project["animation"]["fps"] = 12
        project["prompts"] = {"0": "start", "24": "middle"}
        project["motion"]["zoom"] = "0:(1.0), 47:(1.02)"

        saved = client.put(
            f"/api/animation/projects/{project_id}",
            json=project,
        )
        assert saved.status_code == 200
        assert saved.json()["project"]["animation"]["max_frames"] == 48
        assert saved.json()["project"]["prompts"]["24"] == "middle"

        loaded = client.get(f"/api/animation/projects/{project_id}")
        assert loaded.status_code == 200
        loaded_project = loaded.json()["project"]
        assert loaded_project["animation"]["fps"] == 12.0
        assert loaded_project["motion"]["zoom"] == "0:(1.0), 47:(1.02)"
        assert loaded.json()["path"].endswith("project.json")

        validation = client.post(
            "/api/animation/validate-schedules",
            json={"project": loaded_project},
        )
        assert validation.status_code == 200
        assert validation.json()["valid"] is True

        resolved = client.post(
            "/api/animation/resolve-frame",
            json={"project": loaded_project, "frame": 12},
        )
        assert resolved.status_code == 200
        frame = resolved.json()["resolved"]
        assert frame["frame"] == 12
        assert frame["motion"]["zoom"] > 1.0
        assert frame["prompts"]["positive"]["from_text"] == "start"
        assert frame["prompts"]["positive"]["to_text"] == "middle"

        series = client.post(
            "/api/animation/schedule-series",
            json={
                "project": loaded_project,
                "field": "motion.zoom",
                "sample_count": 12,
            },
        )
        assert series.status_code == 200
        assert series.json()["field"] == "motion.zoom"
        assert series.json()["samples"][0]["frame"] == 0
        assert series.json()["samples"][-1]["frame"] == 47

        source_bytes = io.BytesIO()
        Image.new("RGB", (80, 60), "orange").save(source_bytes, format="PNG")
        uploaded = client.post(
            f"/api/animation/projects/{project_id}/source-image",
            content=source_bytes.getvalue(),
            headers={"content-type": "image/png", "x-filename": "phase3-source.png"},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["source"]["width"] == 80
        assert uploaded.json()["source"]["height"] == 60
        assert uploaded.json()["project"]["animation"]["source_image"] == "assets/source.png"

        source_response = client.get(
            f"/api/animation/projects/{project_id}/source-image"
        )
        assert source_response.status_code == 200
        assert source_response.headers["content-type"].startswith("image/png")

        preview_project = client.get(
            f"/api/animation/projects/{project_id}"
        ).json()["project"]
        preview_project["animation"]["max_frames"] = 6
        preview_project["animation"]["width"] = 64
        preview_project["animation"]["height"] = 64
        preview_project["motion"]["zoom"] = "0:(1.0), 5:(1.02)"
        preview_project["motion"]["translation_x"] = "0:(0), 5:(2)"

        started = client.post(
            "/api/animation/motion-preview",
            json={"project": preview_project},
        )
        assert started.status_code == 202
        job_id = started.json()["id"]

        job = None
        for _ in range(100):
            job_response = client.get(f"/api/animation/motion-preview/{job_id}")
            assert job_response.status_code == 200
            job = job_response.json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        assert job is not None
        assert job["status"] == "completed", job
        assert job["result"]["source_frames"] == 6
        preview_image = client.get(job["url"])
        assert preview_image.status_code == 200
        assert preview_image.headers["content-type"].startswith("image/gif")

        bad_project = dict(loaded_project)
        bad_project["motion"] = dict(loaded_project["motion"])
        bad_project["motion"]["zoom"] = "0:(totally_not_math(t))"
        bad_validation = client.post(
            "/api/animation/validate-schedules",
            json={"project": bad_project},
        )
        assert bad_validation.status_code == 200
        assert bad_validation.json()["valid"] is False

        missing = client.get("/api/animation/projects/not-a-real-project")
        assert missing.status_code == 404


def test_animation_sampler_capabilities_are_model_specific() -> None:
    with TestClient(app) as client:
        response = client.get("/api/generation/capabilities")

    assert response.status_code == 200
    families = response.json()["families"]

    sdxl = {
        item["id"]
        for item in families["sdxl"]["samplers"]["options"]
    }
    assert {
        "euler",
        "euler_a",
        "dpmpp_2m",
        "dpmpp_2m_sde",
        "ddim",
        "lms",
        "heun",
        "unipc",
    } <= sdxl

    flux = {
        item["id"]
        for item in families["flux"]["samplers"]["options"]
    }
    zimage = {
        item["id"]
        for item in families["zimage"]["samplers"]["options"]
    }
    assert flux == {"flowmatch_euler"}
    assert zimage == {"flowmatch_euler"}

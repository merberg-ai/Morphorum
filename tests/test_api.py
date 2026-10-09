from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient
from PIL import Image

import morphorum.animation_depth as animation_depth
import morphorum.animation_motion as animation_motion
import morphorum.animation_projects as animation_projects
import morphorum.animation_render as animation_render
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
        assert 'id="view-loras"' in frontend.text
        assert 'id="lora-manager-family"' in frontend.text
        assert 'id="lora-manager-civitai"' in frontend.text
        assert 'id="lora-manager-refresh-runtime"' in frontend.text
        assert 'value="lora" checked' in frontend.text
        assert 'id="lora-manager-insert"' in frontend.text
        assert 'id="view-animation"' in frontend.text
        assert '<select id="animation-sampler"' in frontend.text
        assert 'id="animation-start-render"' in frontend.text
        assert 'id="animation-start-mode"' in frontend.text
        assert 'id="animation-mode"' in frontend.text
        assert 'id="animation-2d-motion-card"' in frontend.text
        assert 'id="animation-3d-camera-card"' in frontend.text
        assert 'id="animation-3d-translation-z"' in frontend.text
        assert 'id="animation-3d-rotation-y"' in frontend.text
        assert 'id="animation-3d-fov"' in frontend.text
        assert 'data-animation-mode="3d"' in frontend.text
        assert 'id="animation-model-load-progress"' in frontend.text
        assert 'id="animation-model-load-status"' in frontend.text
        assert 'id="animation-resume-render"' in frontend.text
        assert 'id="image-lora-select"' in frontend.text
        assert 'id="image-insert-lora"' in frontend.text
        assert 'id="resolved-loras"' in frontend.text
        assert 'id="animation-timeline-card"' in frontend.text
        assert 'id="animation-timeline-grid"' in frontend.text
        assert 'id="animation-timeline-add"' in frontend.text
        assert 'id="animation-timeline-apply"' in frontend.text
        assert 'id="animation-timeline-delete"' in frontend.text
        assert 'id="animation-timeline-track-select"' in frontend.text
        assert 'id="animation-timeline-scrubber"' in frontend.text
        assert 'id="animation-timeline-keyframe-list"' in frontend.text
        assert 'id="animation-collapse-all"' in frontend.text
        assert 'id="animation-expand-all"' in frontend.text
        assert 'id="animation-render-prompt-telemetry"' in frontend.text
        assert 'id="animation-render-positive-prompt"' in frontend.text
        assert 'id="animation-render-negative-prompt"' in frontend.text
        assert 'id="animation-render-frame-telemetry"' in frontend.text
        assert 'id="animation-render-state-cum-zoom"' in frontend.text
        assert 'id="animation-render-state-strength"' in frontend.text
        assert 'id="animation-render-state-seed"' in frontend.text
        assert 'id="animation-render-state-3d-z"' in frontend.text
        assert 'id="animation-render-state-3d-ry"' in frontend.text
        assert 'id="animation-render-state-depth"' in frontend.text
        assert 'id="animation-render-state-coverage"' in frontend.text
        assert 'id="animation-render-state-cadence"' in frontend.text
        assert 'id="animation-render-state-timing"' in frontend.text
        assert 'id="animation-cadence"' in frontend.text
        assert 'id="animation-3d-depth-resolution"' in frontend.text
        assert 'id="resolved-cadence"' in frontend.text
        assert 'value="cadence.diffusion"' in frontend.text
        assert 'id="resolved-3d-z"' in frontend.text
        assert 'id="resolved-3d-ry"' in frontend.text
        assert 'id="resolved-3d-fov"' in frontend.text
        assert 'value="camera_3d.translation_z"' in frontend.text
        assert 'value="camera_3d.fov"' in frontend.text
        assert 'id="animation-depth-card"' in frontend.text
        assert 'id="animation-depth-model"' in frontend.text
        assert 'id="animation-generate-depth"' in frontend.text
        assert 'id="animation-depth-preview"' in frontend.text
        assert 'id="copy-console-view"' in frontend.text
        assert 'id="copy-console-buffer"' in frontend.text
        assert "__MORPHORUM_ASSET_VERSION__" not in frontend.text
        assert f"/assets/app.css?v={asset_version}" in frontend.text
        assert f"/assets/app.js?v={asset_version}" in frontend.text
        assert f"/assets/animation.css?v={asset_version}" in frontend.text
        assert f"/assets/animation.js?v={asset_version}" in frontend.text
        assert f"/assets/loras.js?v={asset_version}" in frontend.text
        assert "no-cache" in frontend.headers.get("cache-control", "")

        css = client.get("/assets/app.css")
        assert css.status_code == 200
        assert "no-cache" in css.headers.get("cache-control", "")

        app_js = client.get("/assets/app.js")
        assert app_js.status_code == 200
        assert "health.git_branch" in app_js.text
        assert "health.git_commit" in app_js.text
        assert "API ready" in app_js.text

        animation_js = client.get("/assets/animation.js")
        assert animation_js.status_code == 200
        assert "morphorum.animation.cards.v1" in animation_js.text
        assert "current_prompt_state" in animation_js.text
        assert "current_frame_state" in animation_js.text
        assert "animation-render-state-cum-zoom" in animation_js.text
        assert "resolved.camera_3d?.translation_z" in animation_js.text
        assert "resolved.camera_3d?.fov" in animation_js.text
        assert "function animationMode()" in animation_js.text
        assert "syncAnimationModeUi" in animation_js.text
        assert "repairConstantGuidanceForSelectedModel" in animation_js.text
        assert "/api/animation/depth/models" in animation_js.text
        assert "generateDepthPreview" in animation_js.text
        assert "animation-timeline-keyframe-chip" in animation_js.text
        assert "animation-timeline-track-select" in animation_js.text
        assert "cadence.diffusion" in animation_js.text
        assert "animation-3d-depth-resolution" in animation_js.text
        assert "animation-render-state-timing" in animation_js.text


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

        # Checkpoint and LoRA source policies are independent.
        for family in ("sdxl", "flux", "zimage"):
            assert family in settings["models"]
        assert settings["models"]["zimage"]["loras"] == []
        assert "checkpoints" not in settings["models"]["zimage"]
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
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_FRAMES", 8)
    monkeypatch.setattr(
        animation_render,
        "get_model",
        lambda _model_id: {
            "id": "fake-model",
            "family": "sdxl",
            "variant": "sdxl",
            "kind": "checkpoints",
            "name": "Fake SDXL",
            "filename": "fake.safetensors",
            "path": "fake.safetensors",
            "extension": ".safetensors",
            "source": "external",
        },
    )

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

        render_project = dict(preview_project)
        render_project["animation"] = dict(preview_project["animation"])
        render_project["animation"]["max_frames"] = 4
        render_project["animation"]["start_mode"] = "source"
        render_project["model"] = {
            "model_id": "fake-model",
            "family": "sdxl",
            "variant": "sdxl",
        }
        render_project["motion"] = dict(preview_project["motion"])
        render_project["motion"]["zoom"] = "0:(1.0)"
        render_project["generation"] = dict(preview_project["generation"])
        render_project["generation"]["strength"] = "0:(1)"
        render_project["generation"]["steps"] = "0:(5)"
        render_project["generation"]["guidance"] = "0:(6)"
        render_project["generation"]["sampler"] = "euler"

        render_started = client.post(
            "/api/animation/renders",
            json={"project": render_project},
        )
        assert render_started.status_code == 202
        render_id = render_started.json()["id"]

        render_job = None
        for _ in range(120):
            response = client.get(f"/api/animation/renders/{render_id}")
            assert response.status_code == 200
            render_job = response.json()
            if render_job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.05)

        assert render_job is not None
        assert render_job["status"] == "completed", render_job
        assert len(render_job["results"]) == 4
        assert render_job["preview_url"]

        render_preview = client.get(render_job["preview_url"])
        assert render_preview.status_code == 200
        assert render_preview.headers["content-type"].startswith("image/gif")

        latest_frame = client.get(render_job["latest_frame_url"])
        assert latest_frame.status_code == 200
        assert latest_frame.headers["content-type"].startswith("image/png")

        render_history = client.get(
            f"/api/animation/projects/{project_id}/renders"
        )
        assert render_history.status_code == 200
        assert any(
            item["id"] == render_id
            for item in render_history.json()["renders"]
        )

        cleared = client.delete(
            f"/api/animation/projects/{project_id}/source-image"
        )
        assert cleared.status_code == 200
        assert cleared.json()["project"]["animation"]["source_image"] == ""
        missing_source = client.get(
            f"/api/animation/projects/{project_id}/source-image"
        )
        assert missing_source.status_code == 404

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


def test_animation_timeline_editing_api(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    with TestClient(app) as client:
        created = client.post(
            "/api/animation/projects",
            json={"name": "Timeline API"},
        )
        assert created.status_code == 201
        project_id = created.json()["project"]["id"]

        descriptors = client.get("/api/animation/timeline/descriptors")
        assert descriptors.status_code == 200
        descriptor_ids = {
            item["id"] for item in descriptors.json()["tracks"]
        }
        assert "prompts.positive" in descriptor_ids
        assert "camera_2d.zoom" in descriptor_ids

        timeline = client.get(
            f"/api/animation/projects/{project_id}/timeline"
        )
        assert timeline.status_code == 200
        assert timeline.json()["project_id"] == project_id
        assert timeline.json()["tracks"]["camera_2d"]["zoom"]["schedule"] == "0:(1.0)"

        prompt = client.put(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "prompts/positive/keyframes/12",
            json={"value": "neon city"},
        )
        assert prompt.status_code == 200
        assert prompt.json()["track"]["keyframes"][-1] == {
            "frame": 12,
            "value": "neon city",
        }

        zoom = client.put(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "camera_2d/zoom/keyframes/15",
            json={"value": "1.25"},
        )
        assert zoom.status_code == 200
        assert zoom.json()["track"]["schedule"] == "0:(1.0), 15:(1.25)"
        assert zoom.json()["project"]["motion"]["zoom"] == "0:(1.0), 15:(1.25)"

        moved = client.post(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "camera_2d/zoom/keyframes/15/move",
            json={"frame": 18},
        )
        assert moved.status_code == 200
        assert moved.json()["track"]["keyframes"][-1]["frame"] == 18
        assert moved.json()["track"]["keyframes"][-1]["frame_expression"] == "18"

        negative_mode = client.put(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "prompts/negative/interpolation",
            json={"interpolation": "hold"},
        )
        assert negative_mode.status_code == 200
        prompts = negative_mode.json()["project"]["tracks"]["prompts"]
        assert prompts["positive"]["interpolation"] == "blend"
        assert prompts["negative"]["interpolation"] == "hold"
        assert negative_mode.json()["project"]["animation"]["prompt_transition"] == "blend"

        track = client.get(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "camera_2d/zoom"
        )
        assert track.status_code == 200
        assert track.json()["descriptor"]["unit"] == "scale"
        assert track.json()["track"]["schedule"] == "0:(1.0), 18:(1.25)"

        project = client.get(
            f"/api/animation/projects/{project_id}"
        ).json()["project"]
        resolved = client.post(
            "/api/animation/resolve-timeline",
            json={
                "project": project,
                "start_frame": 0,
                "end_frame": 18,
                "step": 9,
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["count"] == 3
        assert [item["frame"] for item in resolved.json()["frames"]] == [0, 9, 18]
        assert resolved.json()["frames"][1]["motion"]["zoom"] > 1.0

        deleted = client.delete(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "camera_2d/zoom/keyframes/18"
        )
        assert deleted.status_code == 200
        assert deleted.json()["track"]["schedule"] == "0:(1.0)"

        protected = client.delete(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "prompts/positive/keyframes/0"
        )
        assert protected.status_code == 400
        assert "requires a frame 0" in protected.json()["detail"]

        unknown = client.get(
            f"/api/animation/projects/{project_id}/timeline/tracks/"
            "camera_3d/teleport"
        )
        assert unknown.status_code == 400


def test_animation_sampler_capabilities_are_model_specific() -> None:
    with TestClient(app) as client:
        response = client.get("/api/generation/capabilities")

    assert response.status_code == 200
    families = response.json()["families"]

    for family in ("sdxl", "flux", "zimage"):
        assert families[family]["tasks"]["txt2img"] is True
        assert families[family]["tasks"]["img2img"] is True

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

def test_lora_inspection_api_rejects_unindexed_file_and_requires_explicit_online_action(
    tmp_path, monkeypatch
) -> None:
    import importlib
    from safetensors.torch import save_file
    import torch
    module = importlib.import_module("morphorum.app")
    inspector = importlib.import_module("morphorum.lora_inspector")
    file = tmp_path / "trigger.safetensors"
    save_file({"unet.down_blocks.0.attn.to_q.lora_A.weight": torch.ones(2, 4)},
              str(file), metadata={"trigger_words": "marker"})
    record = {"id": "synthetic-id", "kind": "loras", "family": "sdxl",
              "name": "trigger", "path": str(file)}
    monkeypatch.setattr(module, "list_models", lambda **kwargs: [record])
    monkeypatch.setattr(inspector, "get_model", lambda model_id: record if model_id == "synthetic-id" else None)
    with TestClient(app) as client:
        library = client.get("/api/loras?family=sdxl")
        assert library.status_code == 200
        assert library.json()["loras"][0]["id"] == "synthetic-id"
        detail = client.get("/api/loras/synthetic-id/inspect")
        assert detail.status_code == 200
        assert detail.json()["trigger_words"] == ["marker"]

        missing = client.get("/api/loras/synthetic-id-absent/inspect")
        # The metadata route is indexed-id restricted, not an arbitrary path read.
        assert missing.status_code == 404

        calls = []
        monkeypatch.setattr(module, "lookup_civitai", lambda model_id: calls.append(model_id) or {
            "found": False, "message": "offline",
        })
        assert not calls
        lookup = client.post("/api/loras/synthetic-id/civitai-lookup")
        assert lookup.status_code == 200
        assert calls == ["synthetic-id"]

def test_lora_manager_server_audit_logs_and_validation(monkeypatch) -> None:
    import importlib
    from morphorum.console import snapshot

    module = importlib.import_module("morphorum.app")
    record = {
        "id": "audit-529922", "kind": "loras", "family": "sdxl",
        "name": "DonMCr33pyD0115XL_529922",
    }
    monkeypatch.setattr(
        module, "get_model",
        lambda model_id: record if model_id == "audit-529922" else None,
    )
    monkeypatch.setattr(
        module.generation_manager, "model_status",
        lambda: {
            "loaded": True, "model_name": "artUniverse", "family": "sdxl",
            "task": "txt2img",
            "loras": [{
                "id": record["id"], "adapter_name": "morphorum_audit",
                "compatibility": "unet-only",
                "diagnostics": {"modules": 12, "abs_sum": 42.25},
            }],
            "active_loras": [{"adapter_name": "morphorum_audit", "weight": 0.8}],
        },
    )
    events = snapshot(limit=1500)
    last_id = events[-1]["id"] if events else 0
    with TestClient(app) as client:
        audit = client.post("/api/loras/audit-529922/runtime-audit")
        assert audit.status_code == 200
        assert audit.json()["active_loras"][0]["weight"] == 0.8

        payload = {
            "event": "prompt_inserted", "weight": 0.85,
            "image_family": "sdxl", "trigger_count": 2,
        }
        ok = client.post("/api/loras/audit-529922/activity", json=payload)
        assert ok.status_code == 200
        assert ok.json()["status"] == "recorded"
        fail = client.post(
            "/api/loras/audit-529922/activity",
            json={**payload, "event": "prompt_rejected", "reason": "invalid_name"},
        )
        assert fail.status_code == 200
        assert client.post(
            "/api/loras/audit-529922/activity", json={**payload, "reason": "spoofed message"},
        ).status_code == 400
        assert client.post(
            "/api/loras/no-such-file/activity", json=payload,
        ).status_code == 404
        assert client.post(
            "/api/loras/audit-529922/activity",
            json={**payload, "weight": "nan"},
        ).status_code in (400, 422)

    lora_lines = [
        event for event in snapshot(after_id=last_id, limit=1500)
        if event["category"] == "lora"
    ]
    assert any("Runtime audit" in event["message"] and "12" in event["message"] for event in lora_lines)
    assert any("insertion succeeded" in event["message"] for event in lora_lines)
    assert any("insertion rejected" in event["message"] for event in lora_lines)
    assert any("DonMCr33pyD0115XL" in event["message"] for event in lora_lines)


def test_b53_3d_preview_api_forwards_red_overlay_to_manager(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path / "projects")
    seen = []

    def fake_start(*, project, source_path, highlight_holes=False):
        seen.append((project, source_path, highlight_holes))
        return {"id": "b53-preview-test", "status": "queued"}

    monkeypatch.setattr(animation_motion.motion_preview_manager, "start", fake_start)

    with TestClient(app) as client:
        created = client.post("/api/animation/projects", json={"name": "B5.3 API"})
        assert created.status_code == 201
        project_id = created.json()["project"]["id"]
        image_bytes = io.BytesIO()
        Image.new("RGB", (48, 32), "teal").save(image_bytes, format="PNG")
        uploaded = client.post(
            f"/api/animation/projects/{project_id}/source-image",
            content=image_bytes.getvalue(),
            headers={"content-type": "image/png", "x-filename": "ref.png"},
        )
        assert uploaded.status_code == 201
        project = uploaded.json()["project"]
        project["animation"]["mode"] = "3d"
        project["animation"]["max_frames"] = 12
        response = client.post(
            "/api/animation/motion-preview",
            json={"project": project, "options": {"highlight_holes": True}},
        )
        assert response.status_code == 202, response.text
        assert len(seen) == 1
        assert seen[0][0]["animation"]["mode"] == "3d"
        assert seen[0][2] is True
        assert seen[0][1].is_file()


def test_deforum_import_preview_and_create_routes(tmp_path, monkeypatch) -> None:
    import morphorum.app as app_module
    import morphorum.deforum_import as importer

    model = {
        "id": "model-1",
        "kind": "checkpoints",
        "family": "sdxl",
        "variant": "sdxl",
        "name": "Test SDXL",
        "filename": "test.safetensors",
        "path": str(tmp_path / "test.safetensors"),
    }
    monkeypatch.setattr(importer, "get_model", lambda _model_id: model)
    monkeypatch.setattr(
        importer,
        "validate_project_schedules",
        lambda project: {"valid": True, "issues": [], "fields": {}},
    )

    created = {}

    def fake_create(content, *, filename="", model_id=None, project_name=None):
        report = importer.preview_deforum_import(
            content,
            filename=filename,
            model_id=model_id,
            project_name=project_name,
        )
        project = dict(report["project"])
        project["id"] = "imported-project-1234"
        project["name"] = project_name or project["name"]
        created["project"] = project
        return project, report

    monkeypatch.setattr(app_module, "create_deforum_import", fake_create)

    source = json.dumps({
        "max_frames": 12,
        "animation_prompts": {"0": "legacy prompt"},
        "sampler": "Euler",
    })
    with TestClient(app) as client:
        preview = client.post(
            "/api/animation/import/deforum/preview",
            json={"content": source, "filename": "legacy.json", "model_id": "model-1"},
        )
        assert preview.status_code == 200
        assert preview.json()["project"]["animation"]["max_frames"] == 12
        assert preview.json()["project"]["generation"]["sampler"] == "euler"

        response = client.post(
            "/api/animation/import/deforum/create",
            json={
                "content": source,
                "filename": "legacy.json",
                "model_id": "model-1",
                "name": "Imported Legacy",
            },
        )
        assert response.status_code == 201
        assert response.json()["project"]["id"] == "imported-project-1234"
        assert response.json()["project"]["name"] == "Imported Legacy"
        assert response.json()["import"]["source_filename"] == "legacy.json"
        assert created["project"]["prompts"]["0"] == "legacy prompt"


def test_deforum_import_route_rejects_python_text() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/animation/import/deforum/preview",
            json={
                "content": "max_frames = 120",
                "filename": "legacy.txt",
            },
        )
    assert response.status_code == 400
    assert "not JSON-serialized" in response.json()["detail"]

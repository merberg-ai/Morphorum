from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import morphorum.animation_depth as animation_depth
import morphorum.animation_projects as animation_projects
from morphorum.app import app


def _png_bytes(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (48, 32), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_depth_preview_api_uses_project_source_and_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path / "projects")

    fake_preview = tmp_path / "depth.png"
    Image.new("L", (48, 32), 128).save(fake_preview, format="PNG")

    cache_key = "a" * 64
    fake_result = {
        "cache_version": 1,
        "cache_key": cache_key,
        "model_id": "depth-anything-v2-small",
        "model_label": "Depth Anything V2 Small",
        "repo_id": "depth-anything/Depth-Anything-V2-Small-hf",
        "depth_type": "relative",
        "device": "cuda",
        "width": 48,
        "height": 32,
        "raw_min": 0.25,
        "raw_max": 3.5,
        "normalized_min": 0.0,
        "normalized_max": 1.0,
        "convention": "relative inverse depth; larger values are nearer",
        "preview_convention": "white=near, black=far",
        "source_sha256": "b" * 64,
        "created_at": "2026-10-08T00:00:00+00:00",
        "cache_hit": False,
        "data_path": str(tmp_path / "depth.npz"),
        "preview_path": str(fake_preview),
        "metadata_path": str(tmp_path / "depth.json"),
    }
    calls = []

    def fake_estimate_path(path: Path, **kwargs):
        calls.append((path, kwargs))
        return dict(fake_result)

    monkeypatch.setattr(
        animation_depth.depth_manager,
        "estimate_path",
        fake_estimate_path,
    )
    monkeypatch.setattr(
        animation_depth.depth_manager,
        "cached",
        lambda value: dict(fake_result) if value == cache_key else None,
    )
    monkeypatch.setattr(
        animation_depth.depth_manager,
        "preview_path",
        lambda value: fake_preview if value == cache_key else Path("missing"),
    )

    with TestClient(app) as client:
        models = client.get("/api/animation/depth/models")
        assert models.status_code == 200
        assert models.json()["models"][0]["id"] == "depth-anything-v2-small"

        created = client.post(
            "/api/animation/projects",
            json={"name": "Depth API"},
        )
        assert created.status_code == 201
        project_id = created.json()["project"]["id"]

        missing_source = client.post(
            f"/api/animation/projects/{project_id}/depth-preview",
            json={"device": "cuda"},
        )
        assert missing_source.status_code == 400
        assert "Upload an animation source image" in missing_source.json()["detail"]

        uploaded = client.post(
            f"/api/animation/projects/{project_id}/source-image",
            content=_png_bytes("orange"),
            headers={"content-type": "image/png", "x-filename": "depth-source.png"},
        )
        assert uploaded.status_code == 201

        initial = client.get(
            f"/api/animation/projects/{project_id}/depth-preview/status"
        )
        assert initial.status_code == 200
        assert initial.json()["available"] is False

        generated = client.post(
            f"/api/animation/projects/{project_id}/depth-preview",
            json={
                "model_id": "depth-anything-v2-small",
                "device": "cuda",
                "force": False,
            },
        )
        assert generated.status_code == 200
        preview = generated.json()["preview"]
        assert preview["cache_key"] == cache_key
        assert preview["width"] == 48
        assert preview["height"] == 32
        assert preview["url"].endswith("/depth-preview/image?v=" + cache_key[:12])
        assert len(calls) == 1
        assert calls[0][1]["model_id"] == "depth-anything-v2-small"
        assert calls[0][1]["device"] == "cuda"
        assert calls[0][1]["force"] is False
        assert calls[0][1]["release_after"] is True

        status = client.get(
            f"/api/animation/projects/{project_id}/depth-preview/status"
        )
        assert status.status_code == 200
        assert status.json()["available"] is True
        assert status.json()["preview"]["cache_key"] == cache_key

        image = client.get(
            f"/api/animation/projects/{project_id}/depth-preview/image"
        )
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/png")

        recomputed = client.post(
            f"/api/animation/projects/{project_id}/depth-preview",
            json={
                "model_id": "depth-anything-v2-small",
                "device": "cpu",
                "force": True,
            },
        )
        assert recomputed.status_code == 200
        assert len(calls) == 2
        assert calls[1][1]["device"] == "cpu"
        assert calls[1][1]["force"] is True

        # Replacing the source invalidates the project preview pointer.
        replaced = client.post(
            f"/api/animation/projects/{project_id}/source-image",
            content=_png_bytes("blue"),
            headers={"content-type": "image/png", "x-filename": "replacement.png"},
        )
        assert replaced.status_code == 201
        invalidated = client.get(
            f"/api/animation/projects/{project_id}/depth-preview/status"
        )
        assert invalidated.status_code == 200
        assert invalidated.json()["available"] is False

        generated_again = client.post(
            f"/api/animation/projects/{project_id}/depth-preview",
            json={},
        )
        assert generated_again.status_code == 200

        cleared = client.delete(
            f"/api/animation/projects/{project_id}/depth-preview"
        )
        assert cleared.status_code == 200
        assert cleared.json()["status"] == "cleared"
        final_status = client.get(
            f"/api/animation/projects/{project_id}/depth-preview/status"
        )
        assert final_status.status_code == 200
        assert final_status.json()["available"] is False

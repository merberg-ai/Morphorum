from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

import morphorum.animation_depth as animation_depth
from morphorum.animation_depth import DepthManager


def test_depth_estimate_caches_numeric_data_and_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_depth, "CACHE_DIR", tmp_path / "cache")
    manager = DepthManager()
    calls = []

    def fake_inference(image, *, model_id, device):
        calls.append((image.size, model_id, device))
        manager._model = object()
        manager._processor = object()
        manager._loaded_model_id = model_id
        manager._device = "cpu"
        return np.array(
            [
                [0.0, 1.0, 2.0],
                [1.0, 2.0, 3.0],
            ],
            dtype=np.float32,
        ), "cpu"

    monkeypatch.setattr(manager, "_run_inference", fake_inference)
    image = Image.new("RGB", (3, 2), "white")

    first = manager.estimate(image, device="cpu")

    assert first["cache_hit"] is False
    assert first["model_id"] == "depth-anything-v2-small"
    assert first["width"] == 3
    assert first["height"] == 2
    assert first["raw_min"] == 0.0
    assert first["raw_max"] == 3.0
    assert first["normalized_min"] == 0.0
    assert first["normalized_max"] == 1.0
    assert first["preview_convention"] == "white=near, black=far"
    assert len(calls) == 1
    assert manager.status()["loaded"] is False

    data_path = Path(first["data_path"])
    preview_path = Path(first["preview_path"])
    metadata_path = Path(first["metadata_path"])
    assert data_path.is_file()
    assert preview_path.is_file()
    assert metadata_path.is_file()

    stored = np.load(data_path)
    assert stored["raw"].shape == (2, 3)
    assert stored["normalized"][0, 0] == 0.0
    assert stored["normalized"][-1, -1] == 1.0

    with Image.open(preview_path) as preview:
        assert preview.mode == "L"
        assert preview.size == (3, 2)
        assert preview.getpixel((0, 0)) == 0
        assert preview.getpixel((2, 1)) == 255

    second = manager.estimate(image, device="cpu")

    assert second["cache_hit"] is True
    assert second["cache_key"] == first["cache_key"]
    assert len(calls) == 1


def test_depth_force_recompute_bypasses_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_depth, "CACHE_DIR", tmp_path / "cache")
    manager = DepthManager()
    calls = 0

    def fake_inference(_image, *, model_id, device):
        nonlocal calls
        calls += 1
        return np.full((2, 2), float(calls), dtype=np.float32), "cpu"

    monkeypatch.setattr(manager, "_run_inference", fake_inference)
    image = Image.new("RGB", (2, 2), "black")

    first = manager.estimate(image, device="cpu")
    second = manager.estimate(image, device="cpu", force=True)

    assert first["cache_key"] == second["cache_key"]
    assert first["cache_hit"] is False
    assert second["cache_hit"] is False
    assert calls == 2


def test_depth_cache_key_changes_when_source_pixels_change(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_depth, "CACHE_DIR", tmp_path / "cache")
    manager = DepthManager()

    monkeypatch.setattr(
        manager,
        "_run_inference",
        lambda image, **_kwargs: (
            np.zeros((image.height, image.width), dtype=np.float32),
            "cpu",
        ),
    )

    black = manager.estimate(Image.new("RGB", (4, 4), "black"), device="cpu")
    white = manager.estimate(Image.new("RGB", (4, 4), "white"), device="cpu")

    assert black["cache_key"] != white["cache_key"]


def test_project_depth_manifest_round_trip(tmp_path) -> None:
    result = {
        "cache_key": "a" * 64,
        "model_id": "depth-anything-v2-small",
        "model_label": "Depth Anything V2 Small",
        "repo_id": "depth-anything/Depth-Anything-V2-Small-hf",
        "depth_type": "relative",
        "device": "cuda",
        "width": 320,
        "height": 240,
        "raw_min": 0.1,
        "raw_max": 4.2,
        "normalized_min": 0.0,
        "normalized_max": 1.0,
        "convention": "relative inverse depth; larger values are nearer",
        "preview_convention": "white=near, black=far",
        "source_sha256": "b" * 64,
        "created_at": "2026-10-08T00:00:00+00:00",
        "cache_hit": False,
    }

    path = animation_depth.save_project_depth_manifest(tmp_path, result)
    loaded = animation_depth.load_project_depth_manifest(tmp_path)

    assert path.is_file()
    assert loaded == result

    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["cache_key"] == "a" * 64

    animation_depth.clear_project_depth_manifest(tmp_path)
    assert animation_depth.load_project_depth_manifest(tmp_path) is None


def test_depth_model_catalog_uses_transformers_small_checkpoint() -> None:
    models = animation_depth.depth_model_catalog()

    assert len(models) == 1
    assert models[0]["id"] == "depth-anything-v2-small"
    assert models[0]["repo_id"] == "depth-anything/Depth-Anything-V2-Small-hf"
    assert models[0]["depth_type"] == "relative"
    assert models[0]["license"] == "apache-2.0"

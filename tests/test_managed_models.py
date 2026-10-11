from __future__ import annotations

import json

import morphorum.managed_models as managed_models


def _create_runtime_layout(root):
    (root / "scheduler").mkdir(parents=True)
    (root / "text_encoder").mkdir()
    (root / "tokenizer").mkdir()
    (root / "transformer").mkdir()
    (root / "vae").mkdir()
    (root / "model_index.json").write_text(
        json.dumps({"_class_name": "ZImagePipeline"}), encoding="utf-8"
    )
    for path in (
        "scheduler/scheduler_config.json",
        "text_encoder/config.json",
        "tokenizer/tokenizer.json",
        "tokenizer/tokenizer_config.json",
        "transformer/config.json",
        "vae/config.json",
    ):
        (root / path).write_text("{}", encoding="utf-8")
    (root / "vae" / "diffusion_pytorch_model.safetensors").write_bytes(b"vae")
    for folder, index_file, prefix in (
        ("text_encoder", "model.safetensors.index.json", "model"),
        ("transformer", "diffusion_pytorch_model.safetensors.index.json", "diffusion"),
    ):
        shards = [f"{prefix}-00001-of-00002.safetensors",
                  f"{prefix}-00002-of-00002.safetensors"]
        (root / folder / index_file).write_text(
            json.dumps({"weight_map": {"w1": shards[0], "w2": shards[1]}}),
            encoding="utf-8",
        )
        for shard in shards:
            (root / folder / shard).write_bytes(b"fake-weight-shard")


def test_runtime_folders_do_not_mean_managed_model_is_installed(tmp_path) -> None:
    destination = tmp_path / "Z-Image-Turbo"
    destination.mkdir()
    _create_runtime_layout(destination)

    assert managed_models.ManagedModelManager._runtime_layout_present(destination) is True
    assert managed_models.ManagedModelManager._installed(destination) is False


def test_completion_marker_is_required_and_verified(tmp_path) -> None:
    destination = tmp_path / "Z-Image-Turbo"
    destination.mkdir()
    _create_runtime_layout(destination)

    marker = destination / managed_models._COMPLETE_MARKER
    marker.write_text(
        json.dumps(
            {
                "status": "complete",
                "model_id": "zimage-turbo",
                "repo_id": "Tongyi-MAI/Z-Image-Turbo",
            }
        ),
        encoding="utf-8",
    )

    assert managed_models.ManagedModelManager._installed(destination) is True

    incomplete = destination / ".cache" / "huggingface" / "download" / "chunk.incomplete"
    incomplete.parent.mkdir(parents=True)
    incomplete.write_bytes(b"partial")

    assert managed_models.ManagedModelManager._installed(destination) is False


def test_status_does_not_expose_partial_package_as_installed(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "Z-Image-Turbo"
    destination.mkdir()
    _create_runtime_layout(destination)
    (destination / "transformer" / "partial.safetensors").write_bytes(b"partial")

    monkeypatch.setattr(
        managed_models,
        "managed_model_location",
        lambda family: tmp_path,
    )
    monkeypatch.setattr(
        managed_models.ManagedModelManager,
        "_migrate_legacy_completion",
        classmethod(lambda cls, entry, path: False),
    )

    manager = managed_models.ManagedModelManager()
    status = manager.status("zimage-turbo")

    assert status["installed"] is False
    assert status["status"] == "not_installed"


def test_zimage_requires_all_official_diffusers_weight_shards(tmp_path) -> None:
    root = tmp_path / "Z-Image-Turbo"
    _create_runtime_layout(root)
    assert managed_models.ManagedModelManager._runtime_layout_present(root)
    (root / "transformer" / "diffusion-00002-of-00002.safetensors").unlink()
    assert not managed_models.ManagedModelManager._runtime_layout_present(root)
    (root / "transformer" / "diffusion-00002-of-00002.safetensors").write_bytes(b"x")
    (root / "text_encoder" / "model-00001-of-00002.safetensors").write_bytes(b"")
    assert not managed_models.ManagedModelManager._runtime_layout_present(root)


def test_managed_package_rejects_wrong_pipeline_and_changed_completion_size(tmp_path) -> None:
    destination = tmp_path / "Z-Image-Turbo"
    _create_runtime_layout(destination)
    marker = destination / managed_models._COMPLETE_MARKER
    total = managed_models.ManagedModelManager._materialized_size(destination)
    marker.write_text(
        json.dumps({
            "status": "complete",
            "repo_id": "Tongyi-MAI/Z-Image-Turbo",
            "installed_bytes": total,
        }),
        encoding="utf-8",
    )
    assert managed_models.ManagedModelManager._installed(destination)
    marker.write_text(
        json.dumps({
            "status": "complete",
            "repo_id": "Tongyi-MAI/Z-Image-Turbo",
            "installed_bytes": total * 2,
        }),
        encoding="utf-8",
    )
    assert not managed_models.ManagedModelManager._installed(destination)
    marker.write_text(
        json.dumps({"status": "complete", "repo_id": "someone-else/z-image"}),
        encoding="utf-8",
    )
    assert not managed_models.ManagedModelManager._installed(destination)
    marker.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    (destination / "model_index.json").write_text(
        json.dumps({"_class_name": "AnotherPipeline"}), encoding="utf-8"
    )
    assert not managed_models.ManagedModelManager._installed(destination)


def test_catalog_single_official_turbo_package_supports_both_tasks() -> None:
    assert list(managed_models.MANAGED_MODEL_CATALOG) == ["zimage-turbo"]
    entry = managed_models.MANAGED_MODEL_CATALOG["zimage-turbo"]
    assert entry["repo_id"] == "Tongyi-MAI/Z-Image-Turbo"
    assert entry["variant"] == "turbo"
    assert "text-to-image and image-to-image" in entry["description"]
    assert not managed_models.ManagedModelManager._is_ignored(
        "transformer/diffusion_pytorch_model-00001-of-00003.safetensors"
    )
    assert not managed_models.ManagedModelManager._is_ignored(
        "text_encoder/model-00001-of-00003.safetensors"
    )
    assert managed_models.ManagedModelManager._is_ignored("assets/showcase.jpg")

from __future__ import annotations

import json

import morphorum.managed_models as managed_models


def _create_runtime_layout(root):
    (root / "scheduler").mkdir(parents=True)
    (root / "text_encoder").mkdir()
    (root / "tokenizer").mkdir()
    (root / "transformer").mkdir()
    (root / "vae").mkdir()
    (root / "model_index.json").write_text("{}", encoding="utf-8")


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

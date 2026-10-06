from __future__ import annotations

import morphorum.model_index as model_index
import morphorum.settings as settings_module
from morphorum.settings import save_settings


def test_model_scan_indexes_configured_files_and_deduplicates(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "config.yaml"
    index_db = tmp_path / "model-index.db"
    model_root = tmp_path / "models"
    nested = model_root / "SDXL"
    lora_root = tmp_path / "loras"
    nested.mkdir(parents=True)
    lora_root.mkdir()

    checkpoint = nested / "example-xl.safetensors"
    checkpoint.write_bytes(b"not-real-weights")
    (nested / "ignore-me.txt").write_text("ignore", encoding="utf-8")
    lora = lora_root / "detail-style.safetensors"
    lora.write_bytes(b"not-real-lora")

    monkeypatch.setattr(settings_module, "USER_CONFIG", user_config)
    monkeypatch.setattr(model_index, "MODEL_INDEX_DB", index_db)

    save_settings(
        {
            "models": {
                "sdxl": {
                    # Nested root intentionally overlaps the parent root.
                    "checkpoints": [str(model_root), str(nested)],
                    "loras": [str(lora_root)],
                }
            }
        }
    )

    result = model_index.scan_models()
    assert result["total"] == 2

    all_models = model_index.list_models(limit=100)
    assert len(all_models) == 2

    checkpoints = model_index.list_models(family="sdxl", kind="checkpoints")
    assert len(checkpoints) == 1
    assert checkpoints[0]["filename"] == checkpoint.name

    loras = model_index.list_models(family="sdxl", kind="loras")
    assert len(loras) == 1
    assert loras[0]["filename"] == lora.name

    detail = model_index.get_model(checkpoints[0]["id"])
    assert detail is not None
    assert detail["path"] == str(checkpoint)

    summary = model_index.model_summary()
    assert summary["total"] == 2
    assert summary["counts"]["sdxl"]["checkpoints"] == 1
    assert summary["counts"]["sdxl"]["loras"] == 1


def test_flux_scan_detects_dev_and_schnell_variants(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "config.yaml"
    index_db = tmp_path / "model-index.db"
    flux_root = tmp_path / "flux"
    flux_root.mkdir()

    dev = flux_root / "flux1-dev.safetensors"
    schnell = flux_root / "flux1-schnell-fp8.safetensors"
    dev.write_bytes(b"fake-dev")
    schnell.write_bytes(b"fake-schnell")

    monkeypatch.setattr(settings_module, "USER_CONFIG", user_config)
    monkeypatch.setattr(model_index, "MODEL_INDEX_DB", index_db)

    save_settings({"models": {"flux": {"checkpoints": [str(flux_root)], "loras": []}}})
    model_index.scan_models()

    indexed = model_index.list_models(family="flux", kind="checkpoints")
    variants = {item["filename"]: item["variant"] for item in indexed}
    assert variants[dev.name] == "dev"
    assert variants[schnell.name] == "schnell"


def test_external_scan_preserves_managed_model_entries(tmp_path, monkeypatch) -> None:
    user_config = tmp_path / "config.yaml"
    index_db = tmp_path / "model-index.db"
    external_root = tmp_path / "sdxl"
    managed_root = tmp_path / "z-image" / "Z-Image-Turbo"
    external_root.mkdir(parents=True)
    managed_root.mkdir(parents=True)

    checkpoint = external_root / "example-xl.safetensors"
    checkpoint.write_bytes(b"fake")
    (managed_root / "model_index.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(settings_module, "USER_CONFIG", user_config)
    monkeypatch.setattr(model_index, "MODEL_INDEX_DB", index_db)

    settings_module.save_settings(
        {
            "models": {
                "sdxl": {
                    "checkpoints": [str(external_root)],
                    "loras": [],
                }
            }
        }
    )

    model_index.upsert_managed_model(
        model_id="managed:zimage-turbo",
        family="zimage",
        name="Z-Image-Turbo",
        path=managed_root,
        variant="turbo",
        size_bytes=1234,
    )

    model_index.scan_models()

    managed = model_index.get_model("managed:zimage-turbo")
    assert managed is not None
    assert managed["source"] == "managed"
    assert managed["family"] == "zimage"

    external = model_index.list_models(family="sdxl", kind="checkpoints")
    assert len(external) == 1
    assert external[0]["source"] == "external"

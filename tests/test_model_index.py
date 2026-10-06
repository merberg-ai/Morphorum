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

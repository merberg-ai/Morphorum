"""MS6.2 host-folder wizard checks and safe persistence, no GPU required."""
from __future__ import annotations

import json
import struct

import pytest
from fastapi.testclient import TestClient

import morphorum.model_index as model_index
import morphorum.settings as settings
from morphorum.app import app
from morphorum.setup_folders import (
    SetupFolderConflict, SetupFolderError, inspect_folder, save_setup_folders,
)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "USER_CONFIG", tmp_path / "config.yaml")
    monkeypatch.setattr(model_index, "MODEL_INDEX_DB", tmp_path / "index.sqlite")
    monkeypatch.delenv("MORPHORUM_BACKEND_ONLY", raising=False)
    return tmp_path


def _save_models(sd, flux, expected_sd=None, expected_flux=None):
    return save_setup_folders(
        kind="checkpoints", paths={"sdxl":sd,"flux":flux},
        expected={"sdxl":expected_sd or [],"flux":expected_flux or []},
    )


def test_read_only_candidate_versus_indexed(isolated):
    folder = isolated / "SDXL"
    folder.mkdir()
    (folder / "example.safetensors").write_bytes(b"fake; never loaded")
    checked = inspect_folder(family="sdxl", kind="checkpoints", path=str(folder))
    assert checked["status"] == "candidates"
    assert checked["candidates"] == 1 and checked["indexed"] == 0
    assert not settings.USER_CONFIG.exists(), "Folder checking must not save settings"
    assert not model_index.MODEL_INDEX_DB.exists() or not model_index.list_models()
    saved = _save_models([str(folder)],[])
    assert saved["paths"]["sdxl"] == [str(folder)]
    assert model_index.scan_models()["total"] == 1
    rescanned = inspect_folder(family="sdxl", kind="checkpoints", path=str(folder))
    assert rescanned["status"] == "indexed"
    assert rescanned["indexed"] == 1
    assert "loadability" in rescanned["message"]


def test_wrong_family_and_bounded_inspection(isolated):
    folder = isolated / "bad_family"
    folder.mkdir()
    # Filename hint only, not runtime proof.
    (folder / "flux1-dev.safetensors").write_bytes(b"fake")
    result = inspect_folder(family="sdxl", kind="checkpoints", path=str(folder))
    assert result["status"] == "incompatible"
    assert result["wrong_family"] == 1
    assert result["candidates"] == 0
    for index in range(1510):
        (folder / ("noise%04d.txt" % index)).write_bytes(b"x")
    limited = inspect_folder(family="sdxl", kind="checkpoints", path=str(folder))
    assert limited["truncated"] is True
    assert limited["inspected_entries"] <= 1501


def test_safetensors_header_hint_and_unknown_models_are_not_declared_loadable(isolated):
    folder = isolated / "mixed"
    folder.mkdir()
    header = json.dumps({
        "__metadata__":{"ss_base_model_version":"sdxl_base_v1"},
        "lora_unet_test": {"dtype":"F16","shape":[1],"data_offsets":[0,2]},
    }).encode()
    (folder / "style.safetensors").write_bytes(struct.pack("<Q",len(header))+header+b"\x00\x00")
    result = inspect_folder(family="flux", kind="loras", path=str(folder))
    assert result["status"] == "incompatible"
    assert result["wrong_family"] == 1
    assert "runtime" not in result.get("verified", "").lower()


def test_invalid_and_unsupported_folders_refused(isolated):
    missing = isolated / "missing"
    result = inspect_folder(family="flux", kind="checkpoints", path=str(missing))
    assert result["status"] == "invalid"
    assert not result["exists"]
    file = isolated / "file.txt"
    file.write_text("not a folder")
    assert inspect_folder(family="sdxl",kind="checkpoints",path=str(file))["status"] == "invalid"
    with pytest.raises(SetupFolderError):
        inspect_folder(family="zimage", kind="checkpoints", path=str(isolated))
    with pytest.raises(SetupFolderError):
        _save_models([str(missing)], [])


def test_save_preserves_unrelated_settings_and_rejects_races(isolated):
    checkpoints = isolated / "SDXL"
    loras = isolated / "LoRAs"
    checkpoints.mkdir()
    loras.mkdir()
    settings.save_settings({
        "models":{"sdxl":{"checkpoints":[str(checkpoints)],"loras":[str(loras)]}},
        "ui":{"theme":"deep-ocean"},
    })
    before = settings.USER_CONFIG.read_bytes()
    with pytest.raises(SetupFolderConflict):
        _save_models([], [], expected_sd=[], expected_flux=[])
    assert settings.USER_CONFIG.read_bytes() == before
    with pytest.raises(SetupFolderError):
        save_setup_folders(
            kind="loras",paths={"sdxl":[str(loras),str(loras)],"flux":[],"zimage":[]},
            expected={"sdxl":[str(loras)],"flux":[],"zimage":[]},
        )
    result = _save_models([], [], expected_sd=[str(checkpoints)])
    assert result["paths"]["sdxl"] == []
    after = settings.load_settings()
    assert after["models"]["sdxl"]["loras"] == [str(loras)]
    assert after["ui"]["theme"] == "deep-ocean"


def test_page_routes_require_same_origin_explicit_action(isolated):
    folder = isolated / "SDXL"
    folder.mkdir()
    payload = {"family":"sdxl","kind":"checkpoints","path":str(folder)}
    with TestClient(app) as client:
        missing_header = client.post("/api/setup/folders/check",json=payload)
        assert missing_header.status_code == 403
        cross_site = client.post("/api/setup/folders/check",json=payload,
            headers={"X-Morphorum-Setup":"1","Origin":"https://evil.example"})
        assert cross_site.status_code == 403
        response = client.post("/api/setup/folders/check",json=payload,
            headers={"X-Morphorum-Setup":"1"})
        assert response.status_code == 200
        assert response.json()["status"] == "empty"
        denied = client.post("/api/setup/folders/save",json={
            "kind":"checkpoints","paths":{"sdxl":[],"flux":[]},
            "expected":{"sdxl":[],"flux":[]},
        })
        assert denied.status_code == 403
        assert not settings.USER_CONFIG.exists()

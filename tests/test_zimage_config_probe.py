"""Z2.20b read-only configuration inspection tests."""
import json
from unittest.mock import patch

from morphorum.zimage_config_probe import probe_configuration


def _fixture(tmp_path):
    managed = tmp_path / "managed"
    scratch = [tmp_path / "transformer_scratch", tmp_path / "encoder_scratch"]
    for path in scratch:
        path.mkdir()
    names = ("transformer", "text_encoder", "tokenizer", "vae", "scheduler")
    configs = {"tokenizer": "tokenizer_config.json", "scheduler": "scheduler_config.json"}
    for name in names:
        folder = managed / name
        folder.mkdir(parents=True)
        (folder / configs.get(name, "config.json")).write_text(json.dumps({"_class_name": name}))
    (managed / "model_index.json").write_text(json.dumps({name: ["library", name] for name in names}))
    for path, family, filename in zip(scratch, ("transformer", "encoder"), ("diffusion_pytorch_model.safetensors", "model.safetensors")):
        (path / filename).write_bytes(b"test")
        (path / "manifest.json").write_text(json.dumps({
            "family": family, "output_file": filename, "output_bytes": 4,
            "loadable": False, "runtime_verified": False, "ready": False,
            "conversion_enabled": False,
        }))
    return *scratch, managed


def test_success_is_unverified_and_never_initializes(tmp_path):
    transformer, encoder, managed = _fixture(tmp_path)
    with patch("morphorum.zimage_config_probe._load_header", return_value=(
        {"weight": {"shape": [2, 2], "dtype": "BF16"}}, 0
    )), patch("morphorum.zimage_config_probe.read_managed_component_schema",
              return_value={"weight": (2, 2)}):
        result = probe_configuration(transformer, encoder, managed)
    assert result["status"] == "config_shape_candidate_unverified"
    assert result["loadable"] is False and result["model_initialized"] is False
    assert result["transformer_tensor_count"] == 1 and result["encoder_tensor_count"] == 1


def test_wrong_family_manifest_blocks(tmp_path):
    transformer, encoder, managed = _fixture(tmp_path)
    path = transformer / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["family"] = "encoder"
    path.write_text(json.dumps(manifest))
    assert probe_configuration(transformer, encoder, managed)["status"] == "blocked"


def test_missing_scheduler_config_blocks(tmp_path):
    transformer, encoder, managed = _fixture(tmp_path)
    (managed / "scheduler" / "scheduler_config.json").unlink()
    assert probe_configuration(transformer, encoder, managed)["status"] == "blocked"


def test_mismatched_shape_blocks(tmp_path):
    transformer, encoder, managed = _fixture(tmp_path)
    with patch("morphorum.zimage_config_probe._load_header", return_value=(
        {"weight": {"shape": [3, 2], "dtype": "BF16"}}, 0
    )), patch("morphorum.zimage_config_probe.read_managed_component_schema",
              return_value={"weight": (2, 2)}):
        assert probe_configuration(transformer, encoder, managed)["status"] == "blocked"

"""Z2.20a preflight safety and memory budgeting tests."""
import json
from unittest.mock import patch

from morphorum.zimage_inference_preflight import plan_experimental_inference


def setup_artifacts(tmp_path):
    managed = tmp_path / "managed"
    for name in ("tokenizer", "vae", "scheduler"):
        (managed / name).mkdir(parents=True)
    folders = []
    for family, filename in (("transformer", "diffusion_pytorch_model.safetensors"), ("encoder", "model.safetensors")):
        folder = tmp_path / family
        folder.mkdir()
        (folder / filename).write_bytes(b"12345678")
        (folder / "manifest.json").write_text(json.dumps({
            "kind": "z218_experimental_nonloadable_bf16_conversion",
            "family": family, "output_file": filename, "output_bytes": 8,
            "ready": False, "loadable": False, "runtime_verified": False,
            "conversion_enabled": False,
        }), encoding="utf-8")
        folders.append(folder)
    return *folders, managed


def test_capacity_preflight_is_always_nonloadable(tmp_path):
    transformer, encoder, managed = setup_artifacts(tmp_path)
    with patch("morphorum.zimage_inference_preflight.verify_fp8_stream_artifact",
               return_value={"status": "verified_nonloadable"}) as verifier:
        result = plan_experimental_inference(
            transformer, encoder, managed_root=managed, ram_gib=64, vram_gib=16)
    assert verifier.call_count == 2
    assert result["status"] == "capacity_candidate_unverified"
    assert result["loadable"] is False
    assert result["runtime_verified"] is False
    assert result["inference_attempted"] is False
    assert result["artifact_hashes_checked"] is True


def test_manifest_authorization_flag_rejected(tmp_path):
    transformer, encoder, managed = setup_artifacts(tmp_path)
    file = transformer / "manifest.json"
    data = json.loads(file.read_text())
    data["loadable"] = True
    file.write_text(json.dumps(data))
    result = plan_experimental_inference(transformer, encoder, managed_root=managed,
                                          ram_gib=64, vram_gib=16, verify_hashes=False)
    assert result["status"] == "blocked"


def test_artifact_mismatch_rejected(tmp_path):
    transformer, encoder, managed = setup_artifacts(tmp_path)
    (encoder / "model.safetensors").write_bytes(b"short")
    result = plan_experimental_inference(transformer, encoder, managed_root=managed,
                                          ram_gib=64, vram_gib=16, verify_hashes=False)
    assert result["status"] == "blocked"


def test_overlap_and_nonfinite_budget_rejected(tmp_path):
    transformer, encoder, managed = setup_artifacts(tmp_path)
    overlap = plan_experimental_inference(transformer, transformer, managed_root=managed,
                                            ram_gib=64, vram_gib=16, verify_hashes=False)
    assert overlap["status"] == "blocked"
    invalid = plan_experimental_inference(transformer, encoder, managed_root=managed,
                                            ram_gib=float("nan"), vram_gib=16, verify_hashes=False)
    assert invalid["status"] == "blocked"


def test_no_unintended_hash_scan(tmp_path):
    transformer, encoder, managed = setup_artifacts(tmp_path)
    with patch("morphorum.zimage_inference_preflight.verify_fp8_stream_artifact") as verifier:
        result = plan_experimental_inference(
            transformer, encoder, managed_root=managed, ram_gib=64, vram_gib=16,
            verify_hashes=False)
    verifier.assert_not_called()
    assert result["artifact_hashes_checked"] is False


def test_missing_managed_component_rejected(tmp_path):
    transformer, encoder, managed = setup_artifacts(tmp_path)
    (managed / "vae").rmdir()
    result = plan_experimental_inference(transformer, encoder, managed_root=managed,
                                          ram_gib=64, vram_gib=16, verify_hashes=False)
    assert result["status"] == "blocked"

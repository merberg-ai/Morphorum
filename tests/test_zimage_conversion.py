import json
import struct

import pytest

from morphorum.zimage_conversion import ConversionPreflightError, plan_conversion, stage_verified_tensor_copy, plan_original_tensor_mapping


def checkpoint(path, dtype="F16", missing=False):
    names = ["x_embedder.weight", "final_layer.weight", "cap_embedder.weight",
             "noise_refiner.0.weight", "context_refiner.0.weight", "layers.0.weight"]
    if missing:
        names.pop()
    header = {}
    width = 1 if dtype.startswith("F8_") else 2
    for i, name in enumerate(names):
        header["model.diffusion_model." + name] = {
            "dtype": dtype, "shape": [1], "data_offsets": [i*width, (i+1)*width]
        }
    blob = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(blob)) + blob + b"a"*(len(names)*width))


def test_conversion_plans_isolated_cache_without_writes(tmp_path):
    file = tmp_path / "checkpoint.safetensors"
    cache = tmp_path / "cache"
    checkpoint(file)
    result = plan_conversion(file, cache)
    assert result["strategy"] == "convert_original_to_diffusers"
    assert result["cache_destination"].startswith(str(cache))
    assert result["conversion_enabled"] is False
    assert result["loadable"] is False and result["ready"] is False
    assert not cache.exists()
    assert plan_conversion(file, cache)["cache_key"] == result["cache_key"]


def test_modified_file_changes_cache_identity(tmp_path):
    file = tmp_path / "checkpoint.safetensors"
    checkpoint(file)
    before = plan_conversion(file, tmp_path / "cache")
    checkpoint(file)
    import os
    stat = file.stat()
    os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
    after = plan_conversion(file, tmp_path / "cache")
    assert before["cache_key"] != after["cache_key"]


def test_fp8_and_incomplete_files_rejected(tmp_path):
    file = tmp_path / "checkpoint.safetensors"
    checkpoint(file, "F8_E4M3FN")
    with pytest.raises(ConversionPreflightError, match="FP8"):
        plan_conversion(file, tmp_path / "cache")
    checkpoint(file, missing=True)
    with pytest.raises(ConversionPreflightError, match="unverified"):
        plan_conversion(file, tmp_path / "cache")


def test_source_parent_as_cache_rejected(tmp_path):
    file = tmp_path / "checkpoint.safetensors"
    checkpoint(file)
    with pytest.raises(ConversionPreflightError, match="ancestor"):
        plan_conversion(file, tmp_path)


def test_z26_atomic_schema_gated_staging(tmp_path):
    file = tmp_path / "weights.safetensors"
    names = ["all_x_embedder.weight", "all_final_layer.weight", "cap_embedder.weight",
             "noise_refiner.0.weight", "context_refiner.0.weight", "layers.0.weight"]
    header = {name: {"dtype": "F16", "shape": [1], "data_offsets": [2*i, 2*i+2]}
              for i, name in enumerate(names)}
    raw = json.dumps(header).encode("utf-8")
    file.write_bytes(struct.pack("<Q", len(raw)) + raw + b"ab"*len(names))
    root = tmp_path / "cache"
    with pytest.raises(ConversionPreflightError, match="exactly match"):
        stage_verified_tensor_copy(file, root, expected_tensor_shapes={names[0]: (1,)})
    assert not list(root.rglob("*.safetensors"))
    result = stage_verified_tensor_copy(
        file, root, expected_tensor_shapes={key: (1,) for key in names}
    )
    assert result["loadable"] is False
    assert result["ready"] is False
    assert (tmp_path / "cache" / "standalone-zimage" / result["cache_key"] /
            "diffusion_pytorch_model.safetensors").read_bytes() == file.read_bytes()
    with pytest.raises(ConversionPreflightError, match="already exists"):
        stage_verified_tensor_copy(file, root, expected_tensor_shapes={key: (1,) for key in names})


def test_z26_refuses_original_layout_even_with_supplied_schema(tmp_path):
    file = tmp_path / "checkpoint.safetensors"
    checkpoint(file)
    with pytest.raises(ConversionPreflightError, match="not yet verified"):
        stage_verified_tensor_copy(file, tmp_path / "cache", expected_tensor_shapes={"x": (1,)})


def test_z27_mapping_renames_and_splits_qkv():
    source = {
        "model.diffusion_model.x_embedder.weight": (4, 2),
        "model.diffusion_model.layers.0.attention.qkv.weight": (12, 4),
        "model.diffusion_model.layers.0.attention.out.weight": (4, 4),
        "model.diffusion_model.norm_final.weight": (4,),
    }
    target = {
        "all_x_embedder.2-1.weight": (4, 2),
        **{f"layers.0.attention.to_{p}.weight": (4, 4) for p in ("q", "k", "v")},
        "layers.0.attention.to_out.0.weight": (4, 4),
    }
    result = plan_original_tensor_mapping(source, target)
    assert result["tensor_count"] == 5
    assert not result["loadable"]
    assert any(op["action"] == "split_qkv" for op in result["operations"])
    with pytest.raises(ConversionPreflightError, match="exactly match"):
        plan_original_tensor_mapping(source, {"not_a_real_tensor": (1,)})


def test_z27_mapping_rejects_invalid_fused_qkv():
    with pytest.raises(ConversionPreflightError, match="divisible by 3"):
        plan_original_tensor_mapping(
            {"layers.0.attention.qkv.weight": (10, 2)},
            {"layers.0.attention.to_q.weight": (3, 2)},
        )


def test_z27_staging_manifest_contains_matching_hashes(tmp_path):
    import hashlib
    file = tmp_path / "weights.safetensors"
    names = ["all_x_embedder.weight", "all_final_layer.weight", "cap_embedder.weight",
             "noise_refiner.0.weight", "context_refiner.0.weight", "layers.0.weight"]
    fields = {key: {"dtype": "F16", "shape": [1], "data_offsets": [2*i, 2*i+2]}
              for i, key in enumerate(names)}
    h = json.dumps(fields).encode()
    file.write_bytes(struct.pack("<Q", len(h)) + h + b"ab"*len(fields))
    plan = stage_verified_tensor_copy(file, tmp_path / "cache",
                                      expected_tensor_shapes={k: (1,) for k in names})
    manifest = json.loads((tmp_path / "cache" / "standalone-zimage" / plan["cache_key"] /
                           "manifest.json").read_text())
    assert manifest["source_sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
    assert manifest["source_sha256"] == manifest["staged_sha256"]
    assert not manifest["loadable"]

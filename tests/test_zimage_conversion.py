import json
import struct

import pytest

from morphorum.zimage_conversion import ConversionPreflightError, plan_conversion, stage_verified_tensor_copy, plan_original_tensor_mapping, convert_original_checkpoint


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


def test_z28_streaming_original_conversion_with_qkv(tmp_path):
    source = tmp_path / "original.safetensors"
    tensors = {
        "model.diffusion_model.x_embedder.weight": ((2,), b"ab"),
        "model.diffusion_model.final_layer.weight": ((2,), b"cd"),
        "model.diffusion_model.cap_embedder.weight": ((2,), b"ef"),
        "model.diffusion_model.noise_refiner.0.weight": ((2,), b"gh"),
        "model.diffusion_model.context_refiner.0.weight": ((2,), b"ij"),
        "model.diffusion_model.layers.0.attention.qkv.weight": ((6, 2), b"abcdefghijkl"),
    }
    fields = {}
    payload = bytearray()
    for name, (shape, data) in tensors.items():
        start = len(payload)
        payload.extend(data)
        fields[name] = {"dtype": "U8", "shape": list(shape),
                        "data_offsets": [start, len(payload)]}
    # Conversion preflight intentionally rejects U8; use F16 for real path.
    fields = {}
    payload = bytearray()
    for name, (_, data) in tensors.items():
        # 2-byte F16 elements. Fused QKV is [6, 1].
        shape = [6, 1] if "qkv" in name else [1]
        start = len(payload)
        payload.extend(data)
        fields[name] = {"dtype": "F16", "shape": shape,
                        "data_offsets": [start, len(payload)]}
    h = json.dumps(fields).encode()
    source.write_bytes(struct.pack("<Q", len(h)) + h + payload)
    expected = {
        "all_x_embedder.2-1.weight": (1,),
        "all_final_layer.2-1.weight": (1,),
        "cap_embedder.weight": (1,),
        "noise_refiner.0.weight": (1,),
        "context_refiner.0.weight": (1,),
        **{f"layers.0.attention.to_{part}.weight": (2, 1) for part in ("q", "k", "v")},
    }
    root = tmp_path / "converted-cache"
    result = convert_original_checkpoint(source, root, expected_output_shapes=expected)
    assert not result["ready"] and not result["loadable"]
    target = root / "standalone-zimage" / result["cache_key"] / "diffusion_pytorch_model.safetensors"
    with target.open("rb") as handle:
        count = struct.unpack("<Q", handle.read(8))[0]
        out_header = json.loads(handle.read(count))
        out_payload = handle.read()
    assert set(out_header) == set(expected)
    parts = []
    for key in [f"layers.0.attention.to_{p}.weight" for p in ("q", "k", "v")]:
        a, b = out_header[key]["data_offsets"]
        parts.append(out_payload[a:b])
    assert parts == [b"abcd", b"efgh", b"ijkl"]
    import hashlib
    manifest = json.loads(target.with_name("manifest.json").read_text())
    assert manifest["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["output_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(ConversionPreflightError, match="already exists"):
        convert_original_checkpoint(source, root, expected_output_shapes=expected)


def test_z28_bad_mapping_never_publishes_cache(tmp_path):
    source = tmp_path / "original.safetensors"
    checkpoint(source)
    root = tmp_path / "cache"
    with pytest.raises(ConversionPreflightError, match="exactly match"):
        convert_original_checkpoint(source, root, expected_output_shapes={"fake": (1,)})
    assert not list(root.rglob("*.safetensors"))

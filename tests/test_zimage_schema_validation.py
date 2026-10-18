"""Z2.17 header-only, complete transformer and Qwen schema validation."""
from __future__ import annotations

import json
import struct

import pytest

from morphorum.zimage_schema_validation import (
    SchemaInspectionError, compare_tensor_schemas, read_managed_component_schema,
    validate_complete_tensor_schema,
)


def _safetensors(path, entries):
    """Write a tiny but structurally valid safetensors file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {}
    payload = bytearray()
    sizes = {"F8_E4M3": 1, "BF16": 2, "F32": 4}
    for name, (dtype, shape, value) in entries.items():
        first = len(payload)
        length = sizes[dtype]
        for dimension in shape:
            length *= dimension
        if dtype == "F32":
            values = struct.pack("<f", value)
        elif dtype == "BF16" and value == 1.0:
            values = struct.pack("<H", 0x3F80) * (length // 2)
        else:
            values = bytes([0x38 if dtype == "F8_E4M3" else 0] * length)
        assert len(values) == length
        payload.extend(values)
        header[name] = {"dtype": dtype, "shape": list(shape),
                        "data_offsets": [first, len(payload)]}
    h = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(h)) + h + payload)
    return path


def _managed(root, family, expected, *, shard_filename="weights-00001-of-00001.safetensors"):
    name = "transformer" if family == "transformer" else "text_encoder"
    index = ("diffusion_pytorch_model.safetensors.index.json" if
             family == "transformer" else "model.safetensors.index.json")
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    _safetensors(directory / shard_filename, {
        key: ("BF16", shape, 0) for key, shape in expected.items()
    })
    (directory / index).write_text(json.dumps({
        "metadata": {"total_size": sum(
            2 * __import__("math").prod(shape) for shape in expected.values()
        )},
        "weight_map": {key: shard_filename for key in expected},
    }))


def _original_transformer(tmp_path):
    source = tmp_path / "external" / "transformer.safetensors"
    weights = {
        "x_embedder.weight": (4,),
        "final_layer.weight": (4,),
        "cap_embedder.0.weight": (4,),
        "noise_refiner.0.weight": (4,),
        "context_refiner.0.weight": (4,),
        "layers.0.attention.qkv.weight": (6, 4),
    }
    entries = {}
    for name, shape in weights.items():
        entries[name] = ("F8_E4M3", shape, 0)
        entries[name[:-len(".weight")] + ".scale_weight"] = ("F32", (1,), 2.0)
    entries["scaled_fp8"] = ("F8_E4M3", (2,), 0)
    _safetensors(source, entries)
    expected = {
        "all_x_embedder.2-1.weight": (4,),
        "all_final_layer.2-1.weight": (4,),
        "cap_embedder.0.weight": (4,),
        "noise_refiner.0.weight": (4,),
        "context_refiner.0.weight": (4,),
        "layers.0.attention.to_q.weight": (2, 4),
        "layers.0.attention.to_k.weight": (2, 4),
        "layers.0.attention.to_v.weight": (2, 4),
    }
    return source, expected


def _encoder(tmp_path):
    source = tmp_path / "external" / "qwen.safetensors"
    weights = {
        "model.embed_tokens.weight": (8, 4),
        "model.layers.0.self_attn.q_proj.weight": (8, 4),
        "model.layers.0.mlp.gate_proj.weight": (8, 4),
    }
    entries = {"model.embed_tokens.weight": ("BF16", (8, 4), 0)}
    for name in list(weights)[1:]:
        entries[name] = ("F8_E4M3", weights[name], 0)
        entries[name[:-len(".weight")] + ".scale_weight"] = ("F32", (1,), 2.0)
        entries[name[:-len(".weight")] + ".scale_input"] = ("BF16", (1,), 1.0)
    entries["scaled_fp8"] = ("F8_E4M3", (0,), 0)
    _safetensors(source, entries)
    return source, weights


def test_z217_transformer_exact_sharded_schema_matches_without_writes(tmp_path):
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    root = tmp_path / "managed"
    _managed(root, "transformer", expected)
    original = source.read_bytes()
    weights = (root / "transformer" / "weights-00001-of-00001.safetensors").read_bytes()
    result = validate_complete_tensor_schema(source, root, family="transformer")
    assert result["status"] == "schema_matches", result
    assert result["schema_verified"] is True
    assert result["mapped_tensor_count"] == len(expected)
    assert result["fused_qkv_splits"] == 1
    assert result["source_parameter_count"] == 6
    assert not result["loadable"] and not result["conversion_enabled"]
    assert source.read_bytes() == original
    assert (root / "transformer" / "weights-00001-of-00001.safetensors").read_bytes() == weights


def test_z217_separate_qwen_encoder_exact_schema(tmp_path):
    pytest.importorskip("torch")
    source, expected = _encoder(tmp_path)
    root = tmp_path / "managed"
    _managed(root, "encoder", expected)
    result = validate_complete_tensor_schema(source, root, family="encoder")
    assert result["status"] == "schema_matches", result
    assert result["source_parameter_count"] == 3
    assert result["fused_qkv_splits"] == 0
    assert result["discarded_unit_input_scale_count"] == 2
    assert result["excluded_input_scale_count"] == 2
    assert result["input_scale_metadata"]["nonunit_count"] == 0
    assert result["schema_verified"] is True
    assert result["loadable"] is False


def test_z217_full_reference_comparison_lists_exact_missing_extra_and_shapes():
    result = compare_tensor_schemas(
        {"a": (2, 2), "unexpected": (1,)},
        {"a": (4, 2), "missing": (1,)},
    )
    assert result["status"] == "schema_mismatch"
    assert result["missing_reference_tensors"] == 1
    assert result["unexpected_external_tensors"] == 1
    assert result["shape_mismatches"] == 1
    assert result["shape_mismatch_examples"][0]["name"] == "a"
    assert result["schema_verified"] is False
    assert result["loadable"] is False


def test_z217_incorrect_reference_detected_without_writing(tmp_path):
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    root = tmp_path / "managed"
    corrupted = dict(expected)
    corrupted["all_final_layer.2-1.weight"] = (5,)
    _managed(root, "transformer", corrupted)
    result = validate_complete_tensor_schema(source, root, family="transformer")
    assert result["status"] == "schema_mismatch"
    assert result["shape_mismatches"] == 1
    assert not result["schema_verified"]
    assert not result["loadable"]


def test_z217_missing_index_remains_blocked(tmp_path):
    pytest.importorskip("torch")
    source, _ = _original_transformer(tmp_path)
    result = validate_complete_tensor_schema(source, tmp_path / "missing", family="transformer")
    assert result["status"] == "blocked"
    assert result["schema_verified"] is False
    assert not (tmp_path / "missing").exists()


def test_z217_rejects_index_reference_to_untrusted_shard(tmp_path):
    root = tmp_path / "managed"
    directory = root / "transformer"
    directory.mkdir(parents=True)
    (directory / "diffusion_pytorch_model.safetensors.index.json").write_text(json.dumps({
        "weight_map": {"a": "../escape.safetensors"},
    }))
    with pytest.raises(SchemaInspectionError, match="filename"):
        read_managed_component_schema(root, "transformer")


def test_z217_rejects_unindexed_extra_tensor_in_managed_shard(tmp_path):
    root = tmp_path / "managed"
    _managed(root, "transformer", {"a": (2,)})
    index = root / "transformer" / "diffusion_pytorch_model.safetensors.index.json"
    index.write_text(json.dumps({"weight_map": {"nonexistent": "weights-00001-of-00001.safetensors"}}))
    with pytest.raises(SchemaInspectionError, match="unindexed"):
        read_managed_component_schema(root, "transformer")


def test_z2172_nonunit_encoder_input_scale_preserved_as_calibration_evidence(tmp_path):
    pytest.importorskip("torch")
    source, expected = _encoder(tmp_path)
    root = tmp_path / "managed"
    _managed(root, "encoder", expected)
    raw = bytearray(source.read_bytes())
    hsize = struct.unpack("<Q", raw[:8])[0]
    header = json.loads(raw[8:8 + hsize])
    spec = header["model.layers.0.self_attn.q_proj.scale_input"]
    offset = 8 + hsize + spec["data_offsets"][0]
    raw[offset:offset + 2] = struct.pack("<H", 0x4000)  # BF16 2.0
    source.write_bytes(raw)
    result = validate_complete_tensor_schema(source, root, family="encoder")
    assert result["status"] == "schema_matches"
    assert result["schema_verified"] is True
    assert result["excluded_input_scale_count"] == 2
    assert result["input_scale_metadata"]["nonunit_count"] == 1
    assert result["input_scale_metadata"]["unit_count"] == 1
    assert result["input_scale_metadata"]["nonunit_max"] == 2.0
    assert result["quantization_compatibility"]["fp8_runtime_verified"] is False
    assert not result["loadable"]


def test_z217_orphan_unit_input_scale_blocks_even_if_value_is_one(tmp_path):
    pytest.importorskip("torch")
    source, expected = _encoder(tmp_path)
    root = tmp_path / "managed"
    _managed(root, "encoder", expected)
    raw = source.read_bytes()
    hsize = struct.unpack("<Q", raw[:8])[0]
    header = json.loads(raw[8:8 + hsize])
    orphan_spec = dict(header["model.layers.0.self_attn.q_proj.scale_input"])
    # Replace a legal paired name with a seemingly harmless orphan name.
    header.pop("model.layers.0.self_attn.q_proj.scale_input")
    header["orphan.scale_input"] = orphan_spec
    new_header = json.dumps(header).encode()
    source.write_bytes(struct.pack("<Q", len(new_header)) + new_header + raw[8 + hsize:])
    result = validate_complete_tensor_schema(source, root, family="encoder")
    assert result["status"] == "blocked"
    assert "Orphan input scale" in result["reason"]
    assert not result["schema_verified"]


def test_z218_stream_preflight_is_exact_and_read_only(tmp_path):
    from morphorum.zimage_fp8_stream import plan_fp8_stream
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    raw = source.read_bytes()
    result = plan_fp8_stream(source, managed, family="transformer")
    assert result["status"] == "planned", result
    assert result["tensor_count"] == 8
    assert result["fp8_output_tensors"] == 8
    assert result["max_input_chunk_bytes"] == 2 * 1024 ** 2
    assert result["estimated_peak_conversion_ram_bytes"] <= 32 * 1024 ** 2
    assert result["output_exact_bytes"] > result["output_payload_bytes"]
    assert result["disk_required_bytes"] >= result["output_exact_bytes"] + 2 * 1024 ** 3
    assert not result["loadable"] and not result["conversion_enabled"]
    assert source.read_bytes() == raw
    assert not (tmp_path / "scratch").exists()


def test_z218_stream_export_validates_qkv_and_atomically_publishes_scratch(tmp_path):
    from morphorum.zimage_fp8_stream import FP8StreamError, export_fp8_stream
    torch = pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    source_raw = source.read_bytes()
    managed_file = managed / "transformer" / "weights-00001-of-00001.safetensors"
    managed_raw = managed_file.read_bytes()
    destination = tmp_path / "scratch" / "experiment"
    exported = export_fp8_stream(source, managed, family="transformer", scratch=destination)
    assert exported["status"] == "exported_nonloadable"
    assert exported["tensor_count"] == 8
    assert not exported["loadable"]
    artifact = destination / "diffusion_pytorch_model.safetensors"
    buf = artifact.read_bytes()
    hsize = struct.unpack("<Q", buf[:8])[0]
    converted = json.loads(buf[8:8 + hsize])
    assert set(converted) == set(expected)
    assert all(v["dtype"] == "BF16" for v in converted.values())
    payload = buf[8 + hsize:]
    assert len(payload) == sum(2 * __import__("math").prod(dims) for dims in expected.values())
    for suffix in ("q", "k", "v"):
        spec = converted[f"layers.0.attention.to_{suffix}.weight"]
        start, end = spec["data_offsets"]
        data = torch.frombuffer(bytearray(payload[start:end]), dtype=torch.uint8).view(torch.bfloat16)
        assert data.shape == (8,)
        assert (data == 2.0).all().item()
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["loadable"] is False
    assert manifest["runtime_verified"] is False
    assert manifest["output_sha256"] == __import__("hashlib").sha256(buf).hexdigest()
    assert len(manifest["tensor_sha256"]) == 8
    assert source.read_bytes() == source_raw
    assert managed_file.read_bytes() == managed_raw
    with pytest.raises(FP8StreamError, match="Scratch destination"):
        export_fp8_stream(source, managed, family="transformer", scratch=destination)


def test_z218_stream_separate_qwen_keeps_bf16_embedding_and_fp8_weights(tmp_path):
    from morphorum.zimage_fp8_stream import export_fp8_stream
    torch = pytest.importorskip("torch")
    source, expected = _encoder(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "encoder", expected)
    output = tmp_path / "scratch" / "encoder"
    result = export_fp8_stream(source, managed, family="encoder", scratch=output)
    assert result["status"] == "exported_nonloadable"
    artifact = output / "model.safetensors"
    raw = artifact.read_bytes()
    length = struct.unpack("<Q", raw[:8])[0]
    header = json.loads(raw[8:8 + length])
    assert set(header) == set(expected)
    assert len(header) == 3
    assert all(t["dtype"] == "BF16" for t in header.values())
    assert not result["loadable"]


def test_z218_stream_blocks_output_inside_managed_model_or_source_tree(tmp_path):
    from morphorum.zimage_fp8_stream import FP8StreamError, export_fp8_stream
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    for output in (source.parent / "bad", managed / "bad"):
        with pytest.raises(FP8StreamError, match="intersects"):
            export_fp8_stream(source, managed, family="transformer", scratch=output)
        assert not output.exists()


def test_z218_stream_requires_exact_schema_not_just_fp8_marker(tmp_path):
    from morphorum.zimage_fp8_stream import plan_fp8_stream
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", {**expected, "alien.weight": (1,)})
    plan = plan_fp8_stream(source, managed, family="transformer")
    assert plan["status"] == "blocked"
    assert not plan["loadable"]


def test_z218_stream_independent_scratch_integrity_detects_tensor_corruption(tmp_path):
    from morphorum.zimage_fp8_stream import (
        FP8StreamError, export_fp8_stream, verify_fp8_stream_artifact
    )
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    destination = tmp_path / "scratch" / "verify"
    exported = export_fp8_stream(source, managed, family="transformer", scratch=destination)
    assert exported["status"] == "exported_nonloadable"
    valid = verify_fp8_stream_artifact(destination)
    assert valid["status"] == "verified_nonloadable"
    assert valid["tensor_count"] == 8 and not valid["loadable"]
    artifact = destination / "diffusion_pytorch_model.safetensors"
    raw = bytearray(artifact.read_bytes())
    raw[-1] ^= 0x01
    artifact.write_bytes(raw)
    with pytest.raises(FP8StreamError, match="tensor SHA-256 mismatch"):
        verify_fp8_stream_artifact(destination)


def test_z218_stream_disk_shortage_refuses_export_before_creation(tmp_path, monkeypatch):
    import morphorum.zimage_fp8_stream as fp8_stream
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    scratch = tmp_path / "scratch" / "new"
    monkeypatch.setattr(fp8_stream, "_free_space", lambda *_: 1)
    plan = fp8_stream.plan_fp8_stream(source, managed, family="transformer", scratch=scratch)
    assert plan["status"] == "insufficient_disk"
    assert plan["scratch_space_sufficient"] is False
    with pytest.raises(fp8_stream.FP8StreamError, match="insufficient_disk"):
        fp8_stream.export_fp8_stream(source, managed, family="transformer", scratch=scratch)
    assert not scratch.exists()


def test_z218_stream_nan_fp8_refuses_publish_and_cleans_temporary_files(tmp_path):
    from morphorum.zimage_fp8_stream import FP8StreamError, export_fp8_stream
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    raw = bytearray(source.read_bytes())
    size = struct.unpack("<Q", raw[:8])[0]
    header = json.loads(raw[8:8 + size])
    start = header["x_embedder.weight"]["data_offsets"][0]
    raw[8 + size + start] = 0x7F  # E4M3FN NaN
    source.write_bytes(raw)
    dest = tmp_path / "scratch" / "bad_fp8"
    with pytest.raises(FP8StreamError, match="Nonfinite FP8 conversion output"):
        export_fp8_stream(source, managed, family="transformer", scratch=dest)
    assert not dest.exists()
    assert not list((tmp_path / "scratch").glob(".z218-stream-*"))
    assert not list((tmp_path / "scratch").glob("*.lock"))


def test_z219_read_only_source_parity_checks_every_transformer_tensor_and_qkv(tmp_path):
    from morphorum.zimage_fp8_stream import (
        export_fp8_stream, verify_fp8_stream_against_source
    )
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    scratch = tmp_path / "scratch" / "z219-transformer"
    exported = export_fp8_stream(source, managed, family="transformer", scratch=scratch)
    before = (scratch / "diffusion_pytorch_model.safetensors").read_bytes()
    result = verify_fp8_stream_against_source(
        source, managed, family="transformer", scratch=scratch
    )
    assert exported["status"] == "exported_nonloadable"
    assert result["status"] == "source_sample_parity_verified_nonloadable"
    assert result["tensor_count"] == 8
    assert result["sample_windows_checked"] >= 8
    assert result["fp8_windows_checked"] >= 8
    assert result["sample_mismatches"] == 0
    assert result["source_full_sha256_verified"] is False
    assert not result["loadable"] and not result["runtime_verified"]
    assert (scratch / "diffusion_pytorch_model.safetensors").read_bytes() == before


def test_z219_read_only_source_parity_for_separate_qwen_encoder(tmp_path):
    from morphorum.zimage_fp8_stream import (
        export_fp8_stream, verify_fp8_stream_against_source
    )
    pytest.importorskip("torch")
    source, expected = _encoder(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "encoder", expected)
    scratch = tmp_path / "scratch" / "z219-encoder"
    export_fp8_stream(source, managed, family="encoder", scratch=scratch)
    result = verify_fp8_stream_against_source(
        source, managed, family="encoder", scratch=scratch
    )
    assert result["status"] == "source_sample_parity_verified_nonloadable"
    assert result["tensor_count"] == 3
    assert result["fp8_windows_checked"] >= 2
    assert not result["loadable"]


def test_z219_parity_rejects_changed_source_metadata(tmp_path):
    from morphorum.zimage_fp8_stream import (
        FP8StreamError, export_fp8_stream, verify_fp8_stream_against_source
    )
    import os
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    scratch = tmp_path / "scratch" / "z219-changed"
    export_fp8_stream(source, managed, family="transformer", scratch=scratch)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 100000))
    with pytest.raises(FP8StreamError, match="checkpoint metadata differs"):
        verify_fp8_stream_against_source(source, managed, family="transformer", scratch=scratch)


def test_z219_parity_rejects_rehashed_but_numerically_wrong_scratch(tmp_path):
    from morphorum.zimage_fp8_stream import (
        FP8StreamError, export_fp8_stream, verify_fp8_stream_against_source
    )
    import hashlib
    pytest.importorskip("torch")
    source, expected = _original_transformer(tmp_path)
    managed = tmp_path / "managed"
    _managed(managed, "transformer", expected)
    scratch = tmp_path / "scratch" / "z219-rehashed"
    export_fp8_stream(source, managed, family="transformer", scratch=scratch)
    artifact = scratch / "diffusion_pytorch_model.safetensors"
    data = bytearray(artifact.read_bytes())
    header_len = struct.unpack("<Q", data[:8])[0]
    header = json.loads(data[8:8 + header_len])
    name = "layers.0.attention.to_k.weight"
    start, end = header[name]["data_offsets"]
    data[8 + header_len + start] ^= 0x01
    artifact.write_bytes(data)
    # Recompute BOTH checksums to prove source parity does more than
    # simply trust an internally self-consistent scratch manifest.
    manifest_path = scratch / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tensor_sha256"][name] = hashlib.sha256(
        data[8 + header_len + start:8 + header_len + end]
    ).hexdigest()
    manifest["output_sha256"] = hashlib.sha256(data).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(FP8StreamError, match="Source-to-output window parity mismatch"):
        verify_fp8_stream_against_source(
            source, managed, family="transformer", scratch=scratch
        )

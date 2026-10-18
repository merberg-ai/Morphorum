"""Z2.16 scratch-only conversion experiments on synthetic checkpoints."""
from __future__ import annotations

import hashlib
import json
import struct

import pytest

from morphorum.zimage_fp8_prototype import (
    FP8PrototypeError, export_fp8_bf16_windows, plan_fp8_bf16_windows,
)
from morphorum.zimage_inspect import inspect_zimage_checkpoint


def make_source(tmp_path, *, marker_count=2, bad_scale=None):
    source = tmp_path / "checkpoints" / "input.safetensors"
    source.parent.mkdir(parents=True)
    payload = bytearray()
    header = {}

    def add(name, dtype, shape, data):
        first = len(payload)
        payload.extend(data)
        header[name] = {
            "dtype": dtype, "shape": list(shape),
            "data_offsets": [first, len(payload)],
        }

    names = (
        "x_embedder.weight", "final_layer.weight", "cap_embedder.1.weight",
        "noise_refiner.0.weight", "context_refiner.0.weight",
        "layers.0.attention.qkv.weight",
    )
    for name in names:
        if name.endswith("qkv.weight"):
            shape = (6, 4)
            values = bytes([0x38, 0x40, 0xB8, 0x00] * 6)
        else:
            shape = (4,)
            values = bytes([0x38, 0x40, 0xB8, 0x00])
        add(name, "F8_E4M3", shape, values)
        scale = bad_scale if name == "x_embedder.weight" and bad_scale is not None else 2.0
        add(name[:-len(".weight")] + ".scale_weight", "F32", (1,),
            struct.pack("<f", scale))
    add("scaled_fp8", "F8_E4M3", (marker_count,), bytes([0] * marker_count))
    encoded = json.dumps(header).encode()
    source.write_bytes(struct.pack("<Q", len(encoded)) + encoded + payload)
    return source


def test_z216_planning_is_read_only_and_qkv_regions_do_not_overlap(tmp_path):
    pytest.importorskip("torch")
    source = make_source(tmp_path)
    before = source.read_bytes()
    plan = plan_fp8_bf16_windows(source)
    assert plan["status"] == "planned"
    assert plan["windows_count"] == 4
    assert plan["max_bf16_bytes"] == 56
    assert [w["partition"] for w in plan["windows"]] == ["full", "q", "k", "v"]
    assert [w["element_offset"] for w in plan["windows"][1:]] == [0, 8, 16]
    assert [w["target_hint"].split(".")[-2] for w in plan["windows"][1:]] == [
        "to_q", "to_k", "to_v"
    ]
    assert before == source.read_bytes()
    assert list(tmp_path.iterdir()) == [source.parent]
    assert not plan["loadable"] and not plan["conversion_enabled"]


def test_z216_explicit_scratch_export_is_atomic_and_bf16_reference_matched(tmp_path):
    torch = pytest.importorskip("torch")
    source = make_source(tmp_path)
    original = source.read_bytes()
    managed = tmp_path / "managed"
    managed.mkdir()
    destination = tmp_path / "experiments" / "run_001"
    result = export_fp8_bf16_windows(source, destination, managed_root=managed)
    assert result["status"] == "sample_windows_exported"
    assert result["bf16_payload_bytes"] == 56
    assert result["window_count"] == 4
    assert not result["loadable"]
    assert source.read_bytes() == original
    assert not list(managed.iterdir())
    assert set(p.name for p in destination.iterdir()) == {"samples.safetensors", "manifest.json"}
    file = destination / "samples.safetensors"
    content = file.read_bytes()
    header_len = struct.unpack("<Q", content[:8])[0]
    output_header = json.loads(content[8:8 + header_len])
    output_payload = content[8 + header_len:]
    assert len(output_payload) == 56
    assert len(output_header) == 4
    for spec in output_header.values():
        assert spec["dtype"] == "BF16"
        assert spec["shape"] == [4] or spec["shape"] == [8]
    a, b = output_header["prototype_window_000"]["data_offsets"]
    window = torch.frombuffer(bytearray(output_payload[a:b]), dtype=torch.uint8).view(
        torch.bfloat16
    ).to(torch.float32)
    assert window.tolist() == [2.0, 4.0, -2.0, 0.0]
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["output_sha256"] == hashlib.sha256(content).hexdigest()
    assert all(x["verified"] for x in manifest["samples"])
    assert not manifest["loadable"] and not manifest["conversion_enabled"]
    with pytest.raises(FP8PrototypeError, match="already exists"):
        export_fp8_bf16_windows(source, destination, managed_root=managed)


def test_z216_blocks_source_tree_and_managed_tree_outputs(tmp_path):
    pytest.importorskip("torch")
    source = make_source(tmp_path)
    with pytest.raises(FP8PrototypeError, match="checkpoint tree"):
        export_fp8_bf16_windows(source, source.parent / "sample_outputs")
    managed = tmp_path / "managed"
    with pytest.raises(FP8PrototypeError, match="managed model tree"):
        export_fp8_bf16_windows(source, managed / "experiment", managed_root=managed)
    assert not managed.exists()


def test_z216_rejects_failed_preflight_without_artifact(tmp_path):
    pytest.importorskip("torch")
    source = make_source(tmp_path, bad_scale=-1.0)
    plan = plan_fp8_bf16_windows(source)
    assert plan["status"] == "blocked"
    destination = tmp_path / "experiments" / "bad"
    with pytest.raises(FP8PrototypeError, match="validation"):
        export_fp8_bf16_windows(source, destination)
    assert not destination.exists()


def test_z216_existing_production_converter_still_blocks_fp8(tmp_path):
    from morphorum.zimage_conversion import ConversionPreflightError, plan_conversion
    source = make_source(tmp_path)
    with pytest.raises(ConversionPreflightError, match="FP8"):
        plan_conversion(source, tmp_path / "cache")

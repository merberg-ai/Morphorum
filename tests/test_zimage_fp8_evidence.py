import json
import struct

from morphorum.zimage_fp8_evidence import probe_fp8_scalars, inspect_managed_auxiliaries


def test_z213_bounded_marker_and_scale_probe(tmp_path):
    file = tmp_path / "model.safetensors"
    names = ["x_embedder.weight", "final_layer.weight", "cap_embedder.weight",
             "noise_refiner.0.weight", "context_refiner.0.weight",
             "layers.0.weight"]
    specs = {}
    payload = bytearray()
    for name in names:
        start = len(payload)
        payload.extend(b"X")
        specs[name] = {"dtype": "F8_E4M3", "shape": [1], "data_offsets": [start, len(payload)]}
    for name, val in (("layers.0.scale_weight", 2.0), ("scaled_fp8", 1.0)):
        start = len(payload)
        payload.extend(struct.pack("<f", val))
        specs[name] = {"dtype": "F32", "shape": [1], "data_offsets": [start, len(payload)]}
    header = json.dumps(specs).encode()
    file.write_bytes(struct.pack("<Q", len(header)) + header + payload)
    result = probe_fp8_scalars(file)
    assert result["marker"]["scalar"]["value"] == 1.0
    assert result["sample_scales"][0]["value"] == 2.0
    assert result["scale_direction"] == "unverified"
    assert result["loadable"] is False


def test_z213_managed_inventory_is_read_only(tmp_path):
    root = tmp_path / "managed"
    result = inspect_managed_auxiliaries(root)
    assert not root.exists()
    assert not result["compatible"]
    assert not result["components"]["tokenizer"]["present"]

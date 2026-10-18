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


def _make_reference_fp8_file(path, marker_size):
    payload = bytearray()
    specs = {}
    ordinary = ["x_embedder.weight", "final_layer.weight", "cap_embedder.weight",
                "noise_refiner.0.weight", "context_refiner.0.weight"]
    for name in ordinary:
        start = len(payload)
        payload.extend(bytes([0x38]))
        specs[name] = {"dtype": "F8_E4M3", "shape": [1],
                       "data_offsets": [start, len(payload)]}
    start = len(payload)
    payload.extend(bytes([0x38, 0x40, 0xB8, 0x00]))
    specs["layers.0.weight"] = {"dtype": "F8_E4M3", "shape": [4],
                                "data_offsets": [start, len(payload)]}
    start = len(payload)
    payload.extend(struct.pack("<f", 2.0))
    specs["layers.0.scale_weight"] = {"dtype": "F32", "shape": [1],
                                     "data_offsets": [start, len(payload)]}
    start = len(payload)
    payload.extend(bytes([0x38]) * marker_size)
    specs["scaled_fp8"] = {"dtype": "F8_E4M3", "shape": [marker_size],
                           "data_offsets": [start, len(payload)]}
    header = json.dumps(specs).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)


def test_z214_two_element_marker_and_bounded_reference_values(tmp_path):
    path = tmp_path / "zimage.safetensors"
    _make_reference_fp8_file(path, 2)
    result = probe_fp8_scalars(path)
    assert result["marker"]["raw_hex"] == "3838"
    assert result["marker"]["decoded_values"] == [1.0, 1.0]
    assert result["marker"]["comfyui_full_precision_matrix_mult"] is True
    sample = result["numerical_samples"][0]
    assert sample["decoded_fp8"] == [1.0, 2.0, -1.0, 0.0]
    assert sample["reference_dequantized"] == [2.0, 4.0, -2.0, 0.0]
    assert result["scale_reference"]["runtime_verified"] is False
    assert result["loadable"] is False


def test_z214_empty_marker_means_no_full_precision_matmul_hint(tmp_path):
    path = tmp_path / "encoder.safetensors"
    _make_reference_fp8_file(path, 0)
    result = probe_fp8_scalars(path)
    assert result["marker"]["raw_hex"] == ""
    assert result["marker"]["decoded_values"] == []
    assert result["marker"]["comfyui_full_precision_matrix_mult"] is False


def test_z214_managed_config_summary_has_no_mutations(tmp_path):
    root = tmp_path / "managed"
    (root / "vae").mkdir(parents=True)
    (root / "scheduler").mkdir()
    (root / "tokenizer").mkdir()
    (root / "text_encoder").mkdir()
    (root / "model_index.json").write_text(json.dumps({
        "_class_name": "ZImagePipeline", "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
        "tokenizer": ["transformers", "Qwen2Tokenizer"],
        "vae": ["diffusers", "AutoencoderKL"],
    }))
    (root / "vae" / "config.json").write_text(json.dumps({
        "_class_name": "AutoencoderKL", "scaling_factor": 0.3611}))
    (root / "scheduler" / "scheduler_config.json").write_text(json.dumps({
        "_class_name": "FlowMatchEulerDiscreteScheduler"}))
    (root / "tokenizer" / "tokenizer_config.json").write_text(json.dumps({
        "tokenizer_class": "Qwen2Tokenizer", "chat_template": "not exposed"}))
    (root / "text_encoder" / "config.json").write_text(json.dumps({
        "model_type": "qwen3", "num_hidden_layers": 36}))
    result = inspect_managed_auxiliaries(root)
    assert result["configuration"]["vae"]["summary"]["_class_name"] == "AutoencoderKL"
    assert result["configuration"]["scheduler"]["summary"]["_class_name"] == "FlowMatchEulerDiscreteScheduler"
    assert "chat_template" not in result["configuration"]["tokenizer"]["summary"]
    assert result["compatible"] is False
    assert result["loadable"] is False

"""Z2.17.2: complete FP8 activation-scale inventory, independent BF16 policy."""
import json
import math
import struct

import pytest

from morphorum.zimage_input_scales import (
    InputScaleInspectionError, inspect_input_scale_metadata,
)


def _make_quantized_encoder(path, *, count=252, special=None):
    """Synthetic 252-layer-scale checkpoint, no model payload decoding."""
    special = special or {}
    payload = bytearray()
    header = {}

    def add(name, dtype, shape, data):
        start = len(payload)
        payload.extend(data)
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [start, len(payload)]}

    for index in range(count):
        prefix = f"model.layers.{index}.self_attn.q_proj"
        add(prefix + ".weight", "F8_E4M3", [4], bytes([0x38] * 4))
        add(prefix + ".scale_weight", "F32", [1], struct.pack("<f", 2.0))
        dtype, value = special.get(index, ("BF16", 1.0))
        if dtype == "BF16":
            raw = struct.pack("<H", struct.unpack("<I", struct.pack("<f", value))[0] >> 16)
        elif dtype == "F16":
            raw = struct.pack("<e", value)
        else:
            raw = struct.pack("<f", value)
        add(prefix + ".scale_input", dtype, [1], raw)
    add("scaled_fp8", "F8_E4M3", [0], b"")
    h = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(h)) + h + payload)
    return path


def test_z2172_all_252_scales_with_mixed_dtypes_and_nonunit_values(tmp_path):
    f = _make_quantized_encoder(
        tmp_path / "encoder.safetensors",
        special={0: ("BF16", 2.0), 37: ("F16", 0.5), 251: ("F32", 1.25)},
    )
    original = f.read_bytes()
    evidence = inspect_input_scale_metadata(f)
    assert evidence["status"] == "inspected"
    assert evidence["count"] == 252
    assert evidence["unit_count"] == 249
    assert evidence["nonunit_count"] == 3
    assert evidence["min"] == 0.5 and evidence["max"] == 2.0
    assert evidence["nonunit_min"] == 0.5 and evidence["nonunit_max"] == 2.0
    assert evidence["dtypes"] == {"BF16": 250, "F16": 1, "F32": 1}
    assert any(row["value"] == 0.5 for row in evidence["examples"])
    assert len(evidence["examples"]) <= 12
    assert not evidence["fp8_runtime_scale_binding_verified"]
    assert not evidence["loadable"]
    assert f.read_bytes() == original


@pytest.mark.parametrize("bad", [0.0, -0.5, float("inf"), float("nan")])
def test_z2172_rejects_invalid_fp8_activation_calibration(tmp_path, bad):
    file = _make_quantized_encoder(
        tmp_path / "bad.safetensors", count=2, special={0: ("F32", bad)}
    )
    with pytest.raises(InputScaleInspectionError, match="Nonfinite or nonpositive"):
        inspect_input_scale_metadata(file)


def test_z2172_rejects_orphan_input_scale_even_when_unit(tmp_path):
    file = _make_quantized_encoder(tmp_path / "orphan.safetensors", count=2)
    raw = file.read_bytes()
    length = struct.unpack("<Q", raw[:8])[0]
    fields = json.loads(raw[8:8 + length])
    entry = fields.pop("model.layers.1.self_attn.q_proj.scale_input")
    fields["orphan.scale_input"] = entry
    new_header = json.dumps(fields).encode()
    file.write_bytes(struct.pack("<Q", len(new_header)) + new_header + raw[8 + length:])
    with pytest.raises(InputScaleInspectionError, match="Orphan"):
        inspect_input_scale_metadata(file)


def test_z2172_dequantized_bf16_linear_does_not_use_fp8_activation_calibration():
    """A WEIGHT-ONLY BF16 route has no FP8 activation quantizer at all.

    This does not validate the model or ComfyUI's GPU FP8 matmul implementation.
    In contrast to BF16, a sample FP8 input quantizer depends on calibration.
    """
    torch = pytest.importorskip("torch")
    input_float = torch.tensor([[1.125, -0.333, 0.0625, 1.953125]],
                               dtype=torch.bfloat16)
    bits = bytearray([0x38, 0x40, 0xB8, 0x00,
                      0x30, 0x38, 0x40, 0xB8])
    fp8_weight = torch.frombuffer(bits, dtype=torch.uint8).view(
        torch.float8_e4m3fn
    ).reshape(2, 4)
    weight_scale = torch.tensor(2.0, dtype=torch.bfloat16)
    weight_bf16 = fp8_weight.to(torch.bfloat16) * weight_scale
    baseline = torch.nn.functional.linear(input_float, weight_bf16)
    for unused_fp8_input_scale in (0.5, 1.0, 2.0, 16.0):
        # No FP8 input quantization exists in this tested BF16 path.
        assert unused_fp8_input_scale > 0
        output = torch.nn.functional.linear(input_float, weight_bf16)
        assert torch.equal(output, baseline)
    # Show that calibration cannot just be discarded for an FP8 execution
    # path: scaling before FP8 casting can alter the quantized activations.
    x = torch.tensor([0.91, 0.097, 0.34], dtype=torch.float32)
    q1 = (x / 1.0).to(torch.float8_e4m3fn).to(torch.float32) * 1.0
    q2 = (x / 0.1).to(torch.float8_e4m3fn).to(torch.float32) * 0.1
    assert not torch.equal(q1, q2)

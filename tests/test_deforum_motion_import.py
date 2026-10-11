"""DMI1: Deforum Motion Studio exports, previews and hardening."""
import json
import pytest

from morphorum.deforum_motion_import import preview_motion_settings
from morphorum.deforum_import import DeforumImportError


def source(**changes):
    obj = {"animation_mode":"3D", "fps":24, "max_frames":120,
           "diffusion_cadence":"0:(3)",
           "soundtrack_path":r"C:\\Music\\riff.wav", "add_soundtrack":"File",
           "translation_x":"0:(0),60:(0.2),119:(0)",
           "translation_y":"0:(0)", "translation_z":"0:(0),24:(1),119:(1)",
           "rotation_3d_x":"0:(0)", "rotation_3d_y":"0:(0)",
           "rotation_3d_z":"0:(0),48:(-0.5),119:(0)"}
    obj.update(changes)
    return json.dumps(obj)


def project(frames=120, fps=24):
    return {"animation":{"max_frames":frames,"fps":fps}}


def test_dms_export_preview_is_nonmutating_and_audio_path_is_basename_only():
    initial=project()
    result=preview_motion_settings(source(),filename="test.txt",project=initial)
    assert initial==project()
    assert result["read_only"]
    assert result["can_apply_unchanged"]
    assert result["source"]["soundtrack_filename"]=="riff.wav"
    assert "Music" not in str(result)
    assert result["source"]["cadence"]==3
    assert len(result["samples"])==120
    assert result["axes"]["rotation_z"]["keyframes"]==3
    assert result["samples"][24]["translation_z"]==1


def test_mismatched_project_timing_is_reported_not_automatically_changed():
    report=preview_motion_settings(source(),project=project(180,30))
    assert not report["can_apply_unchanged"]
    assert not report["project_comparison"]["fps_matches"]
    assert any("FPS" in w for w in report["warnings"])
    assert any("Frame count" in w for w in report["warnings"])


def test_oversize_frame_count_cannot_apply_unchanged():
    report=preview_motion_settings(source(max_frames=3100),project=project(3100,24))
    assert not report["can_apply_unchanged"]
    assert len(report["samples"])<=241


@pytest.mark.parametrize("bad",[
    {"translation_z":"0:(0), 40:(__import__('os').system('echo no'))"},
    {"rotation_3d_x":"0:(0),12:(NaN)"},
    {"rotation_3d_x":"0:(0),12:(inf)"},
    {"rotation_3d_y":"0:(0),60:(3),59:(2)"},
    {"rotation_3d_z":"0:(0),999:(1)"},
    {"translation_x":"12:(0)"},
    {"fps":float("nan")},
    {"max_frames":40000},
    {"diffusion_cadence":"0:(0)"},
    {"diffusion_cadence":"0:(2.5)"},
    {"soundtrack_path":["unsafe"]},
    {"animation_mode":"2D"},
])
def test_malformed_unsafe_and_incompatible_settings_rejected(bad):
    with pytest.raises(DeforumImportError):
        preview_motion_settings(source(**bad),project=project())


def test_missing_axes_produce_warning_and_disable_unchanged_apply():
    data=json.loads(source())
    del data["rotation_3d_y"]
    result=preview_motion_settings(json.dumps(data),project=project())
    assert not result["can_apply_unchanged"]
    assert result["axes"]["rotation_y"]["min"]==0
    assert result["warnings"]


def test_missing_all_axes_rejected():
    data=json.loads(source())
    for name in ("translation_x","translation_y","translation_z",
                 "rotation_3d_x","rotation_3d_y","rotation_3d_z"):
        del data[name]
    with pytest.raises(DeforumImportError):
        preview_motion_settings(json.dumps(data))

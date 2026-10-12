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
    return {"animation":{"max_frames":frames,"fps":fps}, "cadence":{"diffusion":"0:(3)"}}


def test_dms_export_preview_is_nonmutating_and_audio_path_is_basename_only():
    initial=project()
    result=preview_motion_settings(source(),filename="test.txt",project=initial)
    assert initial==project()
    assert result["read_only"]
    assert result["can_apply_unchanged"]
    assert result["source"]["soundtrack_filename"]=="riff.wav"
    assert result["source"]["soundtrack_path"] == r"C:\\Music\\riff.wav"
    assert result["source"]["soundtrack_attached"] is True
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

def test_prepare_import_only_changes_six_camera_axes():
    from morphorum.animation_projects import normalize_animation_project
    from morphorum.deforum_motion_import import prepare_motion_import
    p=normalize_animation_project({
        "name":"Import target", "animation":{"mode":"3d","fps":24,"max_frames":120},
        "cadence":{"diffusion":"0:(3)"},
    },project_id="deforum-motion-import-test")
    imported, report=prepare_motion_import(source(),filename="motion.txt",project=p)
    assert imported["tracks"]["camera_3d"]["translation_z"]["schedule"]=="0:(0),24:(-0.005),119:(-0.005)"
    assert imported["animation"]==p["animation"]
    assert imported["cadence"]==p["cadence"]
    assert imported["prompts"]==p["prompts"]
    assert imported["model"]==p["model"]
    assert imported["motion_lab"]==p["motion_lab"]
    assert p["tracks"]["camera_3d"]["translation_z"]!=imported["tracks"]["camera_3d"]["translation_z"]
    assert report["source_sha256"]


def test_prepare_rejects_incompatible_and_existing_motion_layers():
    from morphorum.animation_projects import normalize_animation_project
    from morphorum.deforum_motion_import import prepare_motion_import
    p=normalize_animation_project({
        "name":"Import target","animation":{"mode":"3d","fps":24,"max_frames":120},
        "cadence":{"diffusion":"0:(3)"},
    },project_id="deforum-motion-import-test")
    with pytest.raises(DeforumImportError,match="FPS"):
        prepare_motion_import(source(fps=30),filename="motion.txt",project=p)
    p["motion_lab"]["layers"]=[{"id":"existing"}]
    with pytest.raises(DeforumImportError,match="Motion Lab"):
        prepare_motion_import(source(),filename="motion.txt",project=p)


def test_compatibility_translation_and_strength():
    from morphorum.animation_projects import normalize_animation_project
    from morphorum.deforum_motion_import import prepare_motion_import
    p=normalize_animation_project({
        "name":"Conversion target","animation":{"mode":"3d","fps":24,"max_frames":120},
        "cadence":{"diffusion":"0:(3)"}
    },project_id="dmi-convert")
    changed,report=prepare_motion_import(source(
        translation_x="0:(200)",translation_y="0:(200)",translation_z="0:(200)",
        rotation_3d_y="0:(5)"
    ),filename="motion.txt",project=p)
    tracks=changed["tracks"]["camera_3d"]
    assert tracks["translation_x"]["schedule"]=="0:(-1)"
    assert tracks["translation_y"]["schedule"]=="0:(1)"
    assert tracks["translation_z"]["schedule"]=="0:(-1)"
    assert tracks["rotation_y"]["schedule"]=="0:(5)"
    raw,_=prepare_motion_import(source(),filename="motion.txt",project=p,
        options={"mode":"raw","translation_strength":0.5,"rotation_strength":0.5})
    assert raw["tracks"]["camera_3d"]["translation_z"]["schedule"]=="0:(0),24:(0.5),119:(0.5)"
    assert raw["tracks"]["camera_3d"]["rotation_z"]["schedule"]=="0:(0),48:(-0.25),119:(0)"


@pytest.mark.parametrize("options",[
    {"mode":"invalid"},{"translation_strength":float("nan")},
    {"rotation_strength":-1},{"translation_strength":5},{"translation_strength":True},
    {"other":"unsafe"},
])
def test_unsafe_conversion_options_rejected(options):
    from morphorum.deforum_motion_import import conversion_options
    with pytest.raises(DeforumImportError):
        conversion_options(options)


def test_four_hundred_percent_strength_is_valid():
    from morphorum.deforum_motion_import import conversion_options, converted_schedule
    options=conversion_options({"translation_strength":4, "rotation_strength":4})
    assert converted_schedule("0:(100)", "translation_z", options, 120)=="0:(-2)"
    assert converted_schedule("0:(12.5)", "rotation_y", options, 120)=="0:(50)"

"""MS6.0 safety baseline for future installation onboarding.

These checks do not launch a setup wizard or change any real user install.
They document existing contracts so MS6.1+ cannot misclassify upgrades,
silently replace projects/settings or confuse LoRAs with base checkpoints.
"""
from __future__ import annotations

from pathlib import Path

import morphorum.animation_projects as projects
import morphorum.model_index as model_index
import morphorum.settings as settings
from morphorum.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


def test_fresh_install_has_default_config_and_starter_project_on_both_platforms() -> None:
    """An installer-created config/project cannot signal a legacy install."""
    windows = (ROOT / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
    linux = (ROOT / "scripts" / "install_linux.sh").read_text(encoding="utf-8")
    assert "Copy-Item (Join-Path $Root 'config\\default.yaml') $userConfig" in windows
    assert "if (-not (Test-Path $userConfig))" in windows
    assert "-m morphorum seed-example" in windows
    assert "cp \"$ROOT/config/default.yaml\" \"$ROOT/data/config.yaml\"" in linux
    assert 'if [[ ! -f "$ROOT/data/config.yaml" ]]; then' in linux
    assert '-m morphorum seed-example' in linux
    # This is the earlier bundled example, which the wizard must not erase.
    assert (ROOT / "config" / "example-project.json").is_file()


def test_serve_mode_defaults_to_webui_and_backend_only_is_explicit() -> None:
    """Parser introspection only: never start network servers in these tests."""
    parser = build_parser()
    normal = parser.parse_args(["serve"])
    assert normal.func.__name__ == "command_serve"
    assert normal.backend_only is False
    assert normal.lan is False
    assert normal.host is None
    assert normal.port is None

    api_only = parser.parse_args(["serve", "--backend-only"])
    assert api_only.backend_only is True
    assert api_only.lan is False

    lan_webui = parser.parse_args(["serve", "--lan"])
    assert lan_webui.backend_only is False
    assert lan_webui.lan is True


def test_readable_directory_is_not_proof_of_model_and_lora_is_not_a_checkpoint(
    tmp_path, monkeypatch,
) -> None:
    """A proper setup wizard must distinguish accessibility from loadability."""
    checkpoint_root = tmp_path / "empty-checkpoint-folder"
    lora_root = tmp_path / "optional-loras"
    checkpoint_root.mkdir()
    lora_root.mkdir()
    (lora_root / "style.safetensors").write_bytes(b"candidate only")
    (checkpoint_root / "readme.txt").write_text("not a checkpoint", encoding="utf-8")

    assert settings.validate_path(str(checkpoint_root))["is_directory"]
    assert settings.validate_path(str(checkpoint_root))["readable"]

    monkeypatch.setattr(settings, "USER_CONFIG", tmp_path / "config.yaml")
    monkeypatch.setattr(model_index, "MODEL_INDEX_DB", tmp_path / "model-index.db")
    settings.save_settings({
        "models": {"sdxl": {
            "checkpoints": [str(checkpoint_root)],
            "loras": [str(lora_root)],
        }},
    })
    scan = model_index.scan_models()
    assert scan["total"] == 1
    assert model_index.list_models(family="sdxl", kind="checkpoints") == []
    candidates = model_index.list_models(family="sdxl", kind="loras")
    assert len(candidates) == 1
    assert candidates[0]["filename"] == "style.safetensors"


def test_settings_update_preserves_existing_paths_and_unknown_user_fields(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "USER_CONFIG", tmp_path / "config.yaml")
    base = settings.save_settings({
        "models": {
            "sdxl": {"checkpoints": [str(tmp_path / "my-checkpoints")], "loras": []},
        },
        "custom_install_field": {"user_data": "preserve"},
    })
    assert base["custom_install_field"] == {"user_data": "preserve"}
    revised = settings.save_settings({"ui": {"theme": "deep-ocean"}})
    assert revised["models"]["sdxl"]["checkpoints"] == [str(tmp_path / "my-checkpoints")]
    assert revised["custom_install_field"] == {"user_data": "preserve"}
    assert revised["ui"]["theme"] == "deep-ocean"
    assert (tmp_path / "config.yaml").is_file()


def test_new_512px_dolly_draft_preserves_existing_projects_and_uses_unique_ids(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    original = projects.create_animation_project({"name": "Existing User Project"})
    original_path = tmp_path / "projects" / original["id"] / "project.json"
    existing_bytes = original_path.read_bytes()

    payload = {
        "name": "Gentle Dolly In",
        "animation": {
            "mode": "3d", "width": 512, "height": 512,
            "max_frames": 48, "fps": 12,
        },
        "model": {"model_id": "", "family": "", "variant": ""},
        "prompts": {"0": "A single orange cat on a wooden stool"},
        "camera_3d": {"translation_z": "0:(0), 47:(0.5)"},
        "generation": {"seed": 4321, "seed_behavior": "fixed"},
    }
    first = projects.create_animation_project(payload)
    second = projects.create_animation_project(payload)
    assert first["id"] != second["id"]
    assert first["id"] != original["id"]
    assert original_path.read_bytes() == existing_bytes
    assert {first["animation"][key] for key in ("width", "height")} == {512}
    assert first["animation"]["max_frames"] == 48
    assert first["animation"]["fps"] == 12
    assert first["animation"]["mode"] == "3d"
    assert first["camera_3d"]["translation_z"] == "0:(0), 47:(0.5)"
    assert first["tracks"]["camera_3d"]["translation_z"]["schedule"] == (
        first["camera_3d"]["translation_z"]
    )
    assert first["model"]["model_id"] == ""
    assert projects.load_animation_project(original["id"])["name"] == "Existing User Project"

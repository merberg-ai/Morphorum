"""Non-invasive checks for bootstrap and first-run project packaging."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_bootstrap_is_standalone_bat_with_custom_folder_prompt() -> None:
    wrapper = (ROOT / "bootstrap.bat").read_text(encoding="utf-8")
    ps = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")
    assert 'scripts\\bootstrap.ps1' in wrapper
    assert 'Invoke-WebRequest' in wrapper
    assert "C:\\Morphorum" in ps
    assert "Read-Host '  Install folder'" in ps
    assert "[string]$InstallDir" in ps
    assert "$env:MORPHORUM_HOME" in ps
    assert "Existing Morphorum install found" in ps


def test_windows_tasks_share_a_common_themed_console() -> None:
    theme = (ROOT / "scripts" / "ui_windows.ps1").read_text(encoding="utf-8")
    assert "function Show-MorphorumBanner" in theme
    assert "function Write-MorphorumSection" in theme
    assert "ForegroundColor Cyan" in theme
    for script in ("install_windows.ps1", "run_windows.ps1", "update_windows.ps1"):
        data = (ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "ui_windows.ps1" in data
        assert "Show-MorphorumBanner" in data
        assert "Write-MorphorumSection" in data


def test_first_run_template_contains_the_complete_user_example() -> None:
    template = json.loads((ROOT / "config" / "example-project.json").read_text(encoding="utf-8"))
    assert template["name"] == "Default"
    assert template["schema_version"] == 2
    assert template["animation"]["mode"] == "3d"
    assert template["animation"]["max_frames"] == 120
    assert template["animation"]["fps"] == 24
    assert template["prompts"]["0"] == "A fat orange cat wearing a black tophat"
    assert template["prompts"]["30"] == "A fat black cat wearing a red tophat"
    assert template["tracks"]["prompts"]["positive"]["keyframes"][1]["frame"] == 30
    assert template["model"]["model_id"] == ""
    installer = (ROOT / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
    assert "seed-example" in installer
    assert "if (-not $Repair -and -not $Update)" in installer
    linux = (ROOT / "scripts" / "install_linux.sh").read_text(encoding="utf-8")
    assert '"$MODE" == "install"' in linux

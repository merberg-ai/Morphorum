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



def test_windows_bootstrap_uses_subroutine_and_passes_nonempty_script_path() -> None:
    """Regression for CMD early percent expansion inside a parenthesized IF."""
    wrapper = (ROOT / "bootstrap.bat").read_text(encoding="utf-8")
    assert 'call :fetch_bootstrap' in wrapper
    assert ':fetch_bootstrap' in wrapper
    assert 'set "MORPHORUM_BOOTSTRAP_TEMP=%TEMP%' in wrapper
    assert 'set "MORPHORUM_BOOTSTRAP_SCRIPT=%MORPHORUM_BOOTSTRAP_TEMP%"' in wrapper
    assert '-File "%MORPHORUM_BOOTSTRAP_SCRIPT%" %*' in wrapper
    assert 'Invoke-WebRequest' in wrapper
    assert '| Out-Null' in wrapper
    # The standalone fetch must not run inside the parenthesized existence IF.
    assert 'if not exist "%MORPHORUM_BOOTSTRAP_SCRIPT%" call :fetch_bootstrap' in wrapper


def test_windows_port_preference_is_saved_and_runners_accept_overrides() -> None:
    installer = (ROOT / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "run_windows.ps1").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")
    for name, data in [("bootstrap", bootstrap), ("install", installer), ("run", runner)]:
        assert "ValidateRange(1, 65535)" in data, name
    assert "Read-Host '  Server port'" in installer
    assert "server-port.txt" in installer
    assert "Set-Content -LiteralPath $PortFile" in installer
    assert "if (-not $Repair -and -not $Update)" in installer
    assert "server-port.txt" in runner
    assert "PortSource" in runner
    assert "PSBoundParameters.ContainsKey('Port')" in runner
    assert 'if ($PSBoundParameters.ContainsKey(\'Port\')) { & $installer -Port $Port }' in bootstrap
    for bat in ("install.bat", "run.bat", "run-lan.bat"):
        assert "%*" in (ROOT / bat).read_text(encoding="utf-8"), bat
    assert "-Lan %*" in (ROOT / "run-lan.bat").read_text(encoding="utf-8")

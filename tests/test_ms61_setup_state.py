"""MS6.1 setup provenance, no-side-effect API and launcher regressions."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import morphorum.setup_state as setup
import morphorum.cli as cli
from morphorum.app import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    path = tmp_path / "data" / "setup-state.json"
    config = tmp_path / "data" / "config.yaml"
    projects = tmp_path / "projects"
    manifest = tmp_path / "data" / "install.json"
    monkeypatch.setattr(setup, "SETUP_STATE_FILE", path)
    monkeypatch.setattr(setup, "USER_CONFIG", config)
    monkeypatch.setattr(setup, "PROJECTS_DIR", projects)
    monkeypatch.setattr(setup, "INSTALL_MANIFEST", manifest)
    monkeypatch.setattr(setup, "ensure_runtime_dirs", lambda: None)
    monkeypatch.delenv("MORPHORUM_SETUP_WIZARD", raising=False)
    return path, config, projects, manifest


def test_fresh_prepare_happens_before_shipped_config_and_default_seed(isolated):
    path, config, projects, manifest = isolated
    assert setup.setup_status()["status"] == "legacy"
    assert not path.exists(), "GET must not create a setup marker"
    prepared = setup.prepare_install()
    assert prepared["provenance"] == "fresh_installer"
    assert prepared["ready"] is False
    assert setup.setup_status()["show_wizard"] is False
    assert setup.prepare_install() == prepared
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("app: saved", encoding="utf-8")
    projects.mkdir()
    (projects / "existing").mkdir()
    ready = setup.mark_install_ready()
    assert ready["ready"]
    assert ready["revision"] == prepared["revision"] + 1
    status = setup.setup_status()
    assert status["show_wizard"] and status["eligible"]
    assert status["step"] == "welcome"
    assert setup.mark_install_ready() == ready


@pytest.mark.parametrize("prior", ["config", "projects", "manifest"])
def test_legacy_install_without_marker_is_never_forced(isolated, prior):
    path, config, projects, manifest = isolated
    selected = {"config": config, "projects": projects / "user-project",
                "manifest": manifest}[prior]
    if prior == "projects":
        selected.mkdir(parents=True)
        (selected / "project.json").write_text("{}", encoding="utf-8")
    else:
        selected.parent.mkdir(parents=True, exist_ok=True)
        selected.write_text("historic", encoding="utf-8")
    before = selected.read_bytes() if selected.is_file() else (
        selected / "project.json").read_bytes()
    assert setup.prepare_install() is None
    assert setup.mark_install_ready() is None
    assert not path.exists()
    assert not setup.setup_status()["show_wizard"]
    assert setup.setup_status(forced=True)["show_wizard"]
    assert (selected.read_bytes() if selected.is_file() else (
        selected / "project.json").read_bytes()) == before


def test_interrupted_install_cannot_be_forced_into_wizard(isolated):
    path, _, _, _ = isolated
    prepared = setup.prepare_install()
    assert prepared["ready"] is False
    state = setup.setup_status(forced=True)
    assert state["status"] == "not_started"
    assert state["ready"] is False
    assert state["show_wizard"] is False
    with pytest.raises(setup.SetupStateError, match="incomplete"):
        setup.update_setup(action="advance", step="modes",
                           revision=prepared["revision"], forced=True)
    assert json.loads(path.read_text(encoding="utf-8")) == prepared


def test_legacy_override_is_read_only_until_explicit_progress(isolated):
    path, _, _, _ = isolated
    first = setup.setup_status(forced=True)
    second = setup.setup_status(forced=True)
    assert first["show_wizard"] and second["show_wizard"]
    assert not path.exists(), "Forced launch alone cannot change the disk"


def test_progress_resume_skip_and_optimistic_revision(isolated):
    path, _, _, _ = isolated
    setup.prepare_install()
    setup.mark_install_ready()
    initial = setup.setup_status()
    state = setup.update_setup(action="advance", step="modes",
                               revision=initial["revision"])
    assert state["status"] == "in_progress" and state["step"] == "modes"
    assert setup.setup_status()["show_wizard"]
    with pytest.raises(setup.SetupStateConflict):
        setup.update_setup(action="advance", step="models",
                           revision=initial["revision"])
    after = setup.update_setup(action="advance", step="models",
                               revision=state["revision"])
    assert setup.setup_status()["step"] == "models"
    finish = setup.update_setup(action="skip", step=None,
                                revision=after["revision"])
    assert finish["status"] == "skipped"
    assert not setup.setup_status()["show_wizard"]
    assert path.is_file()
    with pytest.raises(setup.SetupStateError):
        setup.update_setup(action="advance", step="welcome",
                           revision=finish["revision"])
    reopened = setup.update_setup(action="advance", step="welcome",
                                  revision=finish["revision"], forced=True)
    assert reopened["status"] == "in_progress"
    assert setup.setup_status()["show_wizard"]


def test_manual_reopen_creates_opt_in_record_without_auto_on_legacy(isolated):
    path, _, _, _ = isolated
    assert not setup.setup_status()["show_wizard"]
    state = setup.update_setup(action="advance", step="modes", revision=0, forced=True)
    assert state["provenance"] == "manual_existing" and path.is_file()
    assert state["step"] == "modes"
    assert not setup.setup_status()["show_wizard"], "manual stays manual"
    setup.update_setup(action="skip", step=None, revision=state["revision"], forced=True)
    assert not setup.setup_status()["show_wizard"]


def test_invalid_corrupt_state_never_overwritten_or_auto_shown(isolated):
    path, _, _, _ = isolated
    path.parent.mkdir(parents=True)
    path.write_text("{invalid-json", encoding="utf-8")
    previous = path.read_bytes()
    assert setup.setup_status()["status"] == "error"
    assert setup.setup_status(forced=True)["show_wizard"] is False
    with pytest.raises(setup.SetupStateError):
        setup.prepare_install()
    with pytest.raises(setup.SetupStateError):
        setup.update_setup(action="skip", step=None, revision=0, forced=True)
    assert path.read_bytes() == previous


@pytest.mark.parametrize("data", [
    {"action": "complete", "step": "finish", "revision": 1},
    {"action": "advance", "step": "../secret", "revision": 1},
    {"action": "advance", "step": "modes", "revision": "1"},
])
def test_state_rejects_unimplemented_completion_invalid_actions(isolated, data):
    setup.prepare_install()
    setup.mark_install_ready()
    with pytest.raises(setup.SetupStateError):
        setup.update_setup(**data)


def test_read_only_status_and_protected_actions_through_http(isolated, monkeypatch):
    path, _, _, _ = isolated
    with TestClient(app) as client:
        legacy = client.get("/api/setup/status")
        assert legacy.status_code == 200
        assert legacy.json()["status"] == "legacy"
        assert not path.exists()
        blocked = client.post("/api/setup/progress", json={
            "action": "advance", "step": "modes", "revision": 0, "manual": True,
        })
        assert blocked.status_code == 403
        setup.prepare_install()
        setup.mark_install_ready()
        status = client.get("/api/setup/status").json()
        assert status["show_wizard"]
        forbidden = client.post("/api/setup/progress",
            json={"action": "skip", "revision": status["revision"]},
            headers={"X-Morphorum-Setup": "1",
                     "Origin": "https://untrusted.example"})
        assert forbidden.status_code == 403
        assert client.get("/api/setup/status").json()["status"] == "not_started"
        ok = client.post("/api/setup/progress",
            json={"action": "advance", "step": "modes", "revision": status["revision"]},
            headers={"X-Morphorum-Setup": "1", "Origin": "http://testserver"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["step"] == "modes"
        assert ok.json()["status"] == "in_progress"
        assert path.is_file()


def test_backend_only_cannot_force_wizard_and_cli_webui_is_default(monkeypatch):
    parser = cli.build_parser()
    args = parser.parse_args(["serve", "--backend-only", "--setup-wizard"])
    assert cli.command_serve(args) == 2
    with patch.object(cli.uvicorn, "run") as runner:
        web = parser.parse_args(["serve", "--setup-wizard"])
        assert cli.command_serve(web) == 0
        assert runner.call_args.args[0] == "morphorum.app:app"
        assert cli.os.getenv("MORPHORUM_SETUP_WIZARD") == "1"
        assert cli.command_serve(parser.parse_args(["serve"])) == 0
        assert cli.os.getenv("MORPHORUM_SETUP_WIZARD") is None
    assert setup.setup_status(forced=True, backend_only=True)["show_wizard"] is False


def test_installer_and_launchers_use_explicit_provenance_and_setup_flag():
    windows = (ROOT / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
    linux = (ROOT / "scripts" / "install_linux.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / "run.bat").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "run_windows.ps1").read_text(encoding="utf-8")
    for content in (windows, linux):
        assert "setup-state prepare" in content
        assert "setup-state ready" in content
        assert content.index("setup-state prepare") < content.index("config.yaml")
        assert content.index("seed-example") < content.index("setup-state ready")
    assert '"--setup-wizard" goto setup_wizard' in wrapper
    assert "[switch]$SetupWizard" in runner
    assert "'--setup-wizard'" in runner
    assert "--setup-wizard" in (ROOT / "backend" / "morphorum" /
                               "cli.py").read_text(encoding="utf-8")


def test_webui_setup_shell_is_present_and_is_separate_from_project_wizard():
    html = (ROOT / "frontend" / "dist" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "dist" / "assets" / "first-run-setup.js").read_text(
        encoding="utf-8")
    for id in ("first-run-overlay", "first-run-next", "first-run-skip",
               "first-run-back", "reopen-first-run-setup"):
        assert html.count(f'id="{id}"') == 1
    assert "first-run-setup.js" in html
    assert "first-run-setup.css" in html
    assert "GET /api/setup/status" not in js  # uses the fetch URL directly
    assert "fetch('/api/setup/status'" in js
    assert "'X-Morphorum-Setup':'1'" in js
    assert "Step " in js
    assert "project-wizard.js" in html

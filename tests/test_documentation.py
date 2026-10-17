"""Keep first-run docs navigable and consistent with shipped runtime scripts."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
GUIDES = [
    "README.md",
    "docs/README.md",
    "docs/GETTING_STARTED.md",
    "docs/NEW_PROJECT_WIZARD.md",
    "docs/INSTALLATION.md",
    "docs/TROUBLESHOOTING.md",
    "docs/FFMPEG_MANAGER.md",
    "docs/CURRENT_STATUS.md",
    "docs/TESTING.md",
    "docs/SDXL_GENERATION.md",
    "docs/G5_RELEASE_ACCEPTANCE.md",
]
MD_LINK = re.compile(r"!?\[[^\]]+\]\(([^)]+)\)")


def test_getting_started_guides_have_valid_local_links_and_fences() -> None:
    for name in GUIDES:
        file = ROOT / name
        content = file.read_text(encoding="utf-8")
        assert "\\" + chr(96) not in content, f"{name} has escaped Markdown backticks"
        assert content.count(chr(96) * 3) % 2 == 0, f"{name} has an unclosed code fence"
        for target in MD_LINK.findall(content):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            local = unquote(target.split("#", 1)[0])
            if not local:
                continue
            assert (file.parent / local).is_file(), (
                f"Broken documentation link in {name}: {target}"
            )


def test_readme_matches_actual_shipped_bootstrap_and_run_scripts() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts/bootstrap.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run_windows.ps1").read_text(encoding="utf-8")
    for script in ("bootstrap.bat", "run.bat", "run-lan.bat",
                   "update.bat", "repair.bat", "scripts/bootstrap.sh"):
        assert (ROOT / script).is_file(), script
    assert "https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat" in readme
    assert r"C:\Morphorum" in readme
    assert "7865" in readme
    assert r"C:\Morphorum" in bootstrap
    assert r"data\server-port.txt" in runner
    for theme in ("Midnight Glass", "Deep Ocean", "Amethyst Night",
                  "Slate Graphite"):
        assert theme in readme


def test_example_and_model_docs_match_packaged_descriptors() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    managed = (ROOT / "backend/morphorum/managed_models.py").read_text(encoding="utf-8")
    assert "Tongyi-MAI/Z-Image-Turbo" in managed
    assert "33 GB" in readme
    assert (ROOT / "config/example-project.json").is_file()
    guide = (ROOT / "docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    assert "120 frames" in guide
    assert "24 FPS" in guide
    assert "Motion Lab" in guide


def test_first_project_wizard_user_docs_track_actual_flow() -> None:
    guide = (ROOT / "docs/NEW_PROJECT_WIZARD.md").read_text(encoding="utf-8")
    wizard = (ROOT / "frontend/dist/assets/project-wizard.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for step in (
        "Welcome & Name",
        "Choose a Model",
        "Animation Setup",
        "Prompts & Keyframes",
        "Camera Motion",
        "Generation Settings",
        "Review & Save",
    ):
        assert step in guide
        assert step in wizard
    for feature in ("Import Motion Settings", "Back", "Next", "Start Over", "Save Project & Open Editor"):
        assert feature in guide
    assert "New Project Wizard" in readme
    assert "NEW_PROJECT_WIZARD.md" in readme
    assert "No generation models available" in readme
    assert "model-setup-banner" in (ROOT / "frontend/dist/index.html").read_text(encoding="utf-8")


def test_managed_ffmpeg_public_docs_track_shipped_manager() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/FFMPEG_MANAGER.md").read_text(encoding="utf-8")
    manager = (ROOT / "backend/morphorum/managed_ffmpeg.py").read_text(encoding="utf-8")
    ui = (ROOT / "frontend/dist/assets/app.js").read_text(encoding="utf-8")
    assert "docs/FFMPEG_MANAGER.md" in readme
    assert "scripts/ffmpeg_acceptance.py" in guide
    assert "tools/ffmpeg/current/bin" in guide
    assert (ROOT / "scripts/ffmpeg_acceptance.py").is_file()
    assert "SHA-256" in guide
    assert "BtbN FFmpeg-Builds" in guide
    assert "GPL" in guide
    for word in ("libx264", "libvpx-vp9", "libopus"):
        assert word in guide and word in manager
    for label in ("Install managed FFmpeg", "Remove managed FFmpeg",
                  "Test FFmpeg / FFprobe"):
        assert label in ui or label in readme


def test_g5_release_guides_distinguish_ci_from_windows_acceptance() -> None:
    """Release docs must link to real guides without claiming GPU validation."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    acceptance = (ROOT / "docs/G5_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    sdxl = (ROOT / "docs/SDXL_GENERATION.md").read_text(encoding="utf-8")
    assert "docs/SDXL_GENERATION.md" in readme
    assert "G5_RELEASE_ACCEPTANCE.md" in index
    assert "NOT TESTED" in acceptance
    assert "Explicit owner approval" in acceptance
    assert "explicitly approved merging" in acceptance.lower()
    assert "not provided separately" in acceptance.lower()
    assert "Not individually recorded" in acceptance
    for feature in ("CLIP-L", "CLIP-G", "Karras", "UNet-only"):
        assert feature in sdxl

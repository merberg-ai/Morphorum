"""Theme palette consistency and persistent appearance preferences."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from morphorum import settings as settings_module

ROOT = Path(__file__).resolve().parents[1]
THEMES = ("midnight-glass", "deep-ocean", "amethyst-night", "slate-graphite")


def test_all_theme_configs_match_backend_options_and_css() -> None:
    css = (ROOT / "frontend/dist/assets/app.css").read_text(encoding="utf-8")
    assert settings_module.UI_THEME_OPTIONS == set(THEMES)
    for theme in THEMES:
        definition = json.loads(
            (ROOT / "config" / "themes" / f"{theme}.json").read_text(encoding="utf-8")
        )
        assert definition["id"] == theme
        assert definition["appearance"] == "dark"
        assert definition["colors"]["accent"].startswith("#")
        assert definition["colors"]["text"].startswith("#")
        if theme != "midnight-glass":
            assert f'html[data-theme="{theme}"]' in css


@pytest.mark.parametrize("theme", THEMES)
def test_theme_and_selected_fonts_persist_without_fallback(
    theme: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "settings.yaml"
    monkeypatch.setattr(settings_module, "USER_CONFIG", config_path)
    settings_module.save_settings({
        "ui": {
            "theme": theme,
            "font_style": "geometric",
            "mono_font_style": "classic-mono",
            "ui_scale": "comfortable",
        },
    })
    loaded = settings_module.load_settings()
    assert loaded["ui"]["theme"] == theme
    assert loaded["ui"]["font_style"] == "geometric"
    assert loaded["ui"]["mono_font_style"] == "classic-mono"
    assert loaded["ui"]["ui_scale"] == "comfortable"

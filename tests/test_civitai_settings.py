from morphorum.settings import _normalize_preferences


def test_civitai_defaults_are_opt_in():
    result = _normalize_preferences({})
    assert result["civitai"] == {
        "enabled": False,
        "allow_mature": False,
        "load_previews": True,
        "auto_check_updates": False,
        "layout": "grid",
        "concurrent_downloads": 1,
    }


def test_civitai_preferences_clamp_untrusted_values():
    result = _normalize_preferences({"civitai": {
        "enabled": "yes",
        "allow_mature": True,
        "layout": "unknown",
        "concurrent_downloads": 100,
    }})
    assert result["civitai"]["enabled"] is False
    assert result["civitai"]["allow_mature"] is True
    assert result["civitai"]["layout"] == "grid"
    assert result["civitai"]["concurrent_downloads"] == 3

from morphorum.settings import _normalize_preferences


def test_context_help_defaults_on_and_remembers_explicit_false():
    assert _normalize_preferences({})["ui"]["show_help_hints"] is True
    assert _normalize_preferences({"ui": {"show_help_hints": False}})["ui"]["show_help_hints"] is False


def test_context_help_normalizes_config_string_values():
    assert _normalize_preferences({"ui": {"show_help_hints": "off"}})["ui"]["show_help_hints"] is False
    assert _normalize_preferences({"ui": {"show_help_hints": "yes"}})["ui"]["show_help_hints"] is True

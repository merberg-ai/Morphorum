import pytest
from morphorum.civitai_download import _safe_file, start_download
from morphorum.civitai_detail import _readable

def test_safe_filename():
    assert _safe_file("portrait.safetensors") == "portrait.safetensors"
    with pytest.raises(ValueError):
        _safe_file("portrait.ckpt")
    with pytest.raises(ValueError):
        _safe_file("../escape.safetensors")
    with pytest.raises(ValueError):
        _safe_file("evil?.safetensors")

def test_hub_disabled_never_reads_remote(monkeypatch):
    monkeypatch.setattr("morphorum.civitai_download.load_settings", lambda: {"civitai": {"enabled": False}})
    with pytest.raises(ValueError, match="disabled"):
        start_download(1, 2, "model.safetensors")

def test_description_preserves_paragraph_and_list_lines():
    text = _readable("<h2>About</h2><p>First paragraph.</p><ul><li>One</li><li>Two</li></ul><script>bad()</script>")
    assert "About\n" in text
    assert "• One" in text
    assert "• Two" in text
    assert "bad()" not in text

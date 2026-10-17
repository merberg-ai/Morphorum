import pytest
from morphorum import civitai_auth

def test_key_storage_never_returns_secret(monkeypatch, tmp_path):
    monkeypatch.setattr(civitai_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(civitai_auth, "SECRET_PATH", tmp_path / ".civitai-token")
    monkeypatch.setattr(civitai_auth, "ensure_runtime_dirs", lambda: None)
    monkeypatch.delenv("CIVITAI_API_TOKEN", raising=False)
    token = "TestToken_123456789"
    result = civitai_auth.store_token(token)
    assert result == {"configured": True, "source": "saved"}
    assert civitai_auth.get_token() == token
    assert token not in str(result)
    assert civitai_auth.clear_token() == {"configured": False, "source": "none"}

def test_invalid_key_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(civitai_auth, "SECRET_PATH", tmp_path / ".civitai-token")
    with pytest.raises(ValueError):
        civitai_auth.store_token("hello?\nSECRET")
    assert not (tmp_path / ".civitai-token").exists()

def test_environment_token_precedence(monkeypatch, tmp_path):
    monkeypatch.setattr(civitai_auth, "SECRET_PATH", tmp_path / ".civitai-token")
    monkeypatch.setenv("CIVITAI_API_TOKEN", "EnvironmentKey123")
    assert civitai_auth.get_token() == "EnvironmentKey123"
    assert civitai_auth.token_status() == {"configured": True, "source": "environment"}

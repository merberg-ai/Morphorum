from fastapi.testclient import TestClient

from morphorum.app import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "Morphorum"
    assert payload["version"]


def test_root_serves_application_shell() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Morphorum" in response.text
    assert "Image Generation" in response.text
    assert "Settings" in response.text
    assert "Console" in response.text

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


def test_root_placeholder() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Morphorum" in response.text
    assert "runtime foundation is installed" in response.text

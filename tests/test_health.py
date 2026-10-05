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


def test_system_telemetry_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/telemetry")
    assert response.status_code == 200
    payload = response.json()
    assert 0 <= payload["cpu_percent"] <= 100
    assert payload["ram"]["total_bytes"] > 0
    assert payload["ram"]["available_bytes"] >= 0
    assert 0 <= payload["ram"]["free_percent"] <= 100
    assert "gpu" in payload
    assert isinstance(payload["gpu"]["devices"], list)

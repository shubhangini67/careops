from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "docs" in data


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "careops-ai-api"


def test_dependencies_health() -> None:
    response = client.get("/api/v1/health/dependencies")
    assert response.status_code == 200
    data = response.json()
    assert "overall_ok" in data
    assert "dependencies" in data
    assert isinstance(data["dependencies"], list)
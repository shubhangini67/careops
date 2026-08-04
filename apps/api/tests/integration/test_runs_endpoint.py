from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_db, get_current_user
from app.main import app

MOCK_USER = {"id": 1, "org_id": 1, "email": "test@test.com", "role": "owner"}


def test_list_runs_endpoint_returns_summaries():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    mock_run = MagicMock()
    with patch("app.api.routes.runs.RunService") as MockService:
        service = MockService.return_value
        service.list_runs.return_value = [mock_run]
        service.to_summary.return_value = {
            "id": 1,
            "scenario": "friday_rush",
            "target_date": "2026-05-08",
            "status": "ready",
            "critic_verdict": "approved",
            "critic_score": 0.91,
            "decision_log_id": 10,
            "generated_at": "2026-04-27T10:00:00",
            "created_at": "2026-04-27T10:01:00",
        }

        response = TestClient(app).get("/api/v1/runs")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["runs"][0]["id"] == 1
    service.list_runs.assert_called_once()


def test_get_run_endpoint_returns_detail():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    mock_run = MagicMock()
    with patch("app.api.routes.runs.RunService") as MockService:
        service = MockService.return_value
        service.get_run.return_value = mock_run
        service.to_detail.return_value = {
            "id": 2,
            "scenario": "friday_rush",
            "target_date": "2026-05-15",
            "status": "needs_review",
            "critic_verdict": "revision",
            "critic_score": 0.7,
            "decision_log_id": 11,
            "generated_at": "2026-04-27T10:00:00",
            "created_at": "2026-04-27T10:01:00",
            "final_response": {"scenario": "friday_rush"},
            "recommendations": {},
            "rag_context": {},
            "critic": {"verdict": "revision"},
            "metadata": {},
        }

        response = TestClient(app).get("/api/v1/runs/2")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["final_response"]["scenario"] == "friday_rush"
    service.get_run.assert_called_once_with(2)

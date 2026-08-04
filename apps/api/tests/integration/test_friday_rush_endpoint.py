"""
Integration tests for the Friday Rush planning endpoint — P1-09.

These tests mock the orchestration layer entirely so no real DB,
LLM, or Qdrant is needed. They verify that the route wires deps
correctly, handles responses, and surfaces errors properly.

Run with:
    cd apps/api && pytest tests/integration/test_friday_rush_endpoint.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_orchestration_deps, get_current_user
import app.api.routes.planning as planning_module  # direct import so patch targets always resolve

MOCK_USER = {"id": 1, "org_id": 1, "email": "test@test.com", "role": "owner"}


# ── Shared mock result ────────────────────────────────────────────────────────

MOCK_FINAL_RESPONSE = {
    "scenario": "friday_rush",
    "target_date": "2026-04-11",
    "status": "ready",
    "generated_at": "2026-04-08T10:00:00+00:00",
    "recommendations": {
        "forecast":    {"recommendation": "Prep for 120 orders", "priority": "high", "reasoning": "", "risks": []},
        "reservation": {"recommendation": "Monitor capacity", "priority": "medium", "reasoning": "", "risks": []},
        "complaint":   {"recommendation": "Fix slow prep", "priority": "high", "reasoning": "", "risks": []},
        "menu":        {"insight": "Focus on Margherita", "promo_candidates": ["Margherita"]},
        "inventory":   {"action": "No alerts. Verify manually."},
    },
    "rag_context": {
        "similar_complaints": [{"text": "pizza was cold", "score": 0.91, "metadata": {}}],
        "relevant_sops": [{"text": "Ensure pizzas are served within 5 min of baking", "score": 0.87, "metadata": {}}],
    },
    "critic": {
        "verdict": "approved",
        "score": 0.85,
        "notes": "All recommendations are within operational bounds.",
        "decision_log_id": 1,
    },
}

# Patch target — always points at the name inside the planning module's own namespace
PATCH_TARGET = "app.api.routes.planning.run_friday_rush"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_deps():
    return {"db": MagicMock(), "llm": MagicMock(), "memory": MagicMock()}


@pytest.fixture
def client(mock_deps):
    """Test client with orchestration deps and auth overridden."""
    app.dependency_overrides[get_orchestration_deps] = lambda: mock_deps
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFridayRushEndpoint:

    def test_successful_response_shape(self, client):
        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value=MOCK_FINAL_RESPONSE)):
            resp = client.post("/api/v1/planning/friday-rush", json={"target_date": "2026-04-11"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario"] == "friday_rush"
        assert data["status"] == "ready"
        assert data["critic"]["verdict"] == "approved"
        assert data["critic"]["decision_log_id"] == 1

    def test_target_date_passed_to_orchestration(self, client):
        mock_run = AsyncMock(return_value=MOCK_FINAL_RESPONSE)
        with patch.object(planning_module, "run_friday_rush", new=mock_run):
            client.post("/api/v1/planning/friday-rush", json={"target_date": "2026-04-11"})

        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["target_date"] == "2026-04-11"

    def test_no_target_date_passes_none(self, client):
        mock_run = AsyncMock(return_value=MOCK_FINAL_RESPONSE)
        with patch.object(planning_module, "run_friday_rush", new=mock_run):
            client.post("/api/v1/planning/friday-rush", json={})

        assert mock_run.call_args.kwargs["target_date"] is None

    def test_recommendations_block_present(self, client):
        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value=MOCK_FINAL_RESPONSE)):
            resp = client.post("/api/v1/planning/friday-rush", json={})

        data = resp.json()
        assert "recommendations" in data
        for key in ("forecast", "reservation", "complaint", "menu", "inventory"):
            assert key in data["recommendations"]

    def test_rag_context_present(self, client):
        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value=MOCK_FINAL_RESPONSE)):
            resp = client.post("/api/v1/planning/friday-rush", json={})

        data = resp.json()
        assert data["rag_context"] is not None
        assert "similar_complaints" in data["rag_context"]
        assert "relevant_sops" in data["rag_context"]

    def test_needs_review_status_returns_200(self, client):
        """HTTP 200 even when critic says needs_review — status is in the body."""
        result = {
            **MOCK_FINAL_RESPONSE,
            "status": "needs_review",
            "critic": {**MOCK_FINAL_RESPONSE["critic"], "verdict": "revision", "score": 0.55},
        }
        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value=result)):
            resp = client.post("/api/v1/planning/friday-rush", json={})

        assert resp.status_code == 200
        assert resp.json()["status"] == "needs_review"

    def test_blocked_status_returns_200(self, client):
        """HTTP 200 even when critic rejects — blocked status is in the body."""
        result = {
            **MOCK_FINAL_RESPONSE,
            "status": "blocked",
            "critic": {**MOCK_FINAL_RESPONSE["critic"], "verdict": "rejected", "score": 0.2},
        }
        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value=result)):
            resp = client.post("/api/v1/planning/friday-rush", json={})

        assert resp.status_code == 200
        assert resp.json()["status"] == "blocked"

    def test_orchestration_exception_returns_500(self, client):
        mock_run = AsyncMock(side_effect=Exception("Gemini timeout"))
        with patch.object(planning_module, "run_friday_rush", new=mock_run):
            resp = client.post("/api/v1/planning/friday-rush", json={})

        assert resp.status_code == 500
        assert "Orchestration failed" in resp.json()["detail"]

    def test_empty_orchestration_result_returns_500(self, client):
        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value={})):
            resp = client.post("/api/v1/planning/friday-rush", json={})

        assert resp.status_code == 500

    def test_meta_timestamp_present(self, client):
        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value=MOCK_FINAL_RESPONSE)):
            resp = client.post("/api/v1/planning/friday-rush", json={})

        assert "meta" in resp.json()
        assert "timestamp" in resp.json()["meta"]

    def test_persists_planning_run_and_returns_run_id_in_meta(self, client):
        persisted_run = MagicMock()
        persisted_run.id = 42

        with patch.object(planning_module, "run_friday_rush", new=AsyncMock(return_value=MOCK_FINAL_RESPONSE)), \
             patch.object(planning_module, "RunService") as MockRunService:
            MockRunService.return_value.create_from_response.return_value = persisted_run
            resp = client.post("/api/v1/planning/friday-rush", json={"target_date": "2026-05-08"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["planning_run_id"] == 42
        MockRunService.return_value.create_from_response.assert_called_once()

"""
Shared fixtures for CareOps AI unit tests.

All fixtures here use mocks only — no real DB, LLM, or Qdrant.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.orchestration.state import make_initial_state


# ── State fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def base_state():
    """Minimal clean state — simulation_mode=False for node tests."""
    return make_initial_state(
        scenario="friday_rush",
        target_date="2026-04-11",
        simulation_mode=False,
        debug=False,
    )


@pytest.fixture
def sim_state():
    """State with simulation_mode=True."""
    return make_initial_state(
        scenario="friday_rush",
        target_date="2026-04-11",
        simulation_mode=True,
    )


@pytest.fixture
def errored_state(base_state):
    return {**base_state, "error": "Upstream failure"}


@pytest.fixture
def populated_state(base_state):
    """Full state with all agent outputs populated."""
    return {
        **base_state,
        "forecast_output": {
            "service": "forecast",
            "data": {"predicted_orders": 120, "avg_friday_orders": 100},
            "recommendation": {
                "recommendation": "Prep for 120 orders",
                "priority": "high",
                "reasoning": "Historical trend",
                "risks": [],
            },
        },
        "reservation_output": {
            "service": "reservation",
            "data": {"total_guests": 65, "capacity": 70, "overbooking_risk": False},
            "recommendation": {
                "recommendation": "Monitor capacity closely",
                "priority": "medium",
                "reasoning": "Near capacity",
                "risks": [],
            },
        },
        "complaint_output": {
            "service": "complaint",
            "data": {
                "total_feedback": 40,
                "sentiment_breakdown": {"negative_pct": 30},
                "unique_complaints": ["slow pizza prep"],
            },
            "recommendation": {
                "recommendation": "Address slow pizza prep",
                "priority": "high",
                "reasoning": "Recurring complaint",
                "risks": [],
            },
            "rag_context": {"similar_complaints": [], "relevant_sops": []},
        },
        "menu_output": {
            "service": "menu",
            "data": {"top_items": [{"item": "Margherita", "total_ordered": 80}]},
            "recommendation": {
                "insight": "Focus on Margherita",
                "promo_candidates": ["Margherita"],
            },
        },
        "inventory_output": {
            "service": "inventory",
            "data": {"shortage_alerts": [], "overstock_alerts": []},
            "recommendation": {"action": "No alerts. Verify manually."},
        },
    }


# ── Infrastructure mocks ──────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_db_factory(mock_db):
    """A db_factory callable — parallel fan-out nodes call this to get their
    own Session. Returns the same mock_db so assertions like
    mock_db.query.assert_called() still work."""
    return MagicMock(return_value=mock_db)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value={
        "recommendation": "Test recommendation",
        "priority": "medium",
        "reasoning": "Mock reasoning",
        "risks": [],
    })
    return llm


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.retrieve_similar_complaints = MagicMock(return_value=[
        {"text": "Pizza was cold", "score": 0.9, "metadata": {}}
    ])
    memory.retrieve_relevant_sops = MagicMock(return_value=[
        {"text": "Serve within 5 min", "score": 0.85, "metadata": {}}
    ])
    return memory

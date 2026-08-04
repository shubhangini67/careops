"""
Unit tests for the LangGraph skeleton — P1-08 acceptance criteria.

These tests verify graph flow, state transitions, and error handling
WITHOUT calling real infrastructure (db, LLM, Qdrant are all mocked).

Run with:
    cd apps/api && pytest tests/unit/test_graph_flow.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.orchestration.state import make_initial_state, OrchestratorState
from app.orchestration.nodes.ops_manager import ops_manager_node
from app.orchestration.nodes.aggregator import aggregator_node, _build_critic_summary
from app.orchestration.nodes.final_assembler import final_assembler_node, _derive_status


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_state() -> OrchestratorState:
    return make_initial_state(scenario="friday_rush", target_date="2026-04-11")


@pytest.fixture
def errored_state(valid_state) -> OrchestratorState:
    return {**valid_state, "error": "Something went wrong upstream"}


@pytest.fixture
def populated_state(valid_state) -> OrchestratorState:
    """State with all agent outputs filled in (mocked)."""
    return {
        **valid_state,
        "forecast_output": {
            "service": "forecast",
            "data": {"predicted_orders": 120},
            "recommendation": {"recommendation": "Prep for 120 orders", "priority": "high", "reasoning": "Historical trend", "risks": []},
        },
        "reservation_output": {
            "service": "reservation",
            "data": {"total_guests": 65, "capacity": 70, "overbooking_risk": False},
            "recommendation": {"recommendation": "Monitor capacity closely", "priority": "medium", "reasoning": "Near capacity", "risks": []},
        },
        "complaint_output": {
            "service": "complaint",
            "data": {"total_feedback": 40, "sentiment_breakdown": {"negative_pct": 30}},
            "recommendation": {"recommendation": "Address slow pizza prep", "priority": "high", "reasoning": "Recurring complaint", "risks": []},
            "rag_context": {"similar_complaints": [], "relevant_sops": []},
        },
        "menu_output": {
            "service": "menu",
            "data": {"top_items": [{"item": "Margherita", "total_ordered": 80}]},
            "recommendation": {"insight": "Focus on Margherita", "promo_candidates": ["Margherita"]},
        },
        "inventory_output": {
            "service": "inventory",
            "data": {"shortage_alerts": [], "overstock_alerts": []},
            "recommendation": {"action": "No alerts. Verify manually."},
        },
    }


# ── ops_manager_node ──────────────────────────────────────────────────────────

class TestOpsManagerNode:

    def test_valid_scenario_passes_through(self, valid_state):
        result = ops_manager_node(valid_state)
        assert result["error"] is None
        assert result["scenario"] == "ed_surge"

    def test_unknown_scenario_sets_error(self, valid_state):
        state = {**valid_state, "scenario": "completely_unknown"}
        result = ops_manager_node(state)
        assert result["error"] is not None
        assert "Unknown scenario" in result["error"]

    def test_preserves_all_other_state_keys(self, valid_state):
        result = ops_manager_node(valid_state)
        assert result["target_date"] == valid_state["target_date"]
        assert result["requested_at"] == valid_state["requested_at"]

    def test_sets_default_target_date_when_missing(self):
        state = make_initial_state(scenario="friday_rush", target_date=None)
        result = ops_manager_node(state)
        assert result["target_date"] is not None
        assert len(result["target_date"]) == 10


# ── aggregator_node ───────────────────────────────────────────────────────────

class TestAggregatorNode:

    def test_short_circuits_on_error(self, errored_state):
        result = aggregator_node(errored_state)
        assert result["aggregated_recommendation"] is None

    def test_builds_bundle_from_populated_state(self, populated_state):
        result = aggregator_node(populated_state)
        bundle = result["aggregated_recommendation"]
        assert bundle is not None
        assert bundle["scenario"] == "friday_rush"
        assert "agents" in bundle
        assert set(bundle["agents"].keys()) == {"forecast", "reservation", "complaint", "menu", "inventory"}

    def test_handles_none_agent_output_gracefully(self, valid_state):
        # Only forecast output is set — rest are None
        state = {**valid_state, "forecast_output": {
            "service": "forecast",
            "data": {"predicted_orders": 100},
            "recommendation": {"recommendation": "Prep for 100 orders", "priority": "high", "reasoning": "", "risks": []},
        }}
        result = aggregator_node(state)
        bundle = result["aggregated_recommendation"]
        assert bundle["agents"]["reservation"]["recommendation"] is None
        assert bundle["agents"]["forecast"]["recommendation"] is not None

    def test_handles_errored_agent_output_gracefully(self, valid_state):
        state = {**valid_state, "forecast_output": {
            "service": "forecast",
            "error": "DB connection failed",
        }}
        result = aggregator_node(state)
        bundle = result["aggregated_recommendation"]
        assert bundle["agents"]["forecast"]["recommendation"] == {"error": "DB connection failed"}

    def test_critic_summary_is_string(self, populated_state):
        result = aggregator_node(populated_state)
        summary = result["aggregated_recommendation"]["summary_for_critic"]
        assert isinstance(summary, str)
        assert "friday_rush" in summary

    def test_critic_summary_avoids_raw_inventory_dict_dump(self, populated_state):
        state = {
            **populated_state,
            "inventory_output": {
                "service": "inventory",
                "data": {"shortage_alerts": [], "overstock_alerts": []},
                "recommendation": {
                    "restock_actions": ["Order 5kg mozzarella immediately"],
                    "waste_reduction_actions": ["Use basil in lunch special"],
                    "reasoning": "Critical ingredients need a same-day top-up.",
                },
            },
        }
        result = aggregator_node(state)
        summary = result["aggregated_recommendation"]["summary_for_critic"]
        assert "Order 5kg mozzarella immediately" in summary
        assert "Use basil in lunch special" in summary


# ── final_assembler_node ──────────────────────────────────────────────────────

class TestFinalAssemblerNode:

    def test_assembles_valid_response(self, populated_state):
        state = {
            **populated_state,
            "aggregated_recommendation": {"scenario": "friday_rush"},
            "critic_output": {
                "verdict": "approved",
                "score": 0.85,
                "notes": "All good",
                "decision_log_id": 42,
            },
        }
        result = final_assembler_node(state)
        resp = result["final_response"]

        assert resp["scenario"] == "friday_rush"
        assert resp["status"] == "ready"
        assert resp["critic"]["verdict"] == "approved"
        assert resp["critic"]["decision_log_id"] == 42

    def test_status_ready_for_approved_high_score(self):
        assert _derive_status({"verdict": "approved", "score": 0.9}) == "ready"

    def test_status_blocked_for_rejected(self):
        assert _derive_status({"verdict": "rejected", "score": 0.2}) == "blocked"

    def test_status_needs_review_for_revision(self):
        assert _derive_status({"verdict": "revision", "score": 0.5}) == "needs_review"

    def test_status_needs_review_for_low_score_approved(self):
        assert _derive_status({"verdict": "approved", "score": 0.5}) == "needs_review"

    def test_handles_missing_critic_output(self, valid_state):
        state = {**valid_state, "aggregated_recommendation": {}, "critic_output": None}
        result = final_assembler_node(state)
        resp = result["final_response"]
        assert resp["status"] == "unknown"
        assert resp["critic"]["verdict"] == "unknown"

    def test_includes_rag_context_in_response(self, populated_state):
        state = {
            **populated_state,
            "aggregated_recommendation": {},
            "critic_output": {"verdict": "approved", "score": 0.8, "notes": ""},
        }
        result = final_assembler_node(state)
        assert result["final_response"]["rag_context"] is not None


# ── make_initial_state ────────────────────────────────────────────────────────

class TestMakeInitialState:

    def test_all_output_fields_are_none(self):
        state = make_initial_state("friday_rush")
        output_keys = [
            "forecast_output", "reservation_output", "complaint_output",
            "menu_output", "inventory_output", "aggregated_recommendation",
            "critic_output", "final_response", "error",
        ]
        for key in output_keys:
            assert state[key] is None, f"Expected {key} to be None"

    def test_requested_at_is_iso_string(self):
        state = make_initial_state("friday_rush")
        # Should not raise
        datetime.fromisoformat(state["requested_at"])

    def test_target_date_is_set(self):
        state = make_initial_state("friday_rush", target_date="2026-04-11")
        assert state["target_date"] == "2026-04-11"

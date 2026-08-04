"""
Unit tests for P6-S04 Agent Intelligence Bundle.

Covers:
  - Aggregator contradiction detection (0 LLM calls)
  - Aggregator replan_context injection
  - replan_orchestrator_node state transitions
  - Critic replanning conditional routing
  - Proactive pattern surfacing (chat_service)
  - Semantic chat cache (SemanticChatCache)
  - Session memory summary builder
"""

import pytest
from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _base_state(**overrides):
    state = {
        "scenario": "friday_rush",
        "scenario_profile": None,
        "target_date": "2026-06-27",
        "requested_at": "2026-06-27T00:00:00+00:00",
        "org_id": 1,
        "org_capacity": 70,
        "org_peak_hours": "18:00-22:00",
        "restaurant_profile": None,
        "simulation_mode": False,
        "force_critic_decision": None,
        "debug": False,
        "forecast_output": None,
        "reservation_output": None,
        "complaint_output": None,
        "menu_output": None,
        "inventory_output": None,
        "menu_assumptions": None,
        "inventory_assumptions": None,
        "reservation_assumptions": None,
        "complaint_assumptions": None,
        "aggregated_recommendation": None,
        "critic_output": None,
        "final_response": None,
        "execution_trace": [],
        "llm_registry": None,
        "replan_count": 0,
        "replan_context": None,
        "shared_context": None,
        "error": None,
    }
    state.update(overrides)
    return state


# ──────────────────────────────────────────────────────────────────────────────
# 1. Contradiction detection — _detect_contradictions
# ──────────────────────────────────────────────────────────────────────────────

from app.orchestration.nodes.aggregator import _detect_contradictions


class TestContradictionDetection:

    def test_no_contradictions_when_no_data(self):
        state = _base_state()
        result = _detect_contradictions(state)
        assert result == ""

    def test_inventory_blocker_contradiction(self):
        state = _base_state(
            menu_output={
                "recommendation": {
                    "highlight_items": ["Margherita"],
                    "inventory_blockers": ["Mozzarella is below safe Friday stock"],
                }
            }
        )
        result = _detect_contradictions(state)
        assert "DETECTED CONTRADICTIONS" in result
        assert "Mozzarella is below safe Friday stock" in result

    def test_highlight_vs_low_stock_name_overlap(self):
        state = _base_state(
            menu_output={
                "recommendation": {
                    "highlight_items": ["Mozzarella Sticks"],
                    "inventory_blockers": [],
                }
            },
            inventory_assumptions={
                "items_flagged_low": ["Mozzarella"],
                "items_flagged_overstock": [],
            },
        )
        result = _detect_contradictions(state)
        assert "DETECTED CONTRADICTIONS" in result
        assert "Mozzarella Sticks" in result
        assert "LOW STOCK" in result

    def test_critical_shortage_plus_high_demand(self):
        state = _base_state(
            inventory_output={
                "data": {
                    "shortage_alerts": [
                        {"ingredient": "Tomatoes", "severity": "critical"}
                    ],
                    "overstock_alerts": [],
                    "demand_ratio": 1.4,
                }
            },
            forecast_output={
                "data": {"demand_ratio": 1.4},
                "recommendation": {},
            },
        )
        result = _detect_contradictions(state)
        assert "DETECTED CONTRADICTIONS" in result
        assert "Tomatoes" in result
        assert "1.4x" in result

    def test_no_contradiction_low_demand_ratio(self):
        state = _base_state(
            inventory_output={
                "data": {
                    "shortage_alerts": [
                        {"ingredient": "Basil", "severity": "critical"}
                    ],
                    "demand_ratio": 0.9,
                }
            },
            forecast_output={"data": {"demand_ratio": 0.9}, "recommendation": {}},
        )
        result = _detect_contradictions(state)
        # demand_ratio <= 1.1 → no high-demand contradiction
        assert "Basil" not in result

    def test_no_contradiction_non_critical_shortage(self):
        state = _base_state(
            inventory_output={
                "data": {
                    "shortage_alerts": [
                        {"ingredient": "Oregano", "severity": "low"}
                    ],
                    "demand_ratio": 1.5,
                }
            },
            forecast_output={"data": {"demand_ratio": 1.5}, "recommendation": {}},
        )
        result = _detect_contradictions(state)
        assert "Oregano" not in result

    def test_multiple_contradictions_all_included(self):
        state = _base_state(
            menu_output={
                "recommendation": {
                    "highlight_items": ["Mozzarella Focaccia"],
                    "inventory_blockers": ["Mozzarella stock critically low"],
                }
            },
            inventory_assumptions={
                "items_flagged_low": ["Mozzarella"],
                "items_flagged_overstock": [],
            },
        )
        result = _detect_contradictions(state)
        assert result.count("⚠") >= 2

    def test_returns_empty_string_not_none(self):
        result = _detect_contradictions(_base_state())
        assert isinstance(result, str)
        assert result == ""


# ──────────────────────────────────────────────────────────────────────────────
# 2. Aggregator — replan_context injection
# ──────────────────────────────────────────────────────────────────────────────

from app.orchestration.nodes.aggregator import _build_critic_summary


class TestAggregatorReplanContext:

    def test_replan_context_appended_to_summary(self):
        state = _base_state(replan_context="[Replan attempt 1] score=0.4")
        summary = _build_critic_summary(state)
        assert "CRITIC FEEDBACK FROM PREVIOUS EVALUATION" in summary
        assert "[Replan attempt 1] score=0.4" in summary

    def test_no_replan_context_no_section(self):
        state = _base_state()
        summary = _build_critic_summary(state)
        assert "CRITIC FEEDBACK" not in summary

    def test_live_signals_section_present_when_any_signal_available(self):
        """P6-A24: weather/trends/compliance (none is Swiggy MCP) each
        contribute independently -- any subset present still produces a
        [Live Signals] line."""
        state = _base_state(
            weather_signal={"signal": "Clear conditions expected"},
            trends_signal={"digest": "Mustard oil prices rising"},
            compliance_alerts_signal={"notices": [{"title": "Vegan labelling rule"}]},
        )
        summary = _build_critic_summary(state)
        assert "[Live Signals]" in summary
        assert "Weather: Clear conditions expected" in summary
        assert "Industry trends noted" in summary
        assert "1 recent FSSAI notice(s)" in summary

    def test_live_signals_section_omitted_when_none_available(self):
        state = _base_state()
        summary = _build_critic_summary(state)
        assert "[Live Signals]" not in summary

    def test_live_signals_partial_availability_does_not_crash(self):
        """One source (trends) present, the other two absent -- must still
        produce a valid, non-crashing summary containing just that one."""
        state = _base_state(trends_signal={"digest": "Some trend"})
        summary = _build_critic_summary(state)
        assert "[Live Signals] Industry trends noted" in summary


# ──────────────────────────────────────────────────────────────────────────────
# 3. replan_orchestrator_node
# ──────────────────────────────────────────────────────────────────────────────

from app.orchestration.nodes.replan_orchestrator import replan_orchestrator_node


class TestReplanOrchestratorNode:

    def test_increments_replan_count(self):
        state = _base_state(
            replan_count=0,
            critic_output={"verdict": "rejected", "score": 0.3, "revision_reasons": []},
        )
        result = replan_orchestrator_node(state)
        assert result["replan_count"] == 1

    def test_increments_from_existing_count(self):
        state = _base_state(
            replan_count=1,
            critic_output={"verdict": "revision", "score": 0.5},
        )
        result = replan_orchestrator_node(state)
        assert result["replan_count"] == 2

    def test_does_not_explicitly_clear_critic_output(self):
        # Every OrchestratorState field uses the keep_last reducer (if new is
        # None: return current), so an explicit "critic_output": None here would
        # be a no-op under the real graph anyway — critic_node overwrites it
        # unconditionally on its next run. The node correctly leaves it alone.
        critic_output = {"verdict": "rejected", "score": 0.1}
        state = _base_state(critic_output=critic_output)
        result = replan_orchestrator_node(state)
        assert result["critic_output"] == critic_output

    def test_captures_revision_reasons_in_context(self):
        state = _base_state(
            critic_output={
                "verdict": "revision",
                "score": 0.4,
                "revision_reasons": ["Inventory contradicts menu", "Score too low"],
            },
        )
        result = replan_orchestrator_node(state)
        assert "Inventory contradicts menu" in result["replan_context"]
        assert "Score too low" in result["replan_context"]

    def test_accumulates_context_across_replans(self):
        state = _base_state(
            replan_count=1,
            replan_context="[Replan attempt 1] something",
            critic_output={
                "verdict": "revision",
                "score": 0.5,
                "revision_reasons": ["Still contradicting"],
            },
        )
        result = replan_orchestrator_node(state)
        assert "[Replan attempt 1] something" in result["replan_context"]
        assert "Still contradicting" in result["replan_context"]
        assert result["replan_count"] == 2

    def test_handles_missing_critic_output(self):
        state = _base_state(critic_output=None)
        result = replan_orchestrator_node(state)
        assert result["replan_count"] == 1
        assert result["critic_output"] is None


# ──────────────────────────────────────────────────────────────────────────────
# 4. Critic replanning routing logic
# ──────────────────────────────────────────────────────────────────────────────

from app.orchestration.graph import _route_after_critic, FINAL_ASSEMBLER, REPLAN_ORCHESTRATOR


class TestRoutingAfterCritic:

    def test_approved_goes_to_final_assembler(self):
        state = _base_state(
            critic_output={"verdict": "approved", "score": 0.9},
            replan_count=0,
        )
        assert _route_after_critic(state) == FINAL_ASSEMBLER

    def test_rejected_with_retries_remaining_goes_to_replan(self):
        state = _base_state(
            critic_output={"verdict": "rejected", "score": 0.3},
            replan_count=0,
        )
        assert _route_after_critic(state) == REPLAN_ORCHESTRATOR

    def test_revision_with_retries_remaining_goes_to_replan(self):
        state = _base_state(
            critic_output={"verdict": "revision", "score": 0.5},
            replan_count=1,
        )
        assert _route_after_critic(state) == REPLAN_ORCHESTRATOR

    def test_rejected_at_max_retries_goes_to_final_assembler(self):
        state = _base_state(
            critic_output={"verdict": "rejected", "score": 0.2},
            replan_count=2,
        )
        assert _route_after_critic(state) == FINAL_ASSEMBLER

    def test_revision_at_max_retries_goes_to_final_assembler(self):
        state = _base_state(
            critic_output={"verdict": "revision", "score": 0.4},
            replan_count=2,
        )
        assert _route_after_critic(state) == FINAL_ASSEMBLER

    def test_none_critic_output_routes_to_replan(self):
        state = _base_state(critic_output=None, replan_count=0)
        # Default verdict is "revision" when no output
        assert _route_after_critic(state) == REPLAN_ORCHESTRATOR


# ──────────────────────────────────────────────────────────────────────────────
# 5. Proactive pattern surfacing
# ──────────────────────────────────────────────────────────────────────────────

from app.domain.services.chat_service import get_recurring_failures


class TestProactivePatterns:

    def _mock_run(self, verdict: str, scenario: str = "friday_rush"):
        r = MagicMock()
        r.critic_verdict = verdict
        r.scenario = scenario
        return r

    def test_no_warning_when_all_approved(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            self._mock_run("approved"),
            self._mock_run("approved"),
            self._mock_run("approved"),
        ]
        result = get_recurring_failures(1, db)
        assert result is None

    def test_warning_when_2_of_5_non_approved(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            self._mock_run("rejected"),
            self._mock_run("approved"),
            self._mock_run("revision"),
            self._mock_run("approved"),
            self._mock_run("approved"),
        ]
        result = get_recurring_failures(1, db)
        assert result is not None
        assert "Pattern detected" in result

    def test_no_warning_when_only_1_non_approved(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            self._mock_run("rejected"),
            self._mock_run("approved"),
            self._mock_run("approved"),
        ]
        result = get_recurring_failures(1, db)
        assert result is None

    def test_returns_none_on_fewer_than_2_runs(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            self._mock_run("rejected"),
        ]
        result = get_recurring_failures(1, db)
        assert result is None

    def test_graceful_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB down")
        result = get_recurring_failures(1, db)
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# 6. Session memory summary builder
# ──────────────────────────────────────────────────────────────────────────────

from app.infrastructure.vector.session_memory import SessionMemoryService


class TestSessionMemorySummaryBuilder:

    def test_builds_summary_from_inventory_keywords(self):
        messages = [
            {"role": "user",      "content": "What is the inventory shortage?"},
            {"role": "assistant", "content": "Mozzarella stock is low."},
        ]
        summary = SessionMemoryService.build_summary_from_messages(
            messages, "What is the inventory shortage?"
        )
        assert "inventory" in summary

    def test_builds_summary_with_multiple_topics(self):
        messages = [
            {"role": "user",      "content": "Show me demand forecast and menu highlights"},
            {"role": "assistant", "content": "Demand is high, Margherita is highlighted"},
        ]
        summary = SessionMemoryService.build_summary_from_messages(messages, "demand forecast")
        assert "demand" in summary
        assert "menu" in summary

    def test_includes_last_question_in_summary(self):
        messages = [{"role": "user", "content": "What is the reservation count?"}]
        summary = SessionMemoryService.build_summary_from_messages(messages, "reservation count?")
        assert "reservation count?" in summary

    def test_empty_messages_returns_valid_summary(self):
        summary = SessionMemoryService.build_summary_from_messages([], "hello")
        assert isinstance(summary, str)
        assert len(summary) > 0

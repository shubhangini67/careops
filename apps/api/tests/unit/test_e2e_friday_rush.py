"""
E2E unit test for the CareOps LangGraph pipeline.

Exercises the 7-agent hospital graph (supervisor_router → fan-out → aggregator →
safety_critic → human_approval_queue) using simulation_mode=True and
force_critic_decision so no real DB, LLM, or Qdrant is needed.

Legacy restaurant pipeline tests were replaced when build_graph() switched to
the CareOps graph.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.orchestration.graph import build_graph, run_friday_rush
from app.orchestration.state import make_initial_state


# ── Shared mock deps ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_deps():
    return {
        "db": MagicMock(),
        "llm": MagicMock(),
        "memory": MagicMock(),
    }


# ── Happy path — simulation + override ───────────────────────────────────────

class TestFridayRushE2E:

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_final_response(self, mock_deps):
        """Complete graph run returns a well-shaped final_response dict."""
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        assert isinstance(result, dict)
        assert result.get("scenario") == "ed_surge"
        assert result.get("status") in {"ready", "needs_review", "blocked", "unknown"}

    @pytest.mark.asyncio
    async def test_approved_critic_produces_ready_status(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        assert result["critic"]["verdict"] == "approved"
        assert result["status"] == "ready"

    @pytest.mark.asyncio
    async def test_rejected_critic_produces_blocked_status(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="rejected",
        )

        assert result["critic"]["verdict"] == "rejected"
        assert result["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_revision_critic_produces_needs_review_status(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="revision",
        )

        assert result["critic"]["verdict"] == "revision"
        assert result["status"] == "needs_review"

    @pytest.mark.asyncio
    async def test_all_agent_keys_present_in_recommendations(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        recs = result.get("recommendations", {})
        for key in ("forecast", "reservation", "complaint", "menu", "inventory"):
            assert key in recs, f"Missing recommendations key: {key}"

    @pytest.mark.asyncio
    async def test_forecast_recommendation_includes_data(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        forecast = result.get("recommendations", {}).get("forecast")
        assert isinstance(forecast, dict)
        assert "data" in forecast
        assert "forecast_24h" in forecast["data"] or "predicted_orders" in forecast["data"]

    def test_final_assembler_keeps_complaint_data_with_recommendation(self):
        from app.orchestration.nodes.final_assembler import final_assembler_node

        state = {
            "scenario": "friday_rush",
            "target_date": "2026-04-11",
            "critic_output": {"verdict": "approved", "score": 0.9, "notes": "", "decision_log_id": 1},
            "aggregated_recommendation": {},
            "complaint_output": {
                "service": "complaint",
                "data": {
                    "total_feedback": 12,
                    "unique_complaints": ["cold pizza"],
                    "sentiment_breakdown": {"negative": 3, "positive": 7, "neutral": 2, "negative_pct": 25.0},
                },
                "recommendation": {
                    "issues": [{"issue": "cold pizza", "frequency": "3 reports", "recommendation": "speed up pass", "priority": "high"}],
                    "overall_summary": "Temperature complaints need attention.",
                    "action_items": ["Audit pass timing"],
                },
            },
        }

        result = final_assembler_node(state)
        complaint = result["final_response"]["recommendations"]["complaint"]
        assert isinstance(complaint, dict)
        assert complaint["data"]["total_feedback"] == 12

    @pytest.mark.asyncio
    async def test_rag_context_present_in_response(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        # Phase 2: rag_context is present (may be empty in simulation)
        assert "rag_context" in result
        assert isinstance(result["rag_context"], dict)

    @pytest.mark.asyncio
    async def test_target_date_present_in_response(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        assert result.get("target_date") == "2026-04-11"

    @pytest.mark.asyncio
    async def test_generated_at_timestamp_present(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_meta_block_present(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
        )

        assert "meta" in result
        assert "run_id" in result["meta"]


# ── Error-abort path ──────────────────────────────────────────────────────────

class TestErrorAbortPath:

    @pytest.mark.asyncio
    async def test_unknown_scenario_skips_to_final_assembler(self, mock_deps):
        """ops_manager error → graph skips agents → returns unknown/blocked response."""
        graph = build_graph(mock_deps)

        bad_state = make_initial_state(
            scenario="completely_unknown_scenario",
            simulation_mode=True,
        )
        final_state = await graph.ainvoke(bad_state)

        # Graph should have set an error and produced a final_response
        assert final_state.get("error") is not None
        final = final_state.get("final_response")
        assert final is not None
        # Agent outputs should all be None — they were skipped
        assert final_state["forecast_output"] is None
        assert final_state["reservation_output"] is None

    @pytest.mark.asyncio
    async def test_error_response_has_valid_status(self, mock_deps):
        graph = build_graph(mock_deps)

        bad_state = make_initial_state(scenario="invalid", simulation_mode=True)
        final_state = await graph.ainvoke(bad_state)

        final = final_state.get("final_response", {})
        assert final.get("status") in {"ready", "needs_review", "blocked", "unknown"}


# ── Debug observability ───────────────────────────────────────────────────────

class TestDebugObservability:

    @pytest.mark.asyncio
    async def test_debug_mode_adds_meta_block(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
            debug=True,
        )

        meta = result.get("meta", {})
        assert meta.get("debug") is True
        assert meta.get("simulation_mode") is True

    @pytest.mark.asyncio
    async def test_debug_mode_includes_execution_trace(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
            debug=True,
        )

        trace = result.get("meta", {}).get("node_traces", [])
        assert isinstance(trace, list)
        node_names = [entry["node"] for entry in trace]
        assert "capacity_forecast" in node_names
        assert "safety_critic" in node_names

    @pytest.mark.asyncio
    async def test_no_debug_meta_without_flag(self, mock_deps):
        result = await run_friday_rush(
            deps=mock_deps,
            target_date="2026-04-11",
            simulation_mode=True,
            force_critic_decision="approved",
            debug=False,
        )

        meta = result.get("meta", {})
        assert meta.get("debug") is not True

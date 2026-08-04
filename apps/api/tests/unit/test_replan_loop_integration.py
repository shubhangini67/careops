"""
Graph-level integration test for the replan loop (post-fix).

Regression guard for the bug found via a live run: replan_orchestrator only
re-ran the aggregator, never menu_intelligence, so the critic was shown the
exact same menu_output on every retry and rejected it again and again — the
loop could never converge. This drives the actual compiled graph (not just
individual node functions) with every domain service mocked, forces the critic
to return "revision" on the first pass, and asserts:

  1. MenuService.analyse_and_recommend is called a SECOND time on replan (not
     just the aggregator re-synthesizing the same unchanged output), and
  2. the second call's prior_feedback carries the first critic verdict's
     revision reasons through to the prompt.

Run with: pytest tests/unit/test_replan_loop_integration.py -v
"""

import pytest

pytestmark = pytest.mark.skip(reason="Replan loop applies to legacy restaurant graph only — CareOps graph has no replan_orchestrator.")

from unittest.mock import AsyncMock, MagicMock, patch

from app.orchestration.graph import run_planning_scenario


FORECAST_RESULT = {
    "service": "forecast",
    "data": {"predicted_orders": 90, "avg_friday_orders": 88, "demand_ratio": 1.02},
    "recommendation": {"recommendation": "Prep for steady demand.", "priority": "medium", "reasoning": "", "risks": []},
}
RESERVATION_RESULT = {
    "service": "reservation",
    "data": {"total_guests": 60, "capacity": 70, "occupancy_pct": 85, "waitlist_count": 0},
    "recommendation": {"recommendation": "Manage seating carefully.", "priority": "medium", "reasoning": "", "risks": []},
}
COMPLAINT_SUMMARY = {
    "total_feedback": 10,
    "sentiment_breakdown": {"negative_pct": 10, "positive": 8, "neutral": 1, "negative": 1},
    "unique_complaints": ["slow service"],
    "unique_positives": [],
}
COMPLAINT_RESULT = {
    "service": "complaint",
    "data": COMPLAINT_SUMMARY,
    "recommendation": {"action_items": ["Speed up service"], "overall_summary": "Minor issues.", "issues": []},
}
INVENTORY_RESULT = {
    "service": "inventory",
    "data": {"shortage_alerts": [], "overstock_alerts": [], "total_items_checked": 5, "high_demand_week": False, "demand_ratio": 1.0},
    "recommendation": {"restock_actions": [], "waste_reduction_actions": [], "priority": "low", "reasoning": "", "risks": []},
}
MENU_RESULT = {
    "service": "menu",
    "data": {"top_items": [{"item": "Margherita", "total_ordered": 40}], "shortage_ingredients": [], "overstock_ingredients": []},
    "recommendation": {"highlight_items": ["Margherita"], "deprioritize_items": [], "promo_candidates": [], "reasoning": "Push the classics.", "priority": "medium"},
}

CRITIC_REVISION = {
    "verdict": "revision",
    "score": 0.4,
    "notes": "No confirmed go-list of executable menu items given the shortages.",
    "revision_reasons": ["No confirmed go-list of executable menu items given the shortages."],
    "actionable_feedback": ["Name a confirmed alternative dish, not just acknowledge the shortage."],
    "decision_log_id": 1,
    "sanity_checks": {"issues": [], "passed": True, "summary": "0 errors, 0 warnings", "stale_assumptions": []},
    "cost_analysis": {},
    "dimension_scores": {"safety": 0.5, "feasibility": 0.4, "evidence": 0.5, "actionability": 0.4, "clarity": 0.5},
    "stale_assumptions": [],
}
CRITIC_APPROVED = {
    "verdict": "approved",
    "score": 0.85,
    "notes": "Confirmed go-list now present.",
    "revision_reasons": [],
    "actionable_feedback": [],
    "decision_log_id": 2,
    "sanity_checks": {"issues": [], "passed": True, "summary": "0 errors, 0 warnings", "stale_assumptions": []},
    "cost_analysis": {},
    "dimension_scores": {"safety": 0.9, "feasibility": 0.85, "evidence": 0.85, "actionability": 0.85, "clarity": 0.85},
    "stale_assumptions": [],
}


@pytest.mark.asyncio
async def test_replan_reruns_menu_intelligence_with_prior_feedback():
    mock_db = MagicMock()
    mock_db_factory = MagicMock(return_value=mock_db)
    mock_llm = MagicMock()
    mock_llm.drain_usage = MagicMock(return_value=[])

    mock_swiggy_client = MagicMock()
    mock_swiggy_client.is_available.return_value = False

    with (
        patch("app.orchestration.nodes.demand_forecast.ForecastService") as MockForecast,
        patch("app.orchestration.nodes.reservation.ReservationService") as MockReservation,
        patch("app.orchestration.nodes.complaint_intelligence.ComplaintService") as MockComplaint,
        patch("app.orchestration.nodes.inventory.InventoryService") as MockInventory,
        patch("app.orchestration.nodes.menu_intelligence.MenuService") as MockMenu,
        patch("app.orchestration.nodes.critic.CriticService") as MockCritic,
    ):
        MockForecast.return_value.analyse_and_recommend = AsyncMock(return_value=FORECAST_RESULT)
        MockReservation.return_value.analyse_and_recommend = AsyncMock(return_value=RESERVATION_RESULT)
        MockComplaint.return_value.get_complaint_summary = MagicMock(return_value=COMPLAINT_SUMMARY)
        MockComplaint.return_value.analyse_and_recommend = AsyncMock(return_value=COMPLAINT_RESULT)
        MockInventory.return_value.analyse_and_recommend = AsyncMock(return_value=INVENTORY_RESULT)
        MockMenu.return_value.analyse_and_recommend = AsyncMock(return_value=MENU_RESULT)
        MockCritic.return_value.evaluate_and_log = AsyncMock(side_effect=[CRITIC_REVISION, CRITIC_APPROVED])

        deps = {
            "db": mock_db,
            "db_factory": mock_db_factory,
            "llm": mock_llm,
            "swiggy_client": mock_swiggy_client,
        }

        response = await run_planning_scenario(
            deps=deps,
            scenario="friday_rush",
            target_date="2026-04-11",
            org_id=1,
        )

    # The loop must have actually converged to approved, not exhausted retries.
    assert response["critic"]["verdict"] == "approved"

    # MenuService must be regenerated on replan — called twice, not once.
    menu_calls = MockMenu.return_value.analyse_and_recommend.call_args_list
    assert len(menu_calls) == 2, (
        "menu_intelligence must re-run on replan so the plan actually changes "
        "before being resubmitted to the critic — the old bug re-synthesized "
        "the same unchanged menu_output on every retry."
    )

    # First pass has no prior feedback yet.
    assert menu_calls[0].kwargs["prior_feedback"] is None

    # Second pass must carry the first critic verdict's feedback through.
    second_call_feedback = menu_calls[1].kwargs["prior_feedback"]
    assert second_call_feedback is not None
    assert "No confirmed go-list of executable menu items" in second_call_feedback

    # Critic must have been invoked exactly twice (initial + one replan).
    assert MockCritic.return_value.evaluate_and_log.await_count == 2

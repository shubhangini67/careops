from unittest.mock import AsyncMock, MagicMock

import pytest


def _valid_bundle() -> dict:
    return {
        "scenario": "friday_rush",
        "target_date": "2026-05-01",
        "summary_for_critic": "Scenario: friday_rush | Date: 2026-05-01",
        "agents": {
            "forecast": {"data": {"predicted_orders": 120}, "recommendation": {"recommendation": "Prep for demand.", "priority": "high", "risks": []}},
            "reservation": {"data": {"total_guests": 61}, "recommendation": {"recommendation": "Hold peak waitlist.", "priority": "medium", "risks": []}},
            "complaint": {"data": {"total_feedback": 20}, "recommendation": {"action_items": ["Check pizza temperature"]}},
            "menu": {"data": {"top_items": []}, "recommendation": {"highlight_items": ["Margherita"], "priority": "medium"}},
            "inventory": {
                "data": {
                    "shortage_alerts": [
                        {
                            "ingredient": "Mozzarella Cheese",
                            "unit": "kg",
                            "quantity_in_stock": 3.5,
                            "shortfall": 4.5,
                        }
                    ],
                    "overstock_alerts": [],
                },
                "recommendation": {
                    "restock_actions": ["Order 4.5kg Mozzarella Cheese within 24 hours"],
                    "priority": "high",
                    "risks": ["Stockout"],
                },
            },
        },
    }


def test_sanity_checker_passes_valid_bundle():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    result = EvaluationSanityChecker().check_bundle(_valid_bundle())

    assert result["passed"] is True
    assert result["issues"] == []


def test_sanity_checker_reports_schema_issues():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    result = EvaluationSanityChecker().check_bundle({"scenario": "friday_rush"})

    assert result["passed"] is False
    assert any(issue["code"] == "schema.missing_key" for issue in result["issues"])


# ── Diff 2 (menu capacity vs reservation occupancy) ──────────────────────────
# Regression coverage for the bug found via a live run: menu_intelligence used
# to hardcode assumed_covers_within_capacity=True on every run, so Diff 2 fired
# on nearly every high-occupancy Friday Rush plan regardless of quality. Now
# that menu genuinely computes it from reservation's own occupancy figure
# (same >90% threshold), the two sides of the diff should stay consistent.

def test_diff_2_does_not_fire_when_menu_correctly_reports_constrained():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    bundle = _valid_bundle()
    bundle["assumptions"] = {
        "menu":        {"assumed_covers_within_capacity": False},  # genuinely constrained
        "reservation": {"assumed_peak_occupancy_pct": 99.1},
    }
    result = EvaluationSanityChecker().check_bundle(bundle)

    assert result["stale_assumptions"] == []


def test_diff_2_still_fires_if_menu_wrongly_claims_capacity_is_fine():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    bundle = _valid_bundle()
    bundle["assumptions"] = {
        "menu":        {"assumed_covers_within_capacity": True},  # still a real bug if this happens
        "reservation": {"assumed_peak_occupancy_pct": 99.1},
    }
    result = EvaluationSanityChecker().check_bundle(bundle)

    assert len(result["stale_assumptions"]) == 1
    assert result["stale_assumptions"][0]["node"] == "menu_intelligence"


def test_diff_2_does_not_fire_at_normal_occupancy():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    bundle = _valid_bundle()
    bundle["assumptions"] = {
        "menu":        {"assumed_covers_within_capacity": True},
        "reservation": {"assumed_peak_occupancy_pct": 60.0},
    }
    result = EvaluationSanityChecker().check_bundle(bundle)

    assert result["stale_assumptions"] == []


def test_sanity_checker_flags_unrealistic_inventory_quantity():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    bundle = _valid_bundle()
    bundle["agents"]["inventory"]["recommendation"]["restock_actions"] = [
        "Order 50kg Mozzarella Cheese within 24 hours"
    ]

    result = EvaluationSanityChecker().check_bundle(bundle)

    assert result["passed"] is False
    assert any(issue["code"] == "inventory.quantity_realism" for issue in result["issues"])


def test_sanity_checker_does_not_mix_neighboring_inventory_quantities():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    bundle = _valid_bundle()
    bundle["agents"]["inventory"]["data"]["shortage_alerts"] = [
        {
            "ingredient": "Mozzarella Cheese",
            "unit": "kg",
            "quantity_in_stock": 3.5,
            "shortfall": 4.5,
            "max_actionable_restock_qty": 10.5,
        },
        {
            "ingredient": "Garlic",
            "unit": "kg",
            "quantity_in_stock": 0.8,
            "shortfall": 0.7,
            "max_actionable_restock_qty": 2.4,
        },
        {
            "ingredient": "Fresh Basil",
            "unit": "kg",
            "quantity_in_stock": 0.4,
            "shortfall": 0.6,
            "max_actionable_restock_qty": 1.2,
        },
    ]
    bundle["agents"]["inventory"]["recommendation"]["restock_actions"] = [
        "Order 4.5kg Mozzarella Cheese immediately (covers 4.5kg shortfall; current stock 3.5kg; within max actionable cap 10.5kg).",
        "Order 0.7kg Garlic immediately (covers 0.7kg shortfall; current stock 0.8kg; within max actionable cap 2.4kg).",
        "Order 0.6kg Fresh Basil immediately (covers 0.6kg shortfall; current stock 0.4kg; within max actionable cap 1.2kg).",
    ]

    result = EvaluationSanityChecker().check_bundle(bundle)

    assert result["passed"] is True
    assert result["issues"] == []


def test_sanity_checker_flags_long_term_action():
    from app.domain.services.evaluation_sanity import EvaluationSanityChecker

    bundle = _valid_bundle()
    bundle["agents"]["menu"]["recommendation"]["operational_notes"] = [
        "Start a menu redesign next month."
    ]

    result = EvaluationSanityChecker().check_bundle(bundle)

    assert result["passed"] is False
    assert any(issue["code"] == "feasibility.long_term_action" for issue in result["issues"])


@pytest.mark.asyncio
async def test_critic_downgrades_approved_verdict_when_sanity_checks_fail():
    from app.domain.services.critic_service import CriticService

    bundle = _valid_bundle()
    bundle["agents"]["inventory"]["recommendation"]["restock_actions"] = [
        "Order 50kg Mozzarella Cheese within 24 hours"
    ]

    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={"verdict": "approved", "score": 0.95, "notes": "LLM thinks this is fine."}
    )

    service = CriticService(db=MagicMock(), llm=llm)
    result = await service.evaluate(
        agent="ops_manager",
        recommendation=bundle,
        input_summary=bundle["summary_for_critic"],
    )

    assert result["verdict"] == "revision"
    assert result["score"] == 0.65
    assert result["sanity_checks"]["passed"] is False
    assert result["dimension_scores"]["feasibility"] == 0.65
    assert result["revision_reasons"] == [
        "Automated sanity checks found operational issues that require revision."
    ]
    assert any("Mozzarella Cheese" in item for item in result["actionable_feedback"])


@pytest.mark.asyncio
async def test_critic_rejects_hard_policy_errors():
    from app.domain.services.critic_service import CriticService

    bundle = _valid_bundle()
    bundle["agents"]["reservation"]["recommendation"]["recommendation"] = (
        "Seat 90 guests by increasing dining room capacity."
    )

    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={"verdict": "approved", "score": 0.9, "notes": "Looks okay."}
    )

    service = CriticService(db=MagicMock(), llm=llm)
    result = await service.evaluate(
        agent="ops_manager",
        recommendation=bundle,
        input_summary=bundle["summary_for_critic"],
    )

    assert result["verdict"] == "rejected"
    assert result["score"] == 0.3
    assert result["dimension_scores"]["safety"] == 0.3
    assert result["revision_reasons"] == [
        "Policy violations must be resolved before this plan can be approved."
    ]
    assert any(
        issue["code"] == "policy.capacity_limit"
        for issue in result["sanity_checks"]["issues"]
    )

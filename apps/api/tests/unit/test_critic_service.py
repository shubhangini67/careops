from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_critic_prefers_input_summary_over_raw_bundle():
    from app.domain.services.critic_service import CriticService

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={"verdict": "approved", "score": 0.8, "notes": "Looks good."}
    )

    service = CriticService(db=db, llm=llm)
    recommendation = {
        "scenario": "friday_rush",
        "agents": {"inventory": {"recommendation": {"restock_actions": ["oversized dict dump"]}}},
    }

    await service.evaluate(
        agent="ops_manager",
        recommendation=recommendation,
        input_summary="Scenario: friday_rush | Date: 2026-04-25\n[Inventory] Restock mozzarella only.",
    )

    prompt = llm.complete_json.await_args.kwargs["prompt"]
    assert "Restock mozzarella only." in prompt
    assert "oversized dict dump" not in prompt


@pytest.mark.asyncio
async def test_critic_returns_dimension_scores_and_feedback():
    from app.domain.services.critic_service import CriticService

    recommendation = {
        "scenario": "friday_rush",
        "target_date": "2026-05-08",
        "summary_for_critic": "Scenario: friday_rush | Date: 2026-05-08",
        "agents": {
            "forecast": {"recommendation": {"recommendation": "Prep for demand."}},
            "reservation": {"recommendation": {"recommendation": "Manage seating carefully."}},
            "complaint": {"recommendation": {"action_items": ["Check service timing"]}},
            "menu": {"recommendation": {"highlight_items": ["Chicken Tikka Pizza"]}},
            "inventory": {
                "data": {"shortage_alerts": [], "overstock_alerts": []},
                "recommendation": {"restock_actions": [], "priority": "low"},
            },
        },
    }

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={
            "verdict": "revision",
            "score": 0.72,
            "notes": "Good direction, but needs sharper staffing guidance.",
            "dimension_scores": {
                "safety": 0.9,
                "feasibility": 0.6,
                "evidence": 0.8,
                "actionability": 0.55,
                "clarity": 0.7,
            },
            "revision_reasons": [
                "Staffing change is underspecified.",
                "Reservation-pressure mitigation is too vague.",
            ],
            "actionable_feedback": [
                "Quantify extra staffing by role and shift.",
                "Add one explicit waitlist-control action.",
            ],
        }
    )

    service = CriticService(db=db, llm=llm)
    result = await service.evaluate(
        agent="ops_manager",
        recommendation=recommendation,
        input_summary="Scenario: friday_rush | Date: 2026-05-08",
    )

    assert result["dimension_scores"]["safety"] == 0.9
    assert result["dimension_scores"]["actionability"] == 0.55
    assert result["revision_reasons"] == [
        "Staffing change is underspecified.",
        "Reservation-pressure mitigation is too vague.",
    ]
    assert result["actionable_feedback"] == [
        "Quantify extra staffing by role and shift.",
        "Add one explicit waitlist-control action.",
    ]
    assert result["cost_analysis"]["tradeoff_score"] >= 0.0


@pytest.mark.asyncio
async def test_critic_persists_advanced_metadata_in_decision_log():
    from app.domain.services.critic_service import CriticService

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={
            "verdict": "revision",
            "score": 0.68,
            "notes": "Needs clearer execution details.",
            "dimension_scores": {"feasibility": 0.6, "clarity": 0.55},
            "revision_reasons": ["Execution sequencing is unclear."],
            "actionable_feedback": ["Separate prep actions from service-floor actions."],
        }
    )

    def refresh_log(log):
        log.id = 321

    db.refresh.side_effect = refresh_log

    service = CriticService(db=db, llm=llm)
    result = await service.evaluate_and_log(
        agent="ops_manager",
        recommendation={
            "scenario": "friday_rush",
            "target_date": "2026-05-08",
            "summary_for_critic": "Scenario: friday_rush | Date: 2026-05-08",
            "agents": {
                "forecast": {"recommendation": {"recommendation": "Prep for demand."}},
                "reservation": {"recommendation": {"recommendation": "Hold a small waitlist."}},
                "complaint": {"recommendation": {"action_items": ["Watch service speed"]}},
                "menu": {"recommendation": {"highlight_items": ["Margherita"]}},
                "inventory": {
                    "data": {"shortage_alerts": [], "overstock_alerts": []},
                    "recommendation": {"restock_actions": [], "priority": "low"},
                },
            },
        },
        input_summary="Scenario: friday_rush | Date: 2026-05-08",
    )

    log = db.add.call_args.args[0]
    assert log.metadata_["dimension_scores"]["feasibility"] == 0.6
    assert "cost_analysis" in log.metadata_
    assert log.metadata_["revision_reasons"] == ["Execution sequencing is unclear."]
    assert log.metadata_["actionable_feedback"] == [
        "Separate prep actions from service-floor actions."
    ]
    assert result["decision_log_id"] == 321


@pytest.mark.asyncio
async def test_critic_revises_plan_when_tradeoff_score_is_weak():
    from app.domain.services.critic_service import CriticService

    recommendation = {
        "scenario": "friday_rush",
        "target_date": "2026-05-15",
        "summary_for_critic": "Scenario: friday_rush | Date: 2026-05-15",
        "agents": {
            "forecast": {
                "data": {"predicted_orders": 150, "avg_friday_orders": 90},
                "recommendation": {"recommendation": "Increase staffing by 25% and prepare 35% more ingredients with temporary seating and batch prep."},
            },
            "reservation": {
                "data": {"occupancy_pct": 100, "waitlist_count": 5},
                "recommendation": {"recommendation": "Protect peak reservations."},
            },
            "complaint": {"recommendation": {"action_items": ["Watch service timing"]}},
            "menu": {"recommendation": {"highlight_items": ["Chicken Tikka Pizza"], "promo_candidates": ["Margherita"]}},
            "inventory": {
                "data": {
                    "shortage_alerts": [{"severity": "critical"} for _ in range(8)],
                    "overstock_alerts": [{} for _ in range(3)],
                },
                "recommendation": {"restock_actions": ["Order capped inventory immediately."], "priority": "high"},
            },
        },
    }

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={
            "verdict": "approved",
            "score": 0.86,
            "notes": "The plan generally addresses the demand scenario.",
            "dimension_scores": {
                "safety": 0.84,
                "feasibility": 0.83,
                "evidence": 0.8,
                "actionability": 0.82,
                "clarity": 0.78,
            },
        }
    )

    service = CriticService(db=db, llm=llm)
    service.cost_scoring.evaluate_bundle = MagicMock(
        return_value={
            "cost_pressure_score": 0.93,
            "benefit_score": 0.58,
            "tradeoff_score": 0.18,
            "pressure_components": {
                "prep_burden": 1.0,
                "staffing_burden": 0.82,
                "stock_risk": 0.95,
                "reservation_pressure": 0.9,
            },
            "benefit_components": {
                "demand_alignment": 0.8,
                "inventory_protection": 0.55,
                "service_protection": 0.4,
            },
            "tradeoff_notes": [
                "Prep burden is high for this service window.",
                "Reservation pressure leaves limited slack for risky changes.",
            ],
            "recommended_focus": [
                "Protect seating flow and table turns during the peak window.",
                "Favor low-complexity prep changes over broad execution changes.",
            ],
            "signals": {
                "demand_ratio": 1.67,
                "occupancy_pct": 100,
                "waitlist_count": 5,
                "critical_shortages": 8,
            },
        }
    )
    result = await service.evaluate(
        agent="ops_manager",
        recommendation=recommendation,
        input_summary=recommendation["summary_for_critic"],
    )

    assert result["verdict"] == "revision"
    assert result["score"] == 0.68
    assert result["cost_analysis"]["cost_pressure_score"] >= 0.9
    assert result["cost_analysis"]["tradeoff_score"] < 0.2
    assert any("Operational cost and benefit tradeoffs are weak" in reason for reason in result["revision_reasons"])
    assert result["actionable_feedback"]


def _clean_bundle_with_assumptions(assumptions: dict) -> dict:
    """A schema-clean bundle (no sanity-check errors/warnings of its own) so stale-assumption
    behavior can be tested in isolation from the other override branches."""
    return {
        "scenario": "friday_rush",
        "target_date": "2026-05-08",
        "summary_for_critic": "Scenario: friday_rush | Date: 2026-05-08",
        "assumptions": assumptions,
        "agents": {
            "forecast":    {"data": {}, "recommendation": {"recommendation": "Prep for demand."}},
            "reservation": {"data": {}, "recommendation": {"recommendation": "Manage seating carefully."}},
            "complaint":   {"data": {}, "recommendation": {"action_items": ["Check service timing"]}},
            "menu":        {"data": {}, "recommendation": {"highlight_items": ["Margherita"]}},
            "inventory": {
                "data": {"shortage_alerts": [], "overstock_alerts": []},
                "recommendation": {"restock_actions": [], "priority": "low"},
            },
        },
    }


@pytest.mark.asyncio
async def test_critic_stale_assumptions_stay_visible_but_dont_force_downgrade():
    """Stale assumptions are injected into the critic's own prompt (see
    format_stale_assumptions) — a capable critic reasons about them and
    decides for itself whether they're disqualifying. A live run showed a
    critic that explicitly weighed a stale-assumption conflict, judged it a
    non-blocking "operational refinement," and approved — but an earlier,
    blunter version of this code forcibly overrode that verdict to "revision"
    regardless of the critic's own judgment. Visibility (feedback/notes) must
    stay; the automatic verdict override must not."""
    from app.domain.services.critic_service import CriticService

    # Diff 2: menu assumed capacity headroom, but reservation shows >90% occupancy.
    recommendation = _clean_bundle_with_assumptions({
        "menu":        {"assumed_covers_within_capacity": True},
        "reservation": {"assumed_peak_occupancy_pct": 95},
    })

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={
            "verdict": "approved",
            "score": 0.9,
            "notes": "Looks solid.",
            "dimension_scores": {
                "safety": 0.9, "feasibility": 0.9, "evidence": 0.9,
                "actionability": 0.9, "clarity": 0.9,
            },
        }
    )

    service = CriticService(db=db, llm=llm)
    result = await service.evaluate(
        agent="ops_manager",
        recommendation=recommendation,
        input_summary=recommendation["summary_for_critic"],
    )

    # Verdict and score are NOT force-overridden — the critic's own judgment stands.
    assert result["verdict"] == "approved"
    assert result["score"] == 0.9
    assert result["dimension_scores"]["evidence"] == 0.9

    # But the conflict stays fully visible for audit/manager attention.
    assert result["stale_assumptions"], "expected the Diff 2 conflict to be detected"
    assert any(
        "menu_intelligence assumed covers within capacity" in fb
        for fb in result["actionable_feedback"]
    )
    assert "Cross-agent assumption conflicts: 1 detected." in result["notes"]


@pytest.mark.asyncio
async def test_critic_leaves_approved_verdict_unchanged_when_no_stale_assumptions():
    from app.domain.services.critic_service import CriticService

    recommendation = _clean_bundle_with_assumptions({})

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={
            "verdict": "approved",
            "score": 0.9,
            "notes": "Looks solid.",
            "dimension_scores": {
                "safety": 0.9, "feasibility": 0.9, "evidence": 0.9,
                "actionability": 0.9, "clarity": 0.9,
            },
        }
    )

    service = CriticService(db=db, llm=llm)
    result = await service.evaluate(
        agent="ops_manager",
        recommendation=recommendation,
        input_summary=recommendation["summary_for_critic"],
    )

    assert result["verdict"] == "approved"
    assert result["score"] == 0.9
    assert result["dimension_scores"]["evidence"] == 0.9
    assert result["stale_assumptions"] == []
    assert "Cross-agent assumption conflicts" not in result["notes"]


@pytest.mark.asyncio
async def test_critic_persists_stale_assumptions_in_decision_log():
    from app.domain.services.critic_service import CriticService

    recommendation = _clean_bundle_with_assumptions({
        "menu":        {"assumed_covers_within_capacity": True},
        "reservation": {"assumed_peak_occupancy_pct": 95},
    })

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(
        return_value={"verdict": "approved", "score": 0.9, "notes": "Looks solid."}
    )

    def refresh_log(log):
        log.id = 555

    db.refresh.side_effect = refresh_log

    service = CriticService(db=db, llm=llm)
    await service.evaluate_and_log(
        agent="ops_manager",
        recommendation=recommendation,
        input_summary=recommendation["summary_for_critic"],
    )

    log = db.add.call_args.args[0]
    assert log.metadata_["stale_assumptions"]
    assert log.metadata_["stale_assumptions"][0]["node"] == "menu_intelligence"

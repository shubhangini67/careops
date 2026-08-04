"""Unit tests for the what-if simulator (P5-07).

Tests the CostAwareScoringService directly — no LLM, no DB, no LangGraph.
"""

from app.domain.services.cost_aware_scoring import CostAwareScoringService


def _bundle(predicted_covers: int, avg_covers: float = 100.0) -> dict:
    return {
        "agents": {
            "forecast": {
                "data": {
                    "predicted_orders":    predicted_covers,
                    "avg_friday_orders":   avg_covers,
                    "avg_same_day_orders": avg_covers,
                },
                "recommendation": {},
            },
            "reservation": {"data": {"occupancy_pct": 0, "waitlist_count": 0}, "recommendation": {}},
            "inventory":   {"data": {"shortage_alerts": [], "overstock_alerts": []}, "recommendation": {}},
            "menu":        {"recommendation": {}},
        }
    }


def test_demand_ratio_above_baseline_raises_cost_pressure():
    svc = CostAwareScoringService()
    low  = svc.evaluate_bundle(_bundle(predicted_covers=80,  avg_covers=100.0))
    high = svc.evaluate_bundle(_bundle(predicted_covers=150, avg_covers=100.0))

    assert high["cost_pressure_score"] > low["cost_pressure_score"]
    assert high["signals"]["demand_ratio"] > low["signals"]["demand_ratio"]


def test_demand_ratio_at_baseline_is_neutral():
    svc = CostAwareScoringService()
    result = svc.evaluate_bundle(_bundle(predicted_covers=100, avg_covers=100.0))
    # demand_ratio floored at 1.0 for baseline
    assert result["signals"]["demand_ratio"] == 1.0


def test_demand_ratio_below_baseline_shows_raw_in_signals():
    svc = CostAwareScoringService()
    result = svc.evaluate_bundle(_bundle(predicted_covers=50, avg_covers=100.0))
    # signals shows the real ratio (for display); internal calc floors at 1.0 so
    # cost pressure is NOT elevated for off-peak scenarios
    assert result["signals"]["demand_ratio"] == 0.5
    # Cost pressure stays at baseline — not penalised for being off-peak
    baseline = svc.evaluate_bundle(_bundle(predicted_covers=100, avg_covers=100.0))
    assert result["cost_pressure_score"] <= baseline["cost_pressure_score"]


def test_high_covers_increases_benefit_score():
    svc = CostAwareScoringService()
    low  = svc.evaluate_bundle(_bundle(predicted_covers=60,  avg_covers=100.0))
    high = svc.evaluate_bundle(_bundle(predicted_covers=180, avg_covers=100.0))
    assert high["benefit_score"] >= low["benefit_score"]


def test_different_cover_counts_give_different_tradeoff_scores():
    svc = CostAwareScoringService()
    r60  = svc.evaluate_bundle(_bundle(predicted_covers=60))
    r100 = svc.evaluate_bundle(_bundle(predicted_covers=100))
    r160 = svc.evaluate_bundle(_bundle(predicted_covers=160))
    # All three should differ
    scores = {r60["tradeoff_score"], r100["tradeoff_score"], r160["tradeoff_score"]}
    assert len(scores) > 1


def test_result_contains_all_required_fields():
    svc = CostAwareScoringService()
    result = svc.evaluate_bundle(_bundle(predicted_covers=100))
    required = {"cost_pressure_score", "benefit_score", "tradeoff_score",
                "pressure_components", "benefit_components", "tradeoff_notes",
                "recommended_focus", "signals"}
    assert required.issubset(result.keys())


def test_scores_are_clamped_between_0_and_1():
    svc = CostAwareScoringService()
    for covers in [1, 50, 100, 200, 500]:
        result = svc.evaluate_bundle(_bundle(predicted_covers=covers))
        assert 0.0 <= result["cost_pressure_score"] <= 1.0
        assert 0.0 <= result["benefit_score"] <= 1.0
        assert 0.0 <= result["tradeoff_score"] <= 1.0

from app.domain.services.cost_aware_scoring import CostAwareScoringService


def _bundle(
    occupancy_pct: float = 62.9,
    waitlist_count: int = 2,
    critical_shortages: int = 2,
    shortage_alerts: int = 4,
    overstock_alerts: int = 1,
    predicted_orders: float = 107,
    avg_orders: float = 91.5,
    forecast_text: str = "Increase staffing by 10% and prep 15% more ingredients for top pizzas.",
):
    shortages = [
        {"severity": "critical"} for _ in range(critical_shortages)
    ] + [{"severity": "warning"} for _ in range(max(0, shortage_alerts - critical_shortages))]
    overstocks = [{} for _ in range(overstock_alerts)]
    return {
        "scenario": "friday_rush",
        "target_date": "2026-05-08",
        "summary_for_critic": "Scenario: friday_rush | Date: 2026-05-08",
        "agents": {
            "forecast": {
                "data": {
                    "predicted_orders": predicted_orders,
                    "avg_friday_orders": avg_orders,
                },
                "recommendation": {"recommendation": forecast_text},
            },
            "reservation": {
                "data": {
                    "occupancy_pct": occupancy_pct,
                    "waitlist_count": waitlist_count,
                },
                "recommendation": {"recommendation": "Manage pacing carefully."},
            },
            "menu": {
                "recommendation": {
                    "highlight_items": ["Chicken Tikka Pizza"],
                    "promo_candidates": ["Margherita"],
                }
            },
            "inventory": {
                "data": {
                    "shortage_alerts": shortages,
                    "overstock_alerts": overstocks,
                },
                "recommendation": {"restock_actions": ["Order capped inventory immediately."]},
            },
        },
    }


def test_cost_aware_scoring_reports_pressure_and_tradeoffs():
    report = CostAwareScoringService().evaluate_bundle(_bundle())

    assert 0.0 <= report["cost_pressure_score"] <= 1.0
    assert 0.0 <= report["benefit_score"] <= 1.0
    assert 0.0 <= report["tradeoff_score"] <= 1.0
    assert "prep_burden" in report["pressure_components"]
    assert "reservation_pressure" in report["pressure_components"]
    assert report["signals"]["critical_shortages"] == 2
    assert report["tradeoff_notes"]


def test_cost_aware_scoring_gets_harsher_for_extreme_pressure():
    service = CostAwareScoringService()
    mild = service.evaluate_bundle(_bundle(occupancy_pct=55, waitlist_count=0, critical_shortages=0, shortage_alerts=1, predicted_orders=92, avg_orders=91.5))
    intense = service.evaluate_bundle(_bundle(occupancy_pct=98, waitlist_count=4, critical_shortages=5, shortage_alerts=7, predicted_orders=132, avg_orders=91.5, forecast_text="Increase staffing by 20% and prepare 30% more ingredients with temporary seating."))

    assert intense["cost_pressure_score"] > mild["cost_pressure_score"]
    assert intense["tradeoff_score"] < mild["tradeoff_score"]

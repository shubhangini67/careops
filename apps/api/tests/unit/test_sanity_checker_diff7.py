"""Unit tests for Diff 7 (P6-MI08): competitor Dineout deals vs tonight_busy occupancy signal."""

from app.domain.services.evaluation_sanity import EvaluationSanityChecker


def _bundle_with_market_intel(tonight_busy, dineout_deals_count):
    return {
        "scenario": "friday_rush",
        "target_date": "2026-07-05",
        "summary_for_critic": "test",
        "agents": {
            "forecast":    {"data": {}, "recommendation": {}},
            "reservation": {"data": {}, "recommendation": {}},
            "complaint":   {"data": {}, "recommendation": {}},
            "menu":        {"data": {}, "recommendation": {}},
            "inventory":   {"data": {}, "recommendation": {}},
        },
        "assumptions": {
            "market_intel": {
                "swiggy_available": True,
                "tonight_busy": tonight_busy,
                "dineout_deals_count": dineout_deals_count,
            },
        },
    }


def test_diff7_fires_when_tonight_busy_and_competitor_deals_present():
    bundle = _bundle_with_market_intel(tonight_busy=True, dineout_deals_count=3)
    result = EvaluationSanityChecker().check_bundle(bundle)

    stale = result["stale_assumptions"]
    assert len(stale) == 1
    assert stale[0]["node"] == "market_intel"
    assert stale[0]["assumption_key"] == "tonight_busy"
    assert "3 competitor Dineout deal" in stale[0]["conflict"]


def test_diff7_does_not_fire_when_no_competitor_deals():
    bundle = _bundle_with_market_intel(tonight_busy=True, dineout_deals_count=0)
    result = EvaluationSanityChecker().check_bundle(bundle)
    assert result["stale_assumptions"] == []


def test_diff7_does_not_fire_when_tonight_not_busy():
    bundle = _bundle_with_market_intel(tonight_busy=False, dineout_deals_count=5)
    result = EvaluationSanityChecker().check_bundle(bundle)
    assert result["stale_assumptions"] == []


def test_diff7_does_not_fire_at_exactly_one_deal():
    """Threshold is >= 2 deals -- a single promo shouldn't be treated as demand absorption."""
    bundle = _bundle_with_market_intel(tonight_busy=True, dineout_deals_count=1)
    result = EvaluationSanityChecker().check_bundle(bundle)
    assert result["stale_assumptions"] == []


def test_diff7_fires_at_exactly_two_deals():
    bundle = _bundle_with_market_intel(tonight_busy=True, dineout_deals_count=2)
    result = EvaluationSanityChecker().check_bundle(bundle)
    assert len(result["stale_assumptions"]) == 1


def test_diff7_gracefully_skips_when_market_intel_missing():
    bundle = _bundle_with_market_intel(tonight_busy=True, dineout_deals_count=3)
    bundle["assumptions"] = {}
    result = EvaluationSanityChecker().check_bundle(bundle)
    assert result["stale_assumptions"] == []

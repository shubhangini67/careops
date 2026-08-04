"""Unit tests for CompetitorEnricher P6-MI06/MI09 extensions + the category-first
market analysis redesign (dish-name matching dropped as the analysis basis).

All Swiggy API calls are mocked — no live token needed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher


# ── Dish classification (replaces exact dish-name matching) ─────────────────

def test_classify_dish_matches_by_keyword_not_exact_name():
    enricher = CompetitorEnricher(MagicMock())
    # None of these match our own naming exactly, but all classify correctly by keyword
    assert enricher._classify_dish("royal 4in1 non veg pizza") == "pizza"
    assert enricher._classify_dish("pizza 7 - chicken pepperoni and blue cheese (12 inch) (del)") == "pizza"
    assert enricher._classify_dish("chicken maximus pizza") == "pizza"
    assert enricher._classify_dish("spaghetti carbonara") == "pasta"
    assert enricher._classify_dish("crispy chicken burger") == "burger"
    assert enricher._classify_dish("gooey chocolate brownie") == "dessert"
    assert enricher._classify_dish("mango smoothie") == "beverage"
    assert enricher._classify_dish("garlic parmesan fries") == "sides"


def test_classify_dish_returns_none_for_unrecognized_items():
    enricher = CompetitorEnricher(MagicMock())
    assert enricher._classify_dish("mystery combo deal") is None


# ── Market positioning (replaces bare competitor name list) ──────────────────

def test_positioning_ranks_us_among_competitors():
    enricher = CompetitorEnricher(MagicMock())
    landscape = [
        {"name": "A", "rating": 4.0, "cost_for_two": 300.0, "distance_km": 1.0},
        {"name": "B", "rating": 4.0, "cost_for_two": 500.0, "distance_km": 1.0},
        {"name": "C", "rating": 4.0, "cost_for_two": 900.0, "distance_km": 1.0},
    ]
    our_items = [{"name": "Item", "price": 200.0}]  # cost-for-two estimate = 400

    result = enricher._compute_positioning(landscape, our_items)

    # Fields are named from OUR perspective: "we are cheaper than N of them"
    assert result["your_cost_for_two_estimate"] == 400.0
    assert result["cheaper_than_count"] == 2   # we're cheaper than B (500) and C (900)
    assert result["pricier_than_count"] == 1   # we're pricier than A (300)
    assert result["rank"] == 2                 # 1 competitor (A) is cheaper -> we rank 2nd
    assert result["total"] == 4


def test_positioning_returns_none_without_landscape_or_items():
    enricher = CompetitorEnricher(MagicMock())
    assert enricher._compute_positioning([], [{"name": "Item", "price": 200.0}]) is None
    assert enricher._compute_positioning([{"name": "A", "rating": 4.0, "cost_for_two": 300.0, "distance_km": 1.0}], []) is None


# ── P6-MI06: fetch_food_coupons ──────────────────────────────────────────────

COUPONS_RESPONSE = {
    "bestCoupons": [
        {"code": "SAVE20", "title": "20% off above Rs.300", "discountAmount": 20, "requiresOnlinePayment": False},
        {"code": "ONLINE50", "title": "Rs.50 off online", "discountAmount": 50, "requiresOnlinePayment": True},
    ],
    "moreOffers": [
        {"code": "FLAT15", "title": "15% off no minimum", "discountAmount": 15, "requiresOnlinePayment": False},
    ],
}

RESTAURANTS = [
    {"id": "r1", "name": "Biryani House"},
    {"id": "r2", "name": "Paradise"},
]


@pytest.mark.asyncio
async def test_fetch_competitor_deals_filters_online_payment_coupons():
    c = MagicMock()
    c.call_tool = AsyncMock(return_value=COUPONS_RESPONSE)
    enricher = CompetitorEnricher(c)

    deals = await enricher._fetch_competitor_deals("addr1", RESTAURANTS)

    # ONLINE50 requires online payment -- must be excluded
    assert not any(d["code"] == "ONLINE50" for d in deals)
    assert any(d["code"] == "SAVE20" for d in deals)
    assert any(d["code"] == "FLAT15" for d in deals)
    # 2 valid coupons per restaurant x 2 restaurants = 4
    assert len(deals) == 4


@pytest.mark.asyncio
async def test_fetch_competitor_deals_caps_at_max_coupon_calls():
    call_count = {"n": 0}

    async def counting_call_tool(endpoint, tool_name, arguments):
        call_count["n"] += 1
        return COUPONS_RESPONSE

    c = MagicMock()
    c.call_tool = counting_call_tool
    enricher = CompetitorEnricher(c)

    five_restaurants = [{"id": f"r{i}", "name": f"R{i}"} for i in range(5)]
    await enricher._fetch_competitor_deals("addr1", five_restaurants)

    assert call_count["n"] <= 3


@pytest.mark.asyncio
async def test_fetch_competitor_deals_returns_empty_list_on_failure():
    c = MagicMock()
    c.call_tool = AsyncMock(return_value=None)
    enricher = CompetitorEnricher(c)

    deals = await enricher._fetch_competitor_deals("addr1", RESTAURANTS)
    assert deals == []


# ── P6-MI09: pricing impact model ────────────────────────────────────────────

def test_pricing_impact_computes_correctly_for_above_avg_item():
    enricher = CompetitorEnricher(MagicMock())
    area_avg = {"butter chicken": 280.0}
    our_items = [{"name": "Butter Chicken", "price": 320.0}]  # ~14.3% above avg

    impacts = enricher._compute_pricing_impact(area_avg, our_items)

    assert len(impacts) == 1
    impact = impacts[0]
    assert impact["direction"] == "above"
    assert impact["gap_pct"] == pytest.approx(14.3, abs=0.1)
    assert impact["volume_change_pct"] < 0  # higher price -> lower volume
    assert impact["weekly_revenue_impact_inr"] < 0  # negative impact from overpricing


def test_pricing_impact_computes_correctly_for_below_avg_item():
    enricher = CompetitorEnricher(MagicMock())
    area_avg = {"paneer tikka": 195.0}
    our_items = [{"name": "Paneer Tikka", "price": 180.0}]  # below avg

    impacts = enricher._compute_pricing_impact(area_avg, our_items)

    assert len(impacts) == 1
    impact = impacts[0]
    assert impact["direction"] == "below"
    assert impact["gap_pct"] < 0
    assert impact["volume_change_pct"] > 0  # lower price -> higher volume
    assert impact["weekly_revenue_impact_inr"] > 0


def test_pricing_impact_ignores_gaps_under_5_percent():
    enricher = CompetitorEnricher(MagicMock())
    area_avg = {"dal makhani": 200.0}
    our_items = [{"name": "Dal Makhani", "price": 204.0}]  # 2% gap -- noise

    impacts = enricher._compute_pricing_impact(area_avg, our_items)
    assert impacts == []


def test_pricing_impact_returns_top_5_by_absolute_impact():
    enricher = CompetitorEnricher(MagicMock())
    area_avg = {f"dish {i}": 100.0 for i in range(8)}
    our_items = [{"name": f"Dish {i}", "price": 100.0 + (i * 20)} for i in range(8)]

    impacts = enricher._compute_pricing_impact(area_avg, our_items)
    assert len(impacts) <= 5

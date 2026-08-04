"""P6-A1: menu_breadth/cuisine_crowding/veg_mix/landscape_summary were computed
and shown on /market but never reached _build_prompt(), so the LLM never saw them.
These tests confirm they're now wired into prompt_text, without disturbing the
existing category_pricing/positioning/deals/pricing_impact lines.

P6-A20 update: _build_prompt's signature dropped named-restaurant params
(cheapest, restaurant_names, competitor_landscape, competitor_dineout_deals) in
favor of area aggregates (area_restaurant_count, deals_active_count/summary,
landscape_summary, dineout_deals_count/summary) -- calls below updated to match.
"""

from unittest.mock import MagicMock

from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher
from app.infrastructure.swiggy.enrichers.occupancy import OccupancyEnricher


def _competitor_enricher():
    return CompetitorEnricher(MagicMock())


def _occupancy_enricher():
    return OccupancyEnricher(MagicMock())


# ── CompetitorEnricher ───────────────────────────────────────────────────────

def test_prompt_includes_menu_breadth_when_present():
    enricher = _competitor_enricher()
    prompt = enricher._build_prompt(
        area_avg={}, alerts=[], area_restaurant_count=1, our_items=[],
        menu_breadth={"your_item_count": 27, "competitor_avg_item_count": 19.7, "competitors_sampled": 3},
    )
    assert "Menu breadth" in prompt
    assert "27 items" in prompt
    assert "20" in prompt  # 19.7 rounds to 20 in the rendered line


def test_prompt_includes_cuisine_crowding_when_present():
    enricher = _competitor_enricher()
    prompt = enricher._build_prompt(
        area_avg={}, alerts=[], area_restaurant_count=0, our_items=[],
        cuisine_crowding={"cuisine": "italian", "matching_count": 2, "total_checked": 5},
    )
    assert "Cuisine crowding" in prompt
    assert "2 of 5" in prompt
    assert "italian" in prompt


def test_prompt_includes_veg_mix_when_present():
    enricher = _competitor_enricher()
    prompt = enricher._build_prompt(
        area_avg={}, alerts=[], area_restaurant_count=0, our_items=[],
        veg_mix={"veg_count": 3, "total": 5},
    )
    assert "veg/non-veg mix" in prompt.lower()
    assert "3 of 5" in prompt


def test_prompt_includes_landscape_summary_as_area_aggregate():
    """P6-A20: landscape is now a count/avg-rating/cost-range aggregate -- no
    restaurant is individually named in the prompt."""
    enricher = _competitor_enricher()
    landscape_summary = {
        "count": 2, "avg_rating": 4.0, "cost_for_two_min": 300.0,
        "cost_for_two_max": 600.0, "offers_count": 1,
    }
    prompt = enricher._build_prompt(
        area_avg={}, alerts=[], area_restaurant_count=0, our_items=[],
        landscape_summary=landscape_summary,
    )
    assert "Nearby market landscape" in prompt
    assert "2 nearby option" in prompt
    assert "4.0 stars" in prompt
    assert "300" in prompt and "600" in prompt
    assert "running an active offer" in prompt
    # No restaurant should ever be individually named in this section.
    assert "Low Rated" not in prompt
    assert "Top Rated" not in prompt


def test_prompt_omits_new_sections_when_absent():
    enricher = _competitor_enricher()
    prompt = enricher._build_prompt(
        area_avg={}, alerts=[], area_restaurant_count=0, our_items=[],
    )
    assert "Menu breadth" not in prompt
    assert "Cuisine crowding" not in prompt
    assert "veg/non-veg mix" not in prompt.lower()
    assert "Nearby market landscape" not in prompt


def test_prompt_existing_sections_unaffected_by_new_signals():
    enricher = _competitor_enricher()
    prompt = enricher._build_prompt(
        area_avg={"biryani": 250.0},
        alerts=["Butter Chicken: 12% above area avg"], area_restaurant_count=1,
        our_items=[{"name": "Biryani", "price": 260.0}],
        category_pricing=[{"category": "mains", "your_avg": 300.0, "area_avg": 250.0,
                            "diff_pct": 20.0, "verdict": "above", "competitor_dishes_sampled": 2}],
        positioning={"your_cost_for_two_estimate": 500.0, "rank": 2, "total": 5,
                     "pricier_than_count": 1, "cheaper_than_count": 3},
        menu_breadth={"your_item_count": 10, "competitor_avg_item_count": 15.0, "competitors_sampled": 2},
    )
    assert "Category pricing vs area" in prompt
    assert "Market position" in prompt
    assert "Pricing alerts" in prompt
    assert "Menu breadth" in prompt


# ── OccupancyEnricher ────────────────────────────────────────────────────────

def test_occupancy_prompt_includes_slot_availability_by_time_when_2_plus_slots():
    enricher = _occupancy_enricher()
    prompt = enricher._build_prompt(
        signal="MEDIUM", competitors=3, avg_count=2.5,
        slot_availability_by_time=[
            {"time": "7:00 PM", "avg_availability": 4.0, "signal": "LOW"},
            {"time": "8:30 PM", "avg_availability": 0.5, "signal": "HIGH"},
        ],
    )
    assert "Occupancy By Time Slot" in prompt
    assert "7:00 PM" in prompt
    assert "8:30 PM" in prompt
    assert "Tightest window tonight: 8:30 PM" in prompt


def test_occupancy_prompt_omits_by_time_section_with_fewer_than_2_slots():
    enricher = _occupancy_enricher()
    prompt = enricher._build_prompt(
        signal="LOW", competitors=2, avg_count=5.0,
        slot_availability_by_time=[{"time": "7:00 PM", "avg_availability": 5.0, "signal": "LOW"}],
    )
    assert "Occupancy By Time Slot" not in prompt


def test_occupancy_prompt_existing_sections_unaffected():
    enricher = _occupancy_enricher()
    prompt = enricher._build_prompt(
        signal="HIGH", competitors=4, avg_count=0.8,
        dineout_deals_count=1, dineout_deals_summary="1 nearby restaurant has active Dineout deals tonight.",
        slot_deals=[{"time": "8:00 PM", "deal_title": "Free dessert", "discount_pct": 15.0}],
        slot_availability_by_time=[
            {"time": "7:00 PM", "avg_availability": 1.0, "signal": "HIGH"},
            {"time": "8:00 PM", "avg_availability": 0.5, "signal": "HIGH"},
        ],
    )
    assert "Occupancy Signal" in prompt
    assert "Dineout Deals Tonight" in prompt
    assert "1 nearby restaurant has active Dineout deals tonight." in prompt
    assert "Occupancy By Time Slot" in prompt

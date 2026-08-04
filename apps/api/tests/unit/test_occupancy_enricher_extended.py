"""Unit tests for OccupancyEnricher P6-MI07 extensions (get_restaurant_details + slot deals[]).

All Swiggy Dineout API calls and Redis are mocked — no live token needed.
"""

from datetime import date

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.swiggy.enrichers.occupancy import OccupancyEnricher

TODAY = date.today().isoformat()

LOCATION = {"id": "loc_01", "lat": 12.9716, "lng": 77.5946}
RESTAURANT = {"id": "drest_42", "name": "The Fatty Bao"}
CONTEXT = {"org_id": 1, "cuisine": "North Indian"}

# get_restaurant_details' real shape: deals/name/timings live under "offers" and
# nested "restaurant", not top-level (confirmed live) -- see occupancy.py.
RESTAURANT_DETAILS_RESPONSE = {
    "restaurantId": "drest_42",
    "restaurant": {
        "name": "The Fatty Bao",
        "avgRating": 4.5,
        "timings": "12:00 PM - 11:00 PM",
        "deals": [
            {"title": "20% off on food bill", "isFree": False, "bookingPrice": 0, "discountPercentage": 20},
            {"title": "Free Table Booking", "isFree": True, "bookingPrice": 0, "discountPercentage": 0},
            {"title": "No discount deal", "isFree": False, "discountPercentage": 0},
        ],
    },
    "offers": [
        {"title": "20% off on food bill", "isFree": False, "bookingPrice": 0, "discountPercentage": 20},
        {"title": "Free Table Booking", "isFree": True, "bookingPrice": 0, "discountPercentage": 0},
        {"title": "No discount deal", "isFree": False, "discountPercentage": 0},
    ],
    "amenities": ["WiFi", "Valet"],
}

SLOTS_WITH_DEALS = [
    {
        "displayTime": "7:00 PM",
        "slotGroupName": "Dinner",
        "dateStr": TODAY,
        "deals": [
            {"slotId": 1, "title": "Free Table Booking", "isFree": True, "discountPercentage": 0},
            {"slotId": 2, "title": "15% off", "isFree": False, "discountPercentage": 15},
        ],
    },
    {"displayTime": "7:30 PM", "slotGroupName": "Dinner", "dateStr": TODAY, "deals": []},
]


def _slots_response(slots: list[dict]) -> dict:
    return {"_meta": {"slots": slots}}


# ── PART A: get_restaurant_details ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_competitor_dineout_details_extracts_deals():
    c = MagicMock()
    c.call_tool = AsyncMock(return_value=RESTAURANT_DETAILS_RESPONSE)
    enricher = OccupancyEnricher(c)

    details = await enricher._fetch_competitor_dineout_details(
        [{"id": "drest_42", "name": "The Fatty Bao"}], lat=12.9, lng=77.5,
    )

    assert len(details) == 1
    entry = details[0]
    assert entry["name"] == "The Fatty Bao"
    # only 2 of 3 deals qualify (discount>0 or isFree)
    assert len(entry["deals"]) == 2
    assert entry["amenities"] == ["WiFi", "Valet"]


@pytest.mark.asyncio
async def test_fetch_competitor_dineout_details_skips_restaurants_with_no_deals():
    c = MagicMock()
    c.call_tool = AsyncMock(return_value={"restaurant": {"name": "No Deals Place"}, "offers": [], "amenities": []})
    enricher = OccupancyEnricher(c)

    details = await enricher._fetch_competitor_dineout_details(
        [{"id": "r1", "name": "No Deals Place"}], lat=12.9, lng=77.5,
    )
    assert details == []


@pytest.mark.asyncio
async def test_fetch_competitor_dineout_details_caps_at_max_detail_calls():
    call_count = {"n": 0}

    async def counting_call_tool(endpoint, tool_name, arguments):
        call_count["n"] += 1
        return RESTAURANT_DETAILS_RESPONSE

    c = MagicMock()
    c.call_tool = counting_call_tool
    enricher = OccupancyEnricher(c)

    five_restaurants = [{"id": f"drest_{i}", "name": f"R{i}"} for i in range(5)]
    await enricher._fetch_competitor_dineout_details(five_restaurants, lat=12.9, lng=77.5)

    assert call_count["n"] <= 3


# ── PART B: slot deals[] parsing (zero extra API calls) ──────────────────────

def test_slot_deals_parsed_from_available_slots_response():
    enricher = OccupancyEnricher(MagicMock())
    slot_deals = enricher._extract_slot_deals(SLOTS_WITH_DEALS)

    # only the discount>0 deal counts -- the isFree/no-discount deal is excluded
    assert len(slot_deals) == 1
    assert slot_deals[0]["deal_title"] == "15% off"
    assert slot_deals[0]["discount_pct"] == 15
    assert slot_deals[0]["time"] == "7:00 PM"


def test_slot_deals_returns_empty_list_when_no_deals_present():
    enricher = OccupancyEnricher(MagicMock())
    slots = [{"displayTime": "8:00 PM", "dateStr": TODAY}]
    assert enricher._extract_slot_deals(slots) == []


# ── PART C: wired into enrich() result dict ──────────────────────────────────

@pytest.mark.asyncio
async def test_competitor_dineout_deals_in_result_dict():
    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"locations": [LOCATION]}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": [RESTAURANT]}
        if tool_name == "render_restaurants_dineout":
            return {"restaurants": [RESTAURANT]}
        if tool_name == "get_available_slots":
            return _slots_response(SLOTS_WITH_DEALS)
        if tool_name == "get_restaurant_details":
            return RESTAURANT_DETAILS_RESPONSE
        return None

    c = MagicMock()
    c.call_tool = call_tool
    enricher = OccupancyEnricher(c)
    enricher._cache_get = AsyncMock(return_value=None)
    enricher._cache_set = AsyncMock()

    result = await enricher.enrich(CONTEXT)

    assert result is not None
    # P6-A20: raw named-restaurant deal list is reduced to a count/summary --
    # the restaurant name itself never reaches the result dict or prompt.
    assert result["dineout_deals_count"] == 1
    assert "The Fatty Bao" not in result["dineout_deals_summary"]
    assert "1 nearby restaurant" in result["dineout_deals_summary"]
    assert len(result["slot_deals_found"]) == 1
    assert "## Dineout Deals Tonight" in result["prompt_text"]
    assert "The Fatty Bao" not in result["prompt_text"]


@pytest.mark.asyncio
async def test_result_dict_has_empty_deal_lists_when_no_deals_anywhere():
    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"locations": [LOCATION]}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": [RESTAURANT]}
        if tool_name == "render_restaurants_dineout":
            return {"restaurants": [RESTAURANT]}
        if tool_name == "get_available_slots":
            return _slots_response([{"displayTime": "7:00 PM", "slotGroupName": "Dinner", "dateStr": TODAY, "deals": []}])
        if tool_name == "get_restaurant_details":
            return {"restaurant": {"name": "The Fatty Bao"}, "offers": [], "amenities": []}
        return None

    c = MagicMock()
    c.call_tool = call_tool
    enricher = OccupancyEnricher(c)
    enricher._cache_get = AsyncMock(return_value=None)
    enricher._cache_set = AsyncMock()

    result = await enricher.enrich(CONTEXT)

    assert result is not None
    assert result["dineout_deals_count"] == 0
    assert result["slot_deals_found"] == []
    assert "## Dineout Deals Tonight" not in result["prompt_text"]

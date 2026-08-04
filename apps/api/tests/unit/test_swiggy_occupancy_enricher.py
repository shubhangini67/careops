"""Unit tests for OccupancyEnricher (P6-S08).

All Swiggy Dineout API calls and Redis are mocked — no live token needed.
"""

from datetime import date

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.swiggy.enrichers.occupancy import OccupancyEnricher

# ── helpers ───────────────────────────────────────────────────────────────────

TODAY = date.today().isoformat()

LOCATION = {"id": "loc_01", "lat": 12.9716, "lng": 77.5946}

RESTAURANT = {"id": "drest_42", "name": "The Fatty Bao"}
SPONSORED_RESTAURANT = {"id": "drest_99", "name": "Closed Spot (Ad)"}

SEARCH_TEXT = (
    "Found 2 dineout restaurant(s):\n"
    "1. The Fatty Bao — Asian, Chinese | 4.2★ | ₹800 for two | Vashi (ID: 42)\n"
    "2. Sponsored Place (Ad) — Continental | 4.0★ | ₹900 for two | Vashi (ID: 99)\n"
    "Search coordinates: latitude=19.1, longitude=73.0 (use these for get_restaurant_details and downstream calls)."
)


def _slots(dinner_times: list[str]) -> dict:
    """Build a get_available_slots response with slots["_meta"]["slots"] shape,
    matching the live API -- one slot per given dinner-hour displayTime, dated today."""
    return {
        "_meta": {
            "slots": [
                {"displayTime": t, "slotGroupName": "Dinner", "dateStr": TODAY, "deals": []}
                for t in dinner_times
            ]
        }
    }


SLOTS_BUSY = _slots(["7:00 PM"])            # only 1 of 6 dinner-hour times open -> HIGH
SLOTS_QUIET = _slots(
    ["7:00 PM", "7:30 PM", "8:00 PM", "8:30 PM", "9:00 PM", "9:30 PM"]  # all 6 open -> LOW
)

CONTEXT = {"org_id": 1, "cuisine": "North Indian"}


def _client(locations=None, restaurants=None, slots=None):
    """restaurants, if given, is returned directly as search_restaurants_dineout's
    structuredContent (the shape-compatibility path) AND used to answer
    render_restaurants_dineout, filtered to the ids actually requested --
    faithful to how a real render call would only return what it was asked for."""
    all_restaurants = restaurants if restaurants is not None else [RESTAURANT]
    c = MagicMock()

    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"locations": locations if locations is not None else [LOCATION]}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": all_restaurants}
        if tool_name == "render_restaurants_dineout":
            requested = set(arguments.get("restaurantIds") or [])
            return {"restaurants": [r for r in all_restaurants if r["id"] in requested]}
        if tool_name == "get_available_slots":
            return slots
        return None

    c.call_tool = call_tool
    return c


def _enricher(client, cached=None):
    e = OccupancyEnricher(client)
    e._cache_get = AsyncMock(return_value=cached)
    e._cache_set = AsyncMock()
    return e


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_none_when_no_saved_locations():
    enricher = _enricher(_client(locations=[]))
    result = await enricher.enrich(CONTEXT)
    assert result is None


@pytest.mark.asyncio
async def test_falls_back_to_default_coords_when_location_has_no_lat_lng():
    """Swiggy's real get_saved_locations response never includes lat/lng --
    a location with only an id must still resolve (via DEFAULT_RESTAURANT_LAT/LNG),
    not be treated as "no saved location."""
    enricher = _enricher(_client(locations=[{"id": "loc_01"}], slots=SLOTS_BUSY))
    result = await enricher.enrich(CONTEXT)
    assert result is not None
    assert result["occupancy_signal"] == "HIGH"


@pytest.mark.asyncio
async def test_reads_locations_nested_under_data_key():
    """get_saved_locations' real structuredContent shape is
    {"data": {"locations": [...]}}, not {"locations": [...]} directly."""
    client = MagicMock()

    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": [LOCATION]}}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": [RESTAURANT]}
        if tool_name == "render_restaurants_dineout":
            return {"restaurants": [RESTAURANT]}
        if tool_name == "get_available_slots":
            return SLOTS_BUSY
        return None

    client.call_tool = call_tool
    enricher = _enricher(client)
    result = await enricher.enrich(CONTEXT)
    assert result is not None
    assert result["occupancy_signal"] == "HIGH"


@pytest.mark.asyncio
async def test_parses_restaurants_from_freeform_search_text():
    """search_restaurants_dineout's real structuredContent is empty ({}) --
    restaurant ids/names only exist in its freeform text, which this must parse."""
    client = MagicMock()

    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"locations": [LOCATION]}
        if tool_name == "search_restaurants_dineout":
            return {"text": SEARCH_TEXT}
        if tool_name == "render_restaurants_dineout":
            # only the organic (non-sponsored) id should have been requested
            assert arguments["restaurantIds"] == ["42"]
            return {"restaurants": [{"id": "42", "name": "The Fatty Bao"}], "latitude": 19.1, "longitude": 73.0}
        if tool_name == "get_available_slots":
            return SLOTS_BUSY
        return None

    client.call_tool = call_tool
    enricher = _enricher(client)
    result = await enricher.enrich(CONTEXT)
    assert result is not None
    assert result["occupancy_signal"] == "HIGH"


@pytest.mark.asyncio
async def test_returns_none_when_all_candidates_sponsored():
    enricher = _enricher(_client(restaurants=[SPONSORED_RESTAURANT]))
    result = await enricher.enrich(CONTEXT)
    assert result is None


@pytest.mark.asyncio
async def test_sponsored_restaurants_excluded_from_slot_calls():
    mixed = [RESTAURANT, SPONSORED_RESTAURANT]
    call_count = {"n": 0}

    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"locations": [LOCATION]}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": mixed}
        if tool_name == "render_restaurants_dineout":
            requested = set(arguments.get("restaurantIds") or [])
            return {"restaurants": [r for r in mixed if r["id"] in requested]}
        if tool_name == "get_available_slots":
            call_count["n"] += 1
            return SLOTS_BUSY
        return None

    c = MagicMock()
    c.call_tool = call_tool
    enricher = _enricher(c)
    await enricher.enrich(CONTEXT)
    # only the non-sponsored restaurant should trigger a slot call
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_returns_none_when_slot_calls_all_fail():
    enricher = _enricher(_client(slots=None))  # get_available_slots returns None
    result = await enricher.enrich(CONTEXT)
    assert result is None


@pytest.mark.asyncio
async def test_high_signal_when_few_dinner_slots_open():
    enricher = _enricher(_client(slots=SLOTS_BUSY))
    result = await enricher.enrich(CONTEXT)
    assert result is not None
    assert result["occupancy_signal"] == "HIGH"
    assert result["tonight_busy"] is True


@pytest.mark.asyncio
async def test_low_signal_when_many_dinner_slots_open():
    enricher = _enricher(_client(slots=SLOTS_QUIET))
    result = await enricher.enrich(CONTEXT)
    assert result is not None
    assert result["occupancy_signal"] == "LOW"
    assert result["tonight_busy"] is False


@pytest.mark.asyncio
async def test_slots_on_other_dates_are_ignored():
    """get_available_slots returns a rolling multi-day window regardless of the
    "date" argument (confirmed live) -- only tonight's dateStr should count."""
    other_day_slots = {
        "_meta": {
            "slots": [
                {"displayTime": t, "slotGroupName": "Dinner", "dateStr": "2099-01-01", "deals": []}
                for t in ["7:00 PM", "7:30 PM", "8:00 PM", "8:30 PM", "9:00 PM", "9:30 PM"]
            ]
        }
    }
    enricher = _enricher(_client(slots=other_day_slots))
    result = await enricher.enrich(CONTEXT)
    # zero matching slots for tonight across the one restaurant checked -> HIGH (fully booked proxy)
    assert result is not None
    assert result["occupancy_signal"] == "HIGH"


@pytest.mark.asyncio
async def test_prompt_text_contains_signal_and_competitors():
    enricher = _enricher(_client(slots=SLOTS_BUSY))
    result = await enricher.enrich(CONTEXT)
    assert result is not None
    assert "## Occupancy Signal" in result["prompt_text"]
    assert "HIGH" in result["prompt_text"]


@pytest.mark.asyncio
async def test_cache_hit_skips_api_calls():
    cached = {"occupancy_signal": "MEDIUM", "tonight_busy": False, "cached": True}
    enricher = _enricher(_client(), cached=cached)
    result = await enricher.enrich(CONTEXT)
    assert result == cached


@pytest.mark.asyncio
async def test_cache_written_after_successful_fetch():
    enricher = _enricher(_client(slots=SLOTS_BUSY))
    result = await enricher.enrich(CONTEXT)
    assert result is not None
    enricher._cache_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_max_three_slot_calls_enforced():
    five_restaurants = [{"id": f"drest_{i}", "name": f"R{i}"} for i in range(5)]
    call_count = {"n": 0}

    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"locations": [LOCATION]}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": five_restaurants}
        if tool_name == "render_restaurants_dineout":
            requested = set(arguments.get("restaurantIds") or [])
            return {"restaurants": [r for r in five_restaurants if r["id"] in requested]}
        if tool_name == "get_available_slots":
            call_count["n"] += 1
            return SLOTS_BUSY
        return None

    c = MagicMock()
    c.call_tool = call_tool
    enricher = _enricher(c)
    await enricher.enrich(CONTEXT)
    assert call_count["n"] <= 3


@pytest.mark.asyncio
async def test_exception_returns_none_never_raises():
    c = MagicMock()
    c.call_tool = AsyncMock(side_effect=RuntimeError("Dineout down"))
    enricher = _enricher(c)
    result = await enricher.enrich(CONTEXT)
    assert result is None

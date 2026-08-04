"""Unit tests for CompetitorEnricher (P6-S07).

All Swiggy API calls and Redis are mocked — no live token needed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher


# ── helpers ───────────────────────────────────────────────────────────────────

def _client(restaurants=None, menu=None):
    """Build a mock SwiggyMCPClient with configurable return values."""
    c = MagicMock()

    async def call_tool(endpoint, tool_name, arguments):
        if tool_name == "search_restaurants":
            return {"restaurants": restaurants or []}
        if tool_name == "get_restaurant_menu":
            return menu
        return None

    c.call_tool = call_tool
    return c


OPEN_RESTAURANT = {
    "id": "R1",
    "name": "Spice Garden",
    "availabilityStatus": "OPEN",
    "rating": 4.2,
    "costForTwo": 400,
}

CLOSED_RESTAURANT = {
    "id": "R2",
    "name": "Closed Place",
    "availabilityStatus": "CLOSED",
}

MENU_RESPONSE = {
    "categories": [
        {
            "name": "Main Course",
            "items": [
                {"name": "Butter Chicken", "price": 280},
                {"name": "Margherita", "price": 220},
                {"name": "No Price Item", "price": 0},
            ],
        }
    ]
}

CONTEXT = {
    "org_id": 1,
    "address_id": "addr_abc",
    "cuisine": "North Indian",
    "our_items": [
        {"name": "Butter Chicken", "price": 340},  # 21% above avg — alert expected
        {"name": "Margherita", "price": 230},        # within 10% — no alert
    ],
}


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_none_when_client_returns_no_restaurants():
    enricher = CompetitorEnricher(_client(restaurants=[]))
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        result = await enricher.enrich(CONTEXT)
    assert result is None


@pytest.mark.asyncio
async def test_filters_closed_restaurants():
    """Closed restaurants must not be fetched."""
    enricher = CompetitorEnricher(_client(
        restaurants=[CLOSED_RESTAURANT],
        menu=MENU_RESPONSE,
    ))
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        result = await enricher.enrich(CONTEXT)
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_menu_fetch_fails():
    enricher = CompetitorEnricher(_client(
        restaurants=[OPEN_RESTAURANT],
        menu=None,  # menu call returns None
    ))
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        result = await enricher.enrich(CONTEXT)
    assert result is None


@pytest.mark.asyncio
async def test_correct_area_avg_computed():
    enricher = CompetitorEnricher(_client(
        restaurants=[OPEN_RESTAURANT],
        menu=MENU_RESPONSE,
    ))
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        result = await enricher.enrich(CONTEXT)

    assert result is not None
    assert result["area_avg"]["butter chicken"] == 280.0
    assert result["area_avg"]["margherita"] == 220.0
    assert "no price item" not in result["area_avg"]


@pytest.mark.asyncio
async def test_alert_generated_for_item_above_threshold():
    enricher = CompetitorEnricher(_client(
        restaurants=[OPEN_RESTAURANT],
        menu=MENU_RESPONSE,
    ))
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        result = await enricher.enrich(CONTEXT)

    assert result is not None
    # Butter Chicken: our Rs.340 vs avg Rs.280 = 21% above — alert expected
    assert any("Butter Chicken" in a for a in result["alerts"])
    # Margherita: our Rs.230 vs avg Rs.220 = 4.5% — no alert
    assert not any("Margherita" in a for a in result["alerts"])


@pytest.mark.asyncio
async def test_result_has_no_named_restaurant_pricing():
    """P6-A20: cheapest-map (per-dish price + restaurant) is computed internally
    but never exposed -- result only carries area_avg (dish -> price, no restaurant
    attribution) plus the anonymised count/summary fields."""
    enricher = CompetitorEnricher(_client(
        restaurants=[OPEN_RESTAURANT],
        menu=MENU_RESPONSE,
    ))
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        result = await enricher.enrich(CONTEXT)

    assert result is not None
    assert "cheapest" not in result
    assert "restaurants" not in result
    assert "competitor_landscape" not in result
    assert "competitor_deals" not in result
    assert result["area_avg"]["butter chicken"] == 280.0
    assert result["area_restaurant_count"] == 1


@pytest.mark.asyncio
async def test_prompt_text_present_and_omits_restaurant_names():
    enricher = CompetitorEnricher(_client(
        restaurants=[OPEN_RESTAURANT],
        menu=MENU_RESPONSE,
    ))
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        result = await enricher.enrich(CONTEXT)

    assert result is not None
    assert "## Area Market Signals" in result["prompt_text"]
    assert "Spice Garden" not in result["prompt_text"]


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_value_without_api_call():
    cached_value = {"area_avg": {"dal makhani": 180.0}, "cached": True}
    enricher = CompetitorEnricher(_client())  # client would fail if called
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=cached_value)):
        result = await enricher.enrich(CONTEXT)
    assert result == cached_value


@pytest.mark.asyncio
async def test_cache_is_written_after_successful_fetch():
    enricher = CompetitorEnricher(_client(
        restaurants=[OPEN_RESTAURANT],
        menu=MENU_RESPONSE,
    ))
    mock_set = AsyncMock()
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=mock_set):
        result = await enricher.enrich(CONTEXT)

    assert result is not None
    mock_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_returns_none_when_no_address_id():
    """Missing address_id and no settings fallback must return None gracefully."""
    enricher = CompetitorEnricher(_client(restaurants=[OPEN_RESTAURANT], menu=MENU_RESPONSE))
    with patch("app.infrastructure.swiggy.enrichers.competitor.get_settings") as mock_settings:
        mock_settings.return_value.swiggy_address_id = ""
        with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)):
            result = await enricher.enrich({"org_id": 1})  # no address_id
    assert result is None


@pytest.mark.asyncio
async def test_max_three_menu_calls_enforced():
    """Even with 5 open restaurants, at most 3 menu calls are made."""
    five_restaurants = [
        {"id": f"R{i}", "name": f"Restaurant {i}", "availabilityStatus": "OPEN"}
        for i in range(5)
    ]
    call_count = {"n": 0}

    async def counting_call_tool(endpoint, tool_name, arguments):
        if tool_name == "search_restaurants":
            return {"restaurants": five_restaurants}
        if tool_name == "get_restaurant_menu":
            call_count["n"] += 1
            return MENU_RESPONSE
        return None

    c = MagicMock()
    c.call_tool = counting_call_tool

    enricher = CompetitorEnricher(c)
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)), \
         patch.object(enricher, "_cache_set", new=AsyncMock()):
        await enricher.enrich(CONTEXT)

    assert call_count["n"] <= 3


@pytest.mark.asyncio
async def test_exception_in_client_returns_none():
    """Any unexpected exception inside enrich() must return None, never raise."""
    c = MagicMock()
    c.call_tool = AsyncMock(side_effect=RuntimeError("network down"))

    enricher = CompetitorEnricher(c)
    with patch.object(enricher, "_cache_get", new=AsyncMock(return_value=None)):
        result = await enricher.enrich(CONTEXT)

    assert result is None

"""Unit tests for market_intel_node's our_items wiring.

Regression coverage: market_intel_node previously never passed our_items to
MarketIntelService during a real planning run -- only the standalone
/market/pulse endpoint did. That meant CompetitorEnricher's alerts,
dish_prices, pricing_impact, and category_pricing all silently stayed empty
for every actual plan run. Fixed by loading MenuItem rows via db_factory.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestration.nodes.market_intel import market_intel_node


def _menu_item(name, price, category):
    item = MagicMock()
    item.name = name
    item.price = price
    item.category = category
    return item


@pytest.mark.asyncio
async def test_skips_db_query_when_swiggy_unavailable():
    swiggy_client = MagicMock()
    swiggy_client.is_available.return_value = False
    db_factory = MagicMock()

    state = {"org_id": 1, "scenario_profile": {}}
    result = await market_intel_node(state, swiggy_client=swiggy_client, db_factory=db_factory)

    # P6-A24: Swiggy-specific fields are null, but market_intel_output itself
    # is never wiped to None -- weather/trends/compliance (fetched earlier by
    # demand_forecast_node, absent here) still need a place to surface.
    assert result["market_intel_output"]["competitor_pricing"] is None
    assert result["market_intel_output"]["area_occupancy"] is None
    assert result["market_intel_output"]["live_signals_text"] == ""
    assert result["market_intel_assumptions"] == {"swiggy_available": False}
    db_factory.assert_not_called()


@pytest.mark.asyncio
async def test_live_signals_surface_even_when_swiggy_unavailable():
    """P6-A24: weather/trends/compliance are not Swiggy MCP -- one source
    (Swiggy) being down must never block the other three from reaching
    live_signals_text."""
    swiggy_client = MagicMock()
    swiggy_client.is_available.return_value = False
    db_factory = MagicMock()

    state = {
        "org_id": 1,
        "scenario_profile": {},
        "weather_signal": {"prompt_text": "## Weather Forecast\nClear skies."},
        "trends_signal": {"prompt_text": "## Industry Trends\n- Mustard prices up."},
        "compliance_alerts_signal": {"prompt_text": "## Regulatory Alerts (FSSAI)\n- New vegan labelling rule."},
    }
    result = await market_intel_node(state, swiggy_client=swiggy_client, db_factory=db_factory)

    text = result["market_intel_output"]["live_signals_text"]
    assert "Clear skies." in text
    assert "Mustard prices up." in text
    assert "New vegan labelling rule." in text
    db_factory.assert_not_called()


@pytest.mark.asyncio
async def test_passes_our_items_with_category_to_market_intel_service():
    swiggy_client = MagicMock()
    swiggy_client.is_available.return_value = True

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [
        _menu_item("Butter Chicken", 320.0, "Mains"),
        _menu_item("Paneer Tikka", 180.0, "Starters"),
    ]
    db_factory = MagicMock(return_value=session)

    captured_context = {}

    async def fake_run(context):
        captured_context.update(context)
        return {
            "swiggy_competitor_context": None,
            "swiggy_occupancy_context": None,
            "market_intel_output": {
                "competitor_pricing": None, "area_occupancy": None,
                "pricing_alerts": [], "tonight_busy": None, "fetched_at": "2026-07-05",
            },
        }

    with patch("app.orchestration.nodes.market_intel.MarketIntelService") as mock_service_cls:
        mock_service_cls.return_value.run = fake_run
        state = {"org_id": 1, "scenario_profile": {"cuisine": "North Indian"}}
        await market_intel_node(state, swiggy_client=swiggy_client, db_factory=db_factory)

    assert captured_context["cuisine"] == "North Indian"
    our_items = captured_context["our_items"]
    assert {"name": "Butter Chicken", "price": 320.0, "category": "Mains"} in our_items
    assert {"name": "Paneer Tikka", "price": 180.0, "category": "Starters"} in our_items
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_returns_state_unchanged_when_error_already_set():
    swiggy_client = MagicMock()
    db_factory = MagicMock()
    state = {"error": "upstream failure"}

    result = await market_intel_node(state, swiggy_client=swiggy_client, db_factory=db_factory)

    assert result == state
    db_factory.assert_not_called()

"""Unit tests for the P6-MI04 chatbot Dineout competitive-intelligence tools:
swiggy_get_competitor_deals, swiggy_get_area_occupancy, swiggy_get_common_dishes.

These reuse CompetitorEnricher/OccupancyEnricher directly (same as the planning
pipeline), so tests mock those enrichers' .enrich() rather than raw MCP calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.chat_service import _run_swiggy_tool


def _available_client():
    client = MagicMock()
    client.is_available.return_value = True
    return client


@pytest.mark.asyncio
async def test_get_competitor_deals_combines_food_and_dineout_deals():
    client = _available_client()
    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client), \
         patch("app.domain.services.chat_service.CompetitorEnricher") as mock_comp, \
         patch("app.domain.services.chat_service.OccupancyEnricher") as mock_occ:
        mock_comp.return_value.enrich = AsyncMock(return_value={
            "deals_active_count": 1,
            "deals_summary": "1 nearby restaurant has active deals tonight.",
        })
        mock_occ.return_value.enrich = AsyncMock(return_value={
            "dineout_deals_count": 1,
            "dineout_deals_summary": "1 nearby restaurant has active Dineout deals tonight.",
            "slot_deals_found": [{"time": "7:00 PM", "deal_title": "15% off", "discount_pct": 15, "is_free": False}],
        })

        result = json.loads(await _run_swiggy_tool("swiggy_get_competitor_deals", {"cuisine": "Biryani"}, org_id=1))

    assert result["source"] == "Swiggy Food + Dineout (live, area aggregate)"
    # P6-A20: no restaurant name anywhere in the response -- area count/summary only.
    assert "1 nearby restaurant" in result["food_deals_summary"]
    assert "1 nearby restaurant" in result["dineout_prebooking_deals_summary"]
    assert "Biryani House" not in json.dumps(result)
    assert "The Fatty Bao" not in json.dumps(result)
    assert len(result["dineout_slot_deals_tonight"]) == 1


@pytest.mark.asyncio
async def test_get_competitor_deals_errors_when_nothing_found():
    client = _available_client()
    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client), \
         patch("app.domain.services.chat_service.CompetitorEnricher") as mock_comp, \
         patch("app.domain.services.chat_service.OccupancyEnricher") as mock_occ:
        mock_comp.return_value.enrich = AsyncMock(return_value=None)
        mock_occ.return_value.enrich = AsyncMock(return_value=None)

        result = json.loads(await _run_swiggy_tool("swiggy_get_competitor_deals", {}, org_id=1))

    assert "error" in result


@pytest.mark.asyncio
async def test_get_area_occupancy_returns_signal():
    client = _available_client()
    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client), \
         patch("app.domain.services.chat_service.OccupancyEnricher") as mock_occ:
        mock_occ.return_value.enrich = AsyncMock(return_value={
            "occupancy_signal": "HIGH", "tonight_busy": True, "competitors_checked": 3,
        })

        result = json.loads(await _run_swiggy_tool("swiggy_get_area_occupancy", {"cuisine": "North Indian"}, org_id=1))

    assert result["occupancy_signal"] == "HIGH"
    assert result["tonight_busy"] is True
    assert result["competitors_checked"] == 3


@pytest.mark.asyncio
async def test_get_area_occupancy_errors_when_none():
    client = _available_client()
    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client), \
         patch("app.domain.services.chat_service.OccupancyEnricher") as mock_occ:
        mock_occ.return_value.enrich = AsyncMock(return_value=None)

        result = json.loads(await _run_swiggy_tool("swiggy_get_area_occupancy", {}, org_id=1))

    assert "error" in result


@pytest.mark.asyncio
async def test_get_common_dishes_returns_dishes_with_honesty_note():
    client = _available_client()
    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client), \
         patch("app.domain.services.chat_service.CompetitorEnricher") as mock_comp:
        mock_comp.return_value.enrich = AsyncMock(return_value={
            "area_avg": {"butter chicken": 280.0, "biryani": 320.0},
        })

        result = json.loads(await _run_swiggy_tool("swiggy_get_common_dishes", {"cuisine": "North Indian"}, org_id=1))

    assert len(result["dishes"]) == 2
    assert "not order-volume" in result["note"]


@pytest.mark.asyncio
async def test_get_common_dishes_errors_when_no_area_avg():
    client = _available_client()
    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client), \
         patch("app.domain.services.chat_service.CompetitorEnricher") as mock_comp:
        mock_comp.return_value.enrich = AsyncMock(return_value={"area_avg": {}})

        result = json.loads(await _run_swiggy_tool("swiggy_get_common_dishes", {}, org_id=1))

    assert "error" in result


@pytest.mark.asyncio
async def test_all_new_tools_error_gracefully_when_swiggy_not_connected():
    client = MagicMock()
    client.is_available.return_value = False

    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client):
        for tool_name in ("swiggy_get_competitor_deals", "swiggy_get_area_occupancy", "swiggy_get_common_dishes"):
            result = json.loads(await _run_swiggy_tool(tool_name, {}, org_id=1))
            assert result["error"] == "Swiggy not connected"


@pytest.mark.asyncio
async def test_exception_in_enricher_returns_error_json_never_raises():
    client = _available_client()
    with patch("app.domain.services.chat_service.SwiggyMCPClient", return_value=client), \
         patch("app.domain.services.chat_service.OccupancyEnricher") as mock_occ:
        mock_occ.return_value.enrich = AsyncMock(side_effect=RuntimeError("Dineout down"))

        result = json.loads(await _run_swiggy_tool("swiggy_get_area_occupancy", {}, org_id=1))

    assert "error" in result

"""Unit tests for ConciergeService (Phase 6A-34, Guest Concierge).

All Swiggy MCP calls are mocked via the injected client -- no live network
needed. LLM calls (extract_intent, handle_message's ReAct loop) are mocked
at the client level too, matching chat_service.py's own test conventions.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.concierge_service import ConciergeService, ConciergeSession


def _mock_swiggy_client(**tool_responses: dict | None) -> MagicMock:
    """tool_responses maps tool name -> return value. call_tool ignores
    endpoint/arguments and just looks up by tool name."""
    client = MagicMock()

    async def _call_tool(endpoint, tool_name, arguments):
        return tool_responses.get(tool_name)

    client.call_tool = AsyncMock(side_effect=_call_tool)
    return client


# ── _ensure_dineout_location: real Swiggy response has no lat/lng ───────────

@pytest.mark.asyncio
async def test_ensure_dineout_location_handles_nested_response_without_coords():
    """get_saved_locations nests its payload under "data" and never actually
    returns lat/lng (confirmed live) -- must fall back to DEFAULT_RESTAURANT_LAT/LNG
    rather than treating "no coordinates in the response" as "no location"."""
    client = _mock_swiggy_client(get_saved_locations={
        "data": {"locations": [{"id": "loc1", "addressLine": "Vashi, Navi Mumbai"}]},
    })
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    resolved = await service._ensure_dineout_location(session)

    assert resolved is True
    assert session.location_lat is not None
    assert session.location_lng is not None


@pytest.mark.asyncio
async def test_ensure_dineout_location_falls_back_to_default_when_no_locations_at_all():
    """The Builders Club v1 test account has zero saved Dineout locations (no
    "save location" option in Swiggy's own UI, only wishlist) -- this must
    never surface an internal "couldn't resolve location" error to a guest,
    so it always resolves to the default coordinates instead of failing."""
    client = _mock_swiggy_client(get_saved_locations={"data": {"locations": []}})
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    assert await service._ensure_dineout_location(session) is True
    assert session.location_lat is not None
    assert session.location_lng is not None


@pytest.mark.asyncio
async def test_ensure_dineout_location_falls_back_when_tool_call_fails():
    client = _mock_swiggy_client(get_saved_locations=None)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    assert await service._ensure_dineout_location(session) is True
    assert session.location_lat is not None
    assert session.location_lng is not None


# ── find_venues: two-step search + render flow ──────────────────────────────

@pytest.mark.asyncio
async def test_find_venues_parses_freeform_search_text_and_resolves_locality_coords():
    """search_restaurants_dineout returns empty structuredContent and puts
    everything in freeform text (confirmed live) -- find_venues must parse
    candidate ids/coordinates out of that text and call render_restaurants_dineout
    for real structured data, then adopt the resolved coordinates for the
    guest's stated locality instead of the fixed default."""
    search_text = (
        "1. Ashz Cafe — Italian, North Indian | 4.2★ | ₹500 for two | Vashi (ID: 662725)\n"
        "Search coordinates: latitude=19.0771, longitude=72.9986\n"
    )

    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": []}}
        if tool_name == "search_restaurants_dineout":
            return {"text": search_text}
        if tool_name == "render_restaurants_dineout":
            return {
                "restaurants": [{
                    "id": "662725", "name": "Ashz Cafe", "avgRating": 4.2,
                    "costForTwo": 500, "distanceKm": 1.2, "cuisines": ["Italian"],
                }],
                "latitude": 19.0771, "longitude": 72.9986,
            }
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1", occasion="birthday", headcount=14)

    result = json.loads(await service._tool_find_venues({"query": "Italian", "locality": "Vashi"}, session))

    assert len(result["venues"]) == 1
    assert result["venues"][0]["name"] == "Ashz Cafe"
    assert session.location_lat == 19.0771
    assert session.location_lng == 72.9986


@pytest.mark.asyncio
async def test_find_venues_handles_string_cost_for_two_without_crashing():
    """render_restaurants_dineout's costForTwo came back as a string in
    practice (e.g. "Rs.1,200"), crashing "cost_for_two * (headcount / 2)"
    with "can't multiply sequence by non-int of type 'float'" (confirmed
    live). Must parse to a real number instead of assuming the type."""
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": []}}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": [{"id": "1", "name": "String Cost Place"}]}
        if tool_name == "render_restaurants_dineout":
            return {"restaurants": [{"id": "1", "name": "String Cost Place", "costForTwo": "Rs.1,200"}]}
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_find_venues({"query": "pizza", "headcount": 6}, session))

    assert result["venues"][0]["cost_for_two"] == 1200.0
    assert result["venues"][0]["estimated_cost"] == 3600.0


@pytest.mark.asyncio
async def test_find_venues_handles_direct_structured_content():
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": []}}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": [{"id": "1", "name": "Direct Restaurant"}]}
        if tool_name == "render_restaurants_dineout":
            return {"restaurants": [{"id": "1", "name": "Direct Restaurant", "costForTwo": 800}]}
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_find_venues({"query": "pizza"}, session))
    assert result["venues"][0]["name"] == "Direct Restaurant"


@pytest.mark.asyncio
async def test_find_venues_reads_deals_from_nested_get_restaurant_details_shape():
    """get_restaurant_details' deals live at the top-level "offers" key, not
    "deals" -- "deals" only exists nested inside "restaurant" (confirmed live,
    same quirk occupancy.py already works around)."""
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": []}}
        if tool_name == "search_restaurants_dineout":
            return {"restaurants": [{"id": "1", "name": "Rooftop Place"}]}
        if tool_name == "render_restaurants_dineout":
            return {"restaurants": [{"id": "1", "name": "Rooftop Place", "costForTwo": 1200}]}
        if tool_name == "get_restaurant_details":
            return {
                "offers": [{"title": "20% off", "discountPercentage": 20, "isFree": False}],
                "amenities": ["Rooftop", "Live Music"],
                "restaurant": {"name": "Rooftop Place", "timings": "6 PM - 11 PM"},
            }
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_find_venues({"query": "rooftop"}, session))
    venue = result["venues"][0]
    assert venue["deals"][0]["title"] == "20% off"
    assert "Rooftop" in venue["amenities"]


@pytest.mark.asyncio
async def test_get_venue_details_reads_nested_restaurant_and_top_level_offers():
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": []}}
        if tool_name == "get_restaurant_details":
            return {
                "offers": [{"title": "Free dessert", "isFree": True}],
                "amenities": ["Bar"],
                "restaurant": {"name": "The Fatty Bao", "timings": "12 PM - 11 PM", "address": "Vashi"},
            }
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_get_venue_details({"restaurant_id": "1"}, session))
    assert result["name"] == "The Fatty Bao"
    assert result["timings"] == "12 PM - 11 PM"
    assert result["deals"][0]["title"] == "Free dessert"


@pytest.mark.asyncio
async def test_check_table_availability_filters_slots_to_requested_date():
    """get_available_slots spans many days regardless of the "date" argument
    (confirmed live) -- must filter to the requested date, not mix days."""
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": []}}
        if tool_name == "get_available_slots":
            return {
                "_meta": {"slots": [
                    {"dateStr": "2026-08-08", "displayTime": "7:00 PM", "deals": [{"isFree": True, "slotId": 1, "itemId": "a-1"}]},
                    {"dateStr": "2026-08-09", "displayTime": "7:30 PM", "deals": [{"isFree": True, "slotId": 2, "itemId": "a-2"}]},
                ]},
            }
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_check_table_availability({"restaurant_id": "1", "date": "2026-08-08"}, session))
    assert len(result["slots"]) == 1
    assert result["slots"][0]["display_time"] == "7:00 PM"


@pytest.mark.asyncio
async def test_find_venues_no_note_when_nothing_found():
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_saved_locations":
            return {"data": {"locations": []}}
        if tool_name == "search_restaurants_dineout":
            return {"text": "No results found for this search."}
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_find_venues({"query": "obscure cuisine"}, session))
    assert result["venues"] == []
    assert "note" in result


# ── budget_remaining ─────────────────────────────────────────────────────────

def test_budget_remaining_none_when_no_budget_set():
    session = ConciergeSession(session_id="s1")
    assert session.budget_remaining is None


def test_budget_remaining_computes_correctly():
    session = ConciergeSession(session_id="s1", budget_inr=10000, budget_spent=3500)
    assert session.budget_remaining == 6500


# ── session JSON round-trip ──────────────────────────────────────────────────

def test_session_serialization_round_trips():
    session = ConciergeSession(
        session_id="s1", occasion="birthday", headcount=14, budget_inr=10000,
        preferences=["pizza", "gaming"], active_bookings=[{"restaurant_name": "Smaaash"}],
    )
    restored = ConciergeSession.from_json(session.to_json())
    assert restored == session


# ── extract_intent ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_intent_parses_structured_fields():
    service = ConciergeService(client=_mock_swiggy_client())
    mock_llm_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "occasion": "birthday", "headcount": 14, "budget_inr": 10000,
        "preferences": ["pizza", "gaming"], "intent": "find_venue",
    })))]
    mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch.object(service, "_get_llm_client", return_value=(mock_llm_client, "fake-model")):
        intent = await service.extract_intent("Plan my friend's 25th birthday, 14 people, pizza and gaming, Rs.10k")

    assert intent["occasion"] == "birthday"
    assert intent["headcount"] == 14
    assert intent["budget_inr"] == 10000
    assert "pizza" in intent["preferences"]


@pytest.mark.asyncio
async def test_extract_intent_never_raises_on_llm_failure():
    service = ConciergeService(client=_mock_swiggy_client())
    with patch.object(service, "_get_llm_client", side_effect=Exception("LLM down")):
        intent = await service.extract_intent("anything")
    assert intent == {}


# ── find_supplies: honest not-found for specialty items ─────────────────────

@pytest.mark.asyncio
async def test_find_supplies_honest_not_found_for_specialty_items():
    products_response = {
        "products": [{
            "name": "Birthday Cake",
            "variants": [{"spinId": "spin1", "price": {"offerPrice": 499}, "quantityDescription": "500g", "isInStockAndAvailable": True}],
        }],
    }
    client = _mock_swiggy_client(get_addresses={"addresses": [{"id": "addr1"}]}, search_products=None)
    call_count = {"n": 0}

    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_addresses":
            return {"addresses": [{"id": "addr1"}]}
        if tool_name == "search_products":
            call_count["n"] += 1
            # first item (cake) found, second (gaming controller) not found
            return products_response if call_count["n"] == 1 else None
        return None

    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_find_supplies({"items": ["birthday cake", "gaming controller"]}, session))

    assert len(result["found"]) == 1
    assert result["found"][0]["name"] == "Birthday Cake"
    assert "gaming controller" in result["not_found"]
    assert "Amazon" in result["not_found_note"] or "Meesho" in result["not_found_note"]


# ── apply_best_coupon: COD filter ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_best_coupon_filters_online_payment_required():
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_addresses":
            return {"addresses": [{"id": "addr1"}]}
        if tool_name == "fetch_food_coupons":
            return {
                "bestCoupons": [
                    {"code": "ONLINE50", "discountAmount": 50, "requiresOnlinePayment": True},
                    {"code": "COD20", "discountAmount": 20, "requiresOnlinePayment": False},
                ],
                "moreOffers": [],
            }
        if tool_name == "apply_food_coupon":
            return {"applied": True}
        if tool_name == "get_food_cart":
            return {"bill": {"total": 380}}
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_apply_best_coupon({"restaurant_id": "r1"}, session))

    assert result["applied_coupon"]["code"] == "COD20"


@pytest.mark.asyncio
async def test_apply_best_coupon_no_cod_coupons_available():
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_addresses":
            return {"addresses": [{"id": "addr1"}]}
        if tool_name == "fetch_food_coupons":
            return {"bestCoupons": [{"code": "ONLINE50", "discountAmount": 50, "requiresOnlinePayment": True}], "moreOffers": []}
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    result = json.loads(await service._tool_apply_best_coupon({"restaurant_id": "r1"}, session))
    assert "note" in result
    assert "Cash-on-Delivery" in result["note"]


# ── book_table / order_supplies: staging notice when not configured ─────────

@pytest.mark.asyncio
async def test_book_table_shows_staging_notice_when_staging_not_configured():
    service = ConciergeService(client=_mock_swiggy_client())
    session = ConciergeSession(session_id="s1")

    with patch("app.domain.services.concierge_service._staging_enabled", return_value=False):
        result = json.loads(await service._tool_book_table({
            "restaurant_id": "r1", "restaurant_name": "The Fatty Bao", "slot_id": 4242,
            "item_id": "r1-ticket_7", "reservation_time": 1751289600, "headcount": 4,
            "estimated_cost": 1200,
        }, session))

    assert result["staging_enabled"] is False
    assert result["booking"]["status"] == "pending_staging"
    assert len(session.active_bookings) == 1
    assert session.budget_spent == 1200


@pytest.mark.asyncio
async def test_order_supplies_shows_staging_notice_when_staging_not_configured():
    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_cart":
            return {"items": [{"name": "Cake"}], "bill": {"total": 499}}
        return None

    client = MagicMock()
    client.call_tool = AsyncMock(side_effect=_call_tool)
    service = ConciergeService(client=client)
    session = ConciergeSession(session_id="s1")

    with patch("app.domain.services.concierge_service._staging_enabled", return_value=False):
        result = json.loads(await service._tool_order_supplies({}, session))

    assert result["staging_enabled"] is False
    assert result["order"]["status"] == "pending_staging"
    assert session.budget_spent == 499


# ── handle_message: streaming generator ─────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_message_yields_streamed_text_without_tool_calls():
    service = ConciergeService(client=_mock_swiggy_client())
    session = ConciergeSession(session_id="s1")

    mock_llm_client = MagicMock()
    intent_response = MagicMock()
    intent_response.choices = [MagicMock(message=MagicMock(content="{}"))]

    final_response = MagicMock()
    final_response.choices = [MagicMock(message=MagicMock(content="Hello! How can I help you plan your event?", tool_calls=None))]

    mock_llm_client.chat.completions.create = AsyncMock(side_effect=[intent_response, final_response])

    with patch.object(service, "_get_llm_client", return_value=(mock_llm_client, "fake-model")), \
         patch.object(service, "save_session", new=AsyncMock()):
        chunks = [c async for c in service.handle_message("hi", session)]

    text = "".join(c["content"] for c in chunks if c["type"] == "text")
    assert text.strip() == "Hello! How can I help you plan your event?"


@pytest.mark.asyncio
async def test_handle_message_never_raises_saves_session_even_on_error():
    """Hard rule: a guest never sees a raw exception message -- only the fixed,
    friendly fallback strings, regardless of what actually broke."""
    service = ConciergeService(client=_mock_swiggy_client())
    session = ConciergeSession(session_id="s1")
    save_mock = AsyncMock()

    with patch.object(service, "_get_llm_client", side_effect=Exception("some raw internal exception detail")), \
         patch.object(service, "save_session", new=save_mock):
        chunks = [c async for c in service.handle_message("hi", session)]

    text_chunks = [c["content"] for c in chunks if c["type"] == "text"]
    assert any("wrong" in c.lower() for c in text_chunks)
    assert not any("some raw internal exception detail" in c for c in text_chunks)
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_tool_never_leaks_raw_exception_or_tool_name():
    service = ConciergeService(client=_mock_swiggy_client())
    session = ConciergeSession(session_id="s1")

    # _dispatch is built at __init__ time from bound methods -- patching the
    # dict entry directly (not patch.object on the instance) actually
    # intercepts the call made through _dispatch_tool.
    service._dispatch["find_venues"] = AsyncMock(
        side_effect=Exception("sequence item 0: expected str instance, dict found")
    )
    result = json.loads(await service._dispatch_tool("find_venues", {}, session))

    assert "sequence item" not in result["error"]
    assert "find_venues" not in result["error"]


@pytest.mark.asyncio
async def test_handle_message_yields_tool_result_chunk_before_final_text():
    service = ConciergeService(client=_mock_swiggy_client())
    session = ConciergeSession(session_id="s1")

    mock_llm_client = MagicMock()
    intent_response = MagicMock()
    intent_response.choices = [MagicMock(message=MagicMock(content="{}"))]

    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "get_budget_summary"
    tool_call.function.arguments = "{}"
    tool_call_response = MagicMock()
    tool_call_response.choices = [MagicMock(message=MagicMock(content="", tool_calls=[tool_call]))]

    final_response = MagicMock()
    final_response.choices = [MagicMock(message=MagicMock(content="Here's your budget.", tool_calls=None))]

    mock_llm_client.chat.completions.create = AsyncMock(
        side_effect=[intent_response, tool_call_response, final_response]
    )

    with patch.object(service, "_get_llm_client", return_value=(mock_llm_client, "fake-model")), \
         patch.object(service, "_dispatch_tool", new=AsyncMock(return_value=json.dumps({"budget_remaining": 5000}))), \
         patch.object(service, "save_session", new=AsyncMock()):
        chunks = [c async for c in service.handle_message("what's my budget", session)]

    tool_chunks = [c for c in chunks if c["type"] == "tool_result"]
    assert len(tool_chunks) == 1
    assert tool_chunks[0]["tool"] == "get_budget_summary"
    assert tool_chunks[0]["data"] == {"budget_remaining": 5000}
    text = "".join(c["content"] for c in chunks if c["type"] == "text")
    assert text.strip() == "Here's your budget."

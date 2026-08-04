"""dineout_manager_node — P6-S12.

11th LangGraph node. Runs in parallel with reservation / complaint_intelligence
/ inventory / market_intel in the fan-out from qdrant_enrichment.

IMPORTANT — Swiggy MCP is 100% consumer-facing (confirmed from Swiggy Builders Club docs).
This means:

  WHAT WORKS with consumer API:
  - get_available_slots(restaurantId=OUR_ID) → reads YOUR restaurant's public slot
    visibility as any consumer would see it. Valid if SWIGGY_DINEOUT_RESTAURANT_ID is set.

  WHAT DOES NOT WORK (needs Swiggy Partner API — not in Builders Club):
  - Opening / closing your own Dineout slots
  - Seeing your incoming bookings / guest list
  - book_table does NOT open slots at your own restaurant — it books a table FOR
    a consumer AT a restaurant. "Open more slots" via book_table is architecturally wrong.

Current behaviour:
  get_saved_locations() → lat/lng
  get_available_slots(restaurantId=OUR_ID, date=tonight, lat, lng)
  → assess how many dinner slots are visible to consumers tonight
  → write dineout_manager_output + dineout_manager_assumptions to state

FUTURE USE (needs Swiggy Partner API): actual slot management — open/close slots,
view incoming reservation list, manage table inventory.

Degrades gracefully to None when SWIGGY_DINEOUT_RESTAURANT_ID not set or any failure.
"""

import asyncio
from datetime import date
from typing import Optional

import structlog

from app.core.constants import DEFAULT_RESTAURANT_LAT, DEFAULT_RESTAURANT_LNG
from app.core.settings import get_settings
from app.infrastructure.swiggy.client import DINEOUT_ENDPOINT, SwiggyMCPClient
from app.orchestration.state import OrchestratorState

# structlog, not stdlib logging — see infrastructure/swiggy/enrichers/procurement.py for why.
log = structlog.get_logger()

_DINNER_HOURS = {"19:00", "19:30", "20:00", "20:30", "21:00", "21:30"}
_MAX_DINNER_SLOTS   = len(_DINNER_HOURS)
_LOW_SLOT_THRESHOLD = 2   # dinner-hour times still listed <= this → recommend opening more
                          # (get_available_slots carries no numeric availabilityCount field
                          # live -- see OccupancyEnricher's module docstring for the same
                          # finding. Proxy: fewer listed times = busier, same direction.)


async def dineout_manager_node(
    state: OrchestratorState,
    swiggy_client: SwiggyMCPClient,
) -> OrchestratorState:
    """
    Checks own Dineout slot availability for tonight and writes assessment to state.
    Never raises — returns state unchanged on any failure or missing config.
    """
    if state.get("error"):
        return state

    if not swiggy_client.is_available():
        return {
            **state,
            "dineout_manager_output": None,
            "dineout_manager_assumptions": {"swiggy_available": False},
        }

    try:
        result = await _check_own_slots(state, swiggy_client)
    except Exception as exc:
        log.warning("dineout_manager_node_error", error=str(exc))
        result = None

    if result is None:
        return {
            **state,
            "dineout_manager_output": None,
            "dineout_manager_assumptions": {"swiggy_available": True, "own_slots_checked": False},
        }

    assumptions = {
        "swiggy_available":          True,
        "own_slots_checked":         True,
        "assumed_dineout_slots_low": result.get("open_more_recommended", False),
        "assumed_slots_tonight":     result.get("total_slots_tonight", 0),
        "low_availability_slots":    result.get("low_availability_slots", 0),
        "fetched_at":                result.get("fetched_at"),
    }

    return {
        **state,
        "dineout_manager_output":    result,
        "dineout_manager_assumptions": assumptions,
    }


# ── internal ─────────────────────────────────────────────────────────────────

async def _check_own_slots(
    state: OrchestratorState,
    client: SwiggyMCPClient,
) -> Optional[dict]:
    settings = get_settings()

    # Resolve our Dineout restaurant ID — settings → restaurant_profile → fail
    restaurant_profile = state.get("restaurant_profile") or {}
    our_r_id = (
        restaurant_profile.get("dineout_restaurant_id")
        or settings.swiggy_dineout_restaurant_id
        or ""
    )
    if not our_r_id:
        log.info("dineout_manager_no_restaurant_id", hint="set SWIGGY_DINEOUT_RESTAURANT_ID to enable")
        return None

    # Step 1 — resolve Dineout lat/lng (same pattern as OccupancyEnricher)
    location = await _get_location(client)
    if not location:
        return None

    tonight = date.today().isoformat()

    # Step 2 — get our own slot availability tonight
    data = await client.call_tool(
        DINEOUT_ENDPOINT,
        "get_available_slots",
        {
            "restaurantId": str(our_r_id),
            "date":         tonight,
            "latitude":     location["lat"],
            "longitude":    location["lng"],
        },
    )
    if not data:
        return None

    # Slots live in the JSON-RPC result's _meta.slots, not structuredContent
    # (confirmed live -- client.py's call_tool() merges _meta into its return
    # value), and the response spans many days regardless of the "date"
    # argument, so this filters to tonight's dateStr explicitly.
    slots = (data.get("_meta") or {}).get("slots") or data.get("slots") or []
    dinner_slots = [
        s for s in slots
        if s.get("dateStr") == tonight and _is_dinner_slot(s.get("displayTime") or "")
    ]

    if not dinner_slots:
        return {
            "total_slots_tonight":    0,
            "low_availability_slots": _MAX_DINNER_SLOTS,
            "open_more_recommended":  True,
            "prompt_text":            "No Dineout dinner slots found for tonight -- fully booked or unlisted.",
            "fetched_at":             tonight,
        }

    total = len(dinner_slots)
    # "low_availability_slots" reinterpreted as "how many of the possible
    # dinner-hour times are NOT currently listed as bookable" -- no per-slot
    # numeric count exists live, so time-slot presence/absence is the proxy.
    low = max(0, _MAX_DINNER_SLOTS - total)
    open_more = total <= _LOW_SLOT_THRESHOLD

    result = {
        "total_slots_tonight":    total,
        "low_availability_slots": low,
        "open_more_recommended":  open_more,
        "slot_details": [{"time": s.get("displayTime")} for s in dinner_slots],
        "prompt_text": _build_prompt(total, low, open_more),
        "fetched_at":  tonight,
    }

    log.info(
        "dineout_manager_done",
        total=total, low=low, open_more=open_more,
    )
    return result


async def _get_location(client: SwiggyMCPClient) -> Optional[dict]:
    """Same get_saved_locations quirks as OccupancyEnricher._get_location() --
    payload nests one level deeper under "data", and never includes lat/lng
    (confirmed live), so this falls back to DEFAULT_RESTAURANT_LAT/LNG for any
    location that has an id but no lat/lng."""
    data = await client.call_tool(DINEOUT_ENDPOINT, "get_saved_locations", {})
    if not data:
        return None
    locations = (data.get("data") or {}).get("locations") or data.get("locations") or []
    for loc in locations:
        if not loc.get("id"):
            continue
        lat = loc.get("lat") or DEFAULT_RESTAURANT_LAT
        lng = loc.get("lng") or DEFAULT_RESTAURANT_LNG
        return {"lat": float(lat), "lng": float(lng)}
    return None


def _is_dinner_slot(display_time: str) -> bool:
    try:
        parts = display_time.lower().replace(".", "").strip().split()
        if len(parts) < 2:
            return False
        time_part, meridiem = parts[0], parts[1]
        hh, mm = (int(x) for x in time_part.split(":"))
        if meridiem == "pm" and hh != 12:
            hh += 12
        return f"{hh:02d}:{mm:02d}" in _DINNER_HOURS
    except Exception:
        return False


def _build_prompt(total: int, low: int, open_more: bool) -> str:
    lines = ["## Your Dineout Availability Tonight"]
    lines.append(
        f"{total} of {_MAX_DINNER_SLOTS} dinner-hour times currently listed as bookable "
        f"({low} unlisted/fully booked)."
    )
    if open_more:
        lines.append(
            "Recommendation: consider opening additional Dineout slots — "
            f"only {total} dinner-hour time{'s' if total != 1 else ''} still bookable tonight."
        )
    else:
        lines.append("Dineout capacity appears adequate for tonight.")
    return "\n".join(lines)

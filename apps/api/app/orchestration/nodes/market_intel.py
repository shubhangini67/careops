"""market_intel_node — P6-S11, extended P6-A24.

10th LangGraph node. Runs in parallel with reservation / complaint_intelligence
/ inventory in the fan-out from qdrant_enrichment, then fans in to
menu_intelligence alongside the other three.

Calls MarketIntelService which runs CompetitorEnricher + OccupancyEnricher
concurrently. Their outputs are written to state so:
  - aggregator/critic receive full market context (market_intel_output)
  - menu_intelligence can read swiggy_competitor_context for the Area Market
    Signals section it injects into its LLM prompt
  - reservation can read swiggy_occupancy_context for the Occupancy Signal section
  - swiggy_procurement_options is populated by inventory_node itself, which calls
    ProcurementEnricher directly with actual shortage_items after its own analysis
    completes (not by this node, and not from your_go_to_items — see procurement.py's
    module docstring for why that tool is deliberately unused)

P6-A24: weather/trends/compliance-alerts signals (none of which is Swiggy MCP)
were already fetched earlier in the graph by demand_forecast_node and sit in
state as weather_signal/trends_signal/compliance_alerts_signal. This node reads
them (never re-fetches) and passes them to MarketIntelService so they merge
into market_intel_output["live_signals_text"] alongside the Swiggy signals --
critically, this must happen even when Swiggy itself is unavailable, so one
source going down never blocks the other three from reaching aggregator/critic.

Fails open: Swiggy-specific fields are null when Swiggy is unavailable or
enrichers fail, but live_signals_text still carries whatever non-Swiggy
signals are present.
"""

import asyncio
from typing import Callable

from app.orchestration.state import OrchestratorState
from app.domain.services.market_intel_service import MarketIntelService
from app.infrastructure.swiggy.client import SwiggyMCPClient


def _load_our_items(session) -> list[dict]:
    """Sync DB query — run via asyncio.to_thread so it doesn't block the parallel fan-out."""
    from app.infrastructure.db.models import MenuItem

    items = session.query(MenuItem).filter(MenuItem.is_available.is_(True)).all()
    return [{"name": i.name, "price": i.price, "category": i.category} for i in items]


async def market_intel_node(
    state: OrchestratorState,
    swiggy_client: SwiggyMCPClient,
    db_factory: Callable,
) -> OrchestratorState:
    """
    Fetches live Swiggy market intelligence and writes it to state.
    Never raises — returns state unchanged on any failure or missing token.
    """
    if state.get("error"):
        return state

    live_signals = {
        "weather_signal":           state.get("weather_signal"),
        "trends_signal":            state.get("trends_signal"),
        "compliance_alerts_signal": state.get("compliance_alerts_signal"),
    }

    if not swiggy_client.is_available():
        service = MarketIntelService(swiggy_client)
        market_intel_output = service.build_signals_only_result(live_signals)["market_intel_output"]
        return {
            **state,
            "swiggy_competitor_context": None,
            "swiggy_occupancy_context":  None,
            "market_intel_output":       market_intel_output,
            "market_intel_assumptions":  {"swiggy_available": False},
        }

    scenario_profile = state.get("scenario_profile") or {}

    # Load our own menu (name/price/category) so CompetitorEnricher can compute
    # pricing alerts, dish-level comparisons, and category pricing during a real
    # planning run — not just via the standalone /market/pulse endpoint.
    session = db_factory()
    try:
        our_items = await asyncio.to_thread(_load_our_items, session)
    finally:
        session.close()

    context = {
        "org_id":    state.get("org_id") or 0,
        "cuisine":   scenario_profile.get("cuisine") or "restaurant",
        "our_items": our_items,
        # address_id falls back to settings.swiggy_address_id inside each enricher
        **live_signals,
    }

    service = MarketIntelService(swiggy_client)
    result  = await service.run(context)

    market_intel = result.get("market_intel_output") or {}
    dineout_deals_count = (
        (market_intel.get("dineout_deals_count") or 0)
        + len(market_intel.get("slot_deals_found") or [])
    )
    assumptions = {
        "swiggy_available":             True,
        "assumed_competitor_avg_price": market_intel.get("competitor_pricing"),
        "assumed_area_occupancy":       market_intel.get("area_occupancy"),
        "pricing_alerts_count":         len(market_intel.get("pricing_alerts") or []),
        "tonight_busy":                 market_intel.get("tonight_busy"),
        # P6-MI08 (Diff 7): count of live Dineout deals/promos tonight in the area —
        # used to catch tonight_busy=True occupancy signals that may be inflated
        # because nearby restaurants are actively absorbing demand with promotions.
        "dineout_deals_count":          dineout_deals_count,
        "fetched_at":                   market_intel.get("fetched_at"),
    }

    return {
        **state,
        "swiggy_competitor_context": result.get("swiggy_competitor_context"),
        "swiggy_occupancy_context":  result.get("swiggy_occupancy_context"),
        "market_intel_output":       market_intel,
        "market_intel_assumptions":  assumptions,
    }

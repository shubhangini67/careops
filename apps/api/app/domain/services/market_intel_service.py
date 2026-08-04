"""MarketIntelService — P6-S10, extended P6-A24.

Orchestrates all three Swiggy enrichers concurrently at planning time and
assembles their outputs into state fields ready for the pipeline nodes.

Responsibilities:
  - Run CompetitorEnricher, OccupancyEnricher, ProcurementEnricher in parallel
  - Return a structured result mapping each output to its OrchestratorState key
  - Fail open: any enricher returning None is silently omitted; the service
    never raises, so callers (LangGraph nodes) always get a usable result

P6-A24 (live-intelligence unification): weather/holiday (P6-A21), industry
trends (P6-A22), and regulatory alerts (P6-A23) are NOT Swiggy MCP and are
already fetched earlier in the graph by demand_forecast_node (written to
state as weather_signal/trends_signal/compliance_alerts_signal) -- this
service does not re-fetch them, just merges their prompt_text alongside the
Swiggy competitor/occupancy signals into one combined market_intel_output
["live_signals_text"] field, added inside this existing service rather than
a new graph node. Each of the 5 sources (competitor, occupancy, weather,
trends, compliance) stays independently optional -- any subset being None
never blocks the others from appearing in the combined text.

Returned dict shape:
  {
    "swiggy_competitor_context":  {...} | None,
    "swiggy_occupancy_context":   {...} | None,
    "swiggy_procurement_options": {...} | None,
    "market_intel_output": {
      "competitor_pricing":   {...} | None,
      "area_occupancy":       "HIGH" | "MEDIUM" | "LOW" | None,
      "pricing_alerts":       [...],
      "tonight_busy":         bool | None,
      "procurement_options":  [...],
      "live_signals_text":    str,  # combined Area & Live Signals section (P6-A24)
      "fetched_at":           "YYYY-MM-DD",
    },
  }
"""

import asyncio
from datetime import date
from typing import Optional

import structlog

from app.infrastructure.swiggy.circuit_breaker import get_state
from app.infrastructure.swiggy.client import SwiggyMCPClient
from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher
from app.infrastructure.swiggy.enrichers.occupancy import OccupancyEnricher

# structlog, not stdlib logging — see procurement.py enricher for why.
log = structlog.get_logger()


class MarketIntelService:
    """Parallel orchestrator for all three Swiggy enrichers.

    Instantiate once per planning run, passing the org's SwiggyMCPClient.
    Call run() with planning context; it returns all enricher outputs ready to
    be written into OrchestratorState.
    """

    def __init__(self, client: SwiggyMCPClient) -> None:
        self._competitor = CompetitorEnricher(client)
        self._occupancy  = OccupancyEnricher(client)

    # ── public ───────────────────────────────────────────────────────────────

    async def run(self, context: dict) -> dict:
        """Run all enrichers concurrently and return combined state payloads.

        context keys used (all optional — enrichers degrade gracefully):
          org_id                    int        — scopes Redis cache keys
          address_id                str        — Swiggy Food + Instamart addressId
          cuisine                   str        — e.g. "North Indian"
          our_items                 list       — [{"name": str, "price": float}, ...]
          shortage_items            list[str]  — ingredients that are low in stock
          weather_signal            dict|None  — P6-A21, already fetched by demand_forecast_node
          trends_signal             dict|None  — P6-A22, already fetched by demand_forecast_node
          compliance_alerts_signal  dict|None  — P6-A23, already fetched by demand_forecast_node

        Returns a dict with four keys:
          swiggy_competitor_context   → CompetitorEnricher output or None
          swiggy_occupancy_context    → OccupancyEnricher output or None
          swiggy_procurement_options  → ProcurementEnricher output or None
          market_intel_output         → assembled summary for market_intel_node,
                                         including live_signals_text (P6-A24)
        """
        try:
            return await self._run(context)
        except Exception as exc:
            log.warning("market_intel_service_error", error=str(exc))
            return self.build_signals_only_result(context)

    # ── internal ─────────────────────────────────────────────────────────────

    async def _run(self, context: dict) -> dict:
        competitor_ctx, occupancy_ctx = await asyncio.gather(
            self._competitor.enrich(context),
            self._occupancy.enrich(context),
            return_exceptions=False,
        )

        log.info(
            "market_intel_service_done",
            competitor=competitor_ctx is not None,
            occupancy=occupancy_ctx is not None,
        )

        market_intel_output = self._assemble_market_intel(
            competitor_ctx, occupancy_ctx,
            weather_signal=context.get("weather_signal"),
            trends_signal=context.get("trends_signal"),
            compliance_alerts_signal=context.get("compliance_alerts_signal"),
        )
        if competitor_ctx is None:
            market_intel_output["competitor_status"] = await self._competitor_status()

        return {
            "swiggy_competitor_context": competitor_ctx,
            "swiggy_occupancy_context":  occupancy_ctx,
            "market_intel_output":       market_intel_output,
        }

    def _assemble_market_intel(
        self,
        competitor_ctx: Optional[dict],
        occupancy_ctx:  Optional[dict],
        weather_signal: Optional[dict] = None,
        trends_signal: Optional[dict] = None,
        compliance_alerts_signal: Optional[dict] = None,
    ) -> dict:
        """Build the market_intel_output dict that market_intel_node writes to state.

        Area aggregates only (P6-A20) -- every field here traces back to an
        already-anonymised CompetitorEnricher/OccupancyEnricher field. No restaurant
        is individually named or attributed a specific price/deal anywhere in this dict.
        """
        pricing_alerts   = competitor_ctx.get("alerts", [])      if competitor_ctx else []
        area_avg         = competitor_ctx.get("area_avg")         if competitor_ctx else None
        occupancy_signal = occupancy_ctx.get("occupancy_signal")  if occupancy_ctx  else None
        tonight_busy     = occupancy_ctx.get("tonight_busy")      if occupancy_ctx  else None

        # P6-MI06/MI09: area deals, pricing impact model (bonus, exact-match only)
        deals_active_count = competitor_ctx.get("deals_active_count") if competitor_ctx else None
        deals_summary       = competitor_ctx.get("deals_summary")      if competitor_ctx else None
        pricing_impact   = competitor_ctx.get("pricing_impact")   if competitor_ctx else None
        # Category-level pricing (dish-name-independent) — the primary market intel signal
        category_pricing = competitor_ctx.get("category_pricing") if competitor_ctx else None
        # Nearby market landscape (aggregate rating/cost-for-two range) + synthesized ranking
        landscape_summary = competitor_ctx.get("landscape_summary") if competitor_ctx else None
        positioning        = competitor_ctx.get("positioning")        if competitor_ctx else None
        # Market context signals: menu breadth, cuisine crowding, veg mix
        menu_breadth     = competitor_ctx.get("menu_breadth")     if competitor_ctx else None
        cuisine_crowding = competitor_ctx.get("cuisine_crowding") if competitor_ctx else None
        veg_mix          = competitor_ctx.get("veg_mix")          if competitor_ctx else None

        # P6-MI07: Dineout deals — from get_restaurant_details + parsed slot deals[]
        dineout_deals_count   = occupancy_ctx.get("dineout_deals_count")   if occupancy_ctx else None
        dineout_deals_summary = occupancy_ctx.get("dineout_deals_summary") if occupancy_ctx else None
        slot_deals_found      = occupancy_ctx.get("slot_deals_found")      if occupancy_ctx else None
        # Occupancy-by-time-slot chart data
        slot_availability_by_time = occupancy_ctx.get("slot_availability_by_time") if occupancy_ctx else None

        return {
            "competitor_pricing":         area_avg,
            "area_occupancy":             occupancy_signal,
            "pricing_alerts":             pricing_alerts,
            "tonight_busy":               tonight_busy,
            "deals_active_count":         deals_active_count,
            "deals_summary":              deals_summary,
            "pricing_impact":             pricing_impact,
            "category_pricing":           category_pricing,
            "landscape_summary":          landscape_summary,
            "positioning":                positioning,
            "menu_breadth":               menu_breadth,
            "cuisine_crowding":           cuisine_crowding,
            "veg_mix":                    veg_mix,
            "dineout_deals_count":        dineout_deals_count,
            "dineout_deals_summary":      dineout_deals_summary,
            "slot_deals_found":           slot_deals_found,
            "slot_availability_by_time":  slot_availability_by_time,
            "live_signals_text": self._build_live_signals_text(
                competitor_ctx, occupancy_ctx, weather_signal, trends_signal, compliance_alerts_signal,
            ),
            "fetched_at":                 date.today().isoformat(),
        }

    def _build_live_signals_text(
        self,
        competitor_ctx: Optional[dict],
        occupancy_ctx: Optional[dict],
        weather_signal: Optional[dict],
        trends_signal: Optional[dict],
        compliance_alerts_signal: Optional[dict],
    ) -> str:
        """Combine all five live-intelligence sources into one 'Area & Live
        Signals' text block (P6-A24) -- weather/holiday, industry trends,
        regulatory alerts (none of which is Swiggy MCP) alongside the existing
        anonymised Swiggy competitor/occupancy signals. Each source contributes
        its own prompt_text independently; any subset being None just means
        that section is omitted, never blocks the others or raises.
        """
        sections = [
            (competitor_ctx or {}).get("prompt_text"),
            (occupancy_ctx or {}).get("prompt_text"),
            (weather_signal or {}).get("prompt_text"),
            (trends_signal or {}).get("prompt_text"),
            (compliance_alerts_signal or {}).get("prompt_text"),
        ]
        body = "\n\n".join(s for s in sections if s)
        if not body:
            return ""
        return f"## Area & Live Signals\n\n{body}"

    async def _competitor_status(self) -> dict:
        """Distinguish "temporarily degraded, will retry" from "no data" when
        CompetitorEnricher returns None, so the frontend doesn't show the same
        blank state for both. Never raises — defaults to "no_data" on any error.
        """
        try:
            circuit_state = await get_state("swiggy", "food")
        except Exception:
            return {"state": "no_data", "resets_in_seconds": None}

        if circuit_state.get("state") == "open":
            return {
                "state": "degraded_circuit_open",
                "resets_in_seconds": circuit_state.get("resets_in_seconds"),
            }
        return {"state": "no_data", "resets_in_seconds": None}

    def build_signals_only_result(self, context: Optional[dict] = None) -> dict:
        """Competitor/occupancy data unavailable (Swiggy down, or run() itself
        raised), but the three non-Swiggy live signals already sit in context
        (fetched earlier by demand_forecast_node) -- they still surface in
        live_signals_text rather than being wiped out by an unrelated Swiggy-
        side failure. Public: called both internally (run()'s except branch)
        and directly by market_intel_node when swiggy_client.is_available()
        is False."""
        context = context or {}
        return {
            "swiggy_competitor_context": None,
            "swiggy_occupancy_context":  None,
            "market_intel_output": {
                "competitor_pricing":       None,
                "area_occupancy":           None,
                "pricing_alerts":           [],
                "tonight_busy":             None,
                "deals_active_count":       None,
                "deals_summary":            None,
                "pricing_impact":           None,
                "category_pricing":         None,
                "landscape_summary":        None,
                "positioning":              None,
                "menu_breadth":             None,
                "cuisine_crowding":         None,
                "veg_mix":                  None,
                "dineout_deals_count":      None,
                "dineout_deals_summary":    None,
                "slot_deals_found":         None,
                "slot_availability_by_time": None,
                "live_signals_text": self._build_live_signals_text(
                    None, None,
                    context.get("weather_signal"),
                    context.get("trends_signal"),
                    context.get("compliance_alerts_signal"),
                ),
                "fetched_at":               date.today().isoformat(),
            },
        }

"""live_signals_node.

Runs first, right after ops_manager -- before demand_forecast. Fetches all
three non-Swiggy live-intelligence signals (weather + holiday, industry
trends, regulatory/FSSAI alerts) up front, in one place, so demand_forecast
(which needs weather to apply its multiplier) and every downstream node
reacts to one consistent snapshot instead of demand_forecast_node silently
owning this fetch itself.

This is a straight extraction of what demand_forecast_node used to do
inline (P6-A21/A22/A23) -- not new fetch logic, no new dependency, no new
failure mode. None of the three sources is Swiggy MCP, so none needs
consent/compliance gating, and none needs anything else in state to run --
just target_date, already set at request time by make_initial_state.

Swiggy-specific signals (competitor pricing via market_intel_node, area
occupancy via market_intel_node, own-restaurant Dineout slot visibility via
dineout_manager_node) deliberately stay where they are, in the parallel
fan-out after qdrant_enrichment -- not pulled into this node. Two reasons:
  1. Their fetch cost currently overlaps with reservation/complaint/
     inventory instead of blocking everything up front; moving them here
     would add their latency to the critical path of every single run.
  2. Swiggy's own contribution should stay a clearly, individually
     attributed capability (its own specialist cards), not folded into a
     generic "live signals" bucket -- see CLAUDE.md's Swiggy-attribution
     requirement for the demo.

Fails open on all three sources independently, exactly as before.
"""

import asyncio
from datetime import datetime

from app.core.calendar_utils import get_date_context
from app.core.constants import DEFAULT_RESTAURANT_LAT, DEFAULT_RESTAURANT_LNG
from app.infrastructure.external.compliance_alerts_service import ComplianceAlertsService
from app.infrastructure.external.trends_service import TrendsService
from app.infrastructure.external.weather_service import WeatherService
from app.orchestration.state import OrchestratorState


async def live_signals_node(state: OrchestratorState) -> OrchestratorState:
    """Fetch weather+holiday, industry trends, and regulatory alerts.

    Never raises -- any failure here just means those signals stay None for
    the rest of the run (demand_forecast falls back to Prophet's raw output,
    market_intel_node's live_signals_text simply omits the missing section).
    """
    if state.get("error"):
        return state

    # Simulation mode never touches real external services -- matches
    # demand_forecast_node's own pre-extraction behavior (its simulation_mode
    # branch returned before ever reaching this fetch), and keeps the E2E
    # "unit" tests (test_e2e_friday_rush.py) from making real network calls
    # to Open-Meteo/RSS/FSSAI on every run.
    if state.get("simulation_mode", False):
        return state

    try:
        target_date_str = state.get("target_date")
        target_date = datetime.fromisoformat(target_date_str) if target_date_str else None

        weather_signal = None
        is_holiday, holiday_name = False, None
        if target_date is not None:
            _, is_holiday, holiday_name = get_date_context(target_date.date().isoformat())
            weather_signal = await WeatherService().get_forecast(
                lat=DEFAULT_RESTAURANT_LAT,
                lng=DEFAULT_RESTAURANT_LNG,
                target_date=target_date.date(),
            )

        trends_signal, compliance_alerts_signal = await asyncio.gather(
            TrendsService().get_digest(),
            ComplianceAlertsService().get_alerts(),
        )

        return {
            **state,
            "weather_signal":           weather_signal,
            "trends_signal":            trends_signal,
            "compliance_alerts_signal": compliance_alerts_signal,
            "holiday_context":          {"is_holiday": is_holiday, "holiday_name": holiday_name},
        }

    except Exception:
        return {
            **state,
            "weather_signal":           None,
            "trends_signal":            None,
            "compliance_alerts_signal": None,
            "holiday_context":          None,
        }

"""LiveScenarioComposer.

Backs the "Run for today" instant path -- replaces forcing "right now,
whatever today actually is" through ScenarioRecommender's fixed 4-preset
pick. Live-verified that forcing a fit was actively wrong, not just
inelegant: on a plain Wednesday with a few ingredient shortages and light
rain, ScenarioRecommender picked "low_stock_weekend" -- the LLM reasoned
correctly about the shortage signal, then stapled a label onto it that
claims it's a weekend when it isn't, because the preset bundles "tight
ingredient constraints" and "it's a weekend" into one ID and nothing forces
those two facts to actually agree.

This service never picks from a fixed set. It composes a fresh label +
service window + operational focus from what's actually true right now --
real day-of-week, real current time, weather, holiday, inventory shortage
count, area occupancy -- the same way ScenarioProfileService turns free
text into a profile, except the input here is live signals instead of an
owner's sentence. Output is shaped identically to ScenarioProfileService's
(id/label/description/service_window/operational_focus/cuisine) so it slots
into the exact same ops_manager_node custom_profile branch, no graph change
needed.

The 4 presets (friday_rush/weekday_lunch/holiday_spike/low_stock_weekend)
are untouched and still exist as deliberate manual shortcuts for exploring
a hypothetical scenario on a future date -- this service is specifically
for "right now," not a replacement for them.

Never raises -- falls back to a deterministic profile built directly from
the real signals (never a mismatched label, by construction: the fallback's
day-type language always comes from the actual weekday/holiday check, never
from a hardcoded preset name).
"""

import asyncio
import json
import re
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.orm import Session

from app.core.calendar_utils import get_date_context
from app.core.constants import DEFAULT_RESTAURANT_LAT, DEFAULT_RESTAURANT_LNG
from app.domain.services.inventory_service import InventoryService
from app.domain.services.market_intel_service import MarketIntelService
from app.domain.services.run_service import RunService
from app.infrastructure.db.models import Organization
from app.infrastructure.external.weather_service import WeatherService
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.swiggy.client import SwiggyMCPClient

log = structlog.get_logger()

_RESTAURANT_TZ = ZoneInfo("Asia/Kolkata")


class LiveScenarioComposer:
    """Composes an ad-hoc scenario profile from live signals, not a fixed list.

    Instantiate once per request. compose() never raises -- any internal
    failure degrades to a deterministic, signal-grounded profile instead.
    """

    def __init__(self, db: Session, swiggy_client: SwiggyMCPClient, llm: BaseLLMProvider) -> None:
        self.db = db
        self.swiggy_client = swiggy_client
        self.llm = llm

    # ── public ───────────────────────────────────────────────────────────────

    async def compose(self, org_id: int, target_date: str) -> dict:
        """Return {profile, reason, confidence, signals_used}.

        profile is shaped like ScenarioProfile: {id, label, description,
        service_window, operational_focus, cuisine}.
        """
        try:
            return await self._compose(org_id, target_date)
        except Exception as exc:
            log.warning("live_scenario_composer_error", error=str(exc))
            return self._fallback(target_date)

    # ── internal ─────────────────────────────────────────────────────────────

    async def _compose(self, org_id: int, target_date: str) -> dict:
        is_weekend, is_holiday, holiday_name = get_date_context(target_date)
        now_local = datetime.now(_RESTAURANT_TZ)
        current_time_str = now_local.strftime("%H:%M")

        weather_signal, market_context, shortage_count, recent_runs_summary = await asyncio.gather(
            self._get_weather_signal(target_date),
            self._get_market_context(org_id),
            self._shortage_count(),
            self._recent_runs_summary(org_id),
        )
        occupancy_signal = market_context.get("area_occupancy")

        signals_used = [f"current_time:{current_time_str}"]
        if is_holiday:
            signals_used.append("holiday_detected")
        if is_weekend:
            signals_used.append("weekend_detected")
        if occupancy_signal:
            signals_used.append(f"occupancy_{occupancy_signal}")
        if shortage_count:
            signals_used.append(f"shortage_count:{shortage_count}")
        if weather_signal:
            signals_used.append(f"weather_{weather_signal.get('condition', 'unknown')}")

        llm_result = await self._ask_llm(
            target_date=target_date,
            current_time_str=current_time_str,
            is_weekend=is_weekend,
            is_holiday=is_holiday,
            holiday_name=holiday_name,
            occupancy_signal=occupancy_signal,
            shortage_count=shortage_count,
            weather_signal=weather_signal,
            recent_runs_summary=recent_runs_summary,
        )

        label             = str((llm_result or {}).get("label") or "").strip()
        service_window    = str((llm_result or {}).get("service_window") or "").strip()
        operational_focus = str((llm_result or {}).get("operational_focus") or "").strip()

        if not label or not operational_focus or not re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}$", service_window):
            fallback = self._fallback(target_date, is_weekend=is_weekend, is_holiday=is_holiday,
                                       holiday_name=holiday_name, shortage_count=shortage_count,
                                       current_time_str=current_time_str)
            fallback["signals_used"] = signals_used
            return fallback

        confidence = (llm_result or {}).get("confidence")
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"

        return {
            "profile": {
                "id": "live-composed",
                "label": label,
                "description": operational_focus,
                "service_window": service_window,
                "operational_focus": operational_focus,
                "cuisine": None,
            },
            "reason": str((llm_result or {}).get("reason") or "").strip() or operational_focus,
            "confidence": confidence,
            "signals_used": signals_used,
        }

    async def _get_market_context(self, org_id: int) -> dict:
        if not self.swiggy_client.is_available():
            return {}
        org = self.db.query(Organization).filter(Organization.id == org_id).first()
        cuisine = (org.settings or {}).get("cuisine_type", "restaurant") if org else "restaurant"
        result = await MarketIntelService(self.swiggy_client).run({"org_id": org_id, "cuisine": cuisine})
        return result.get("market_intel_output") or {}

    async def _shortage_count(self) -> int:
        try:
            shortage_data = await InventoryService(db=self.db, llm=None).compute_shortage_data()
            return len(shortage_data.get("actionable_shortages") or [])
        except Exception:
            return 0

    async def _recent_runs_summary(self, org_id: int) -> list[dict]:
        recent_runs = RunService(self.db).list_runs(org_id, limit=3)
        return [
            {"scenario": r.scenario, "critic_verdict": r.critic_verdict, "critic_score": r.critic_score}
            for r in recent_runs
        ]

    async def _get_weather_signal(self, target_date: str) -> Optional[dict]:
        try:
            parsed = datetime.strptime(target_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            parsed = date.today()
        return await WeatherService().get_forecast(
            lat=DEFAULT_RESTAURANT_LAT, lng=DEFAULT_RESTAURANT_LNG, target_date=parsed,
        )

    async def _ask_llm(
        self,
        target_date: str,
        current_time_str: str,
        is_weekend: bool,
        is_holiday: bool,
        holiday_name: Optional[str],
        occupancy_signal: Optional[str],
        shortage_count: int,
        recent_runs_summary: list[dict],
        weather_signal: Optional[dict] = None,
    ) -> dict:
        day_type = "holiday" if is_holiday else ("weekend" if is_weekend else "weekday")
        holiday_suffix = f" ({holiday_name})" if holiday_name else ""
        weather_line = f"\nWeather: {weather_signal['signal']}" if weather_signal else ""

        prompt = f"""
## Right now
Date: {target_date} -- a {day_type}{holiday_suffix}
Current local time: {current_time_str}{weather_line}

## Market context
Area Dineout occupancy signal: {occupancy_signal or "unavailable"}

## Inventory context
Actionable shortage ingredients right now: {shortage_count}

## Recent planning runs (most recent first)
{json.dumps(recent_runs_summary) if recent_runs_summary else "No prior runs."}

## Task
Write a fresh, accurate operational profile for the service that's actually
relevant right now, given the current time -- do not force this into any
fixed named category. If it's before ~11:00, both lunch and dinner service
may be relevant; between ~11:00-16:00, focus on lunch/afternoon service;
after ~16:00, focus on the evening/dinner service ahead.

CRITICAL: only describe the date as a "weekend" or "holiday" if the date
context above actually says so. Never use those words otherwise -- a
weekday plan that also has ingredient shortages is a weekday plan with
shortages, not a weekend.

Respond with a JSON object containing:
- "label": a short 2-4 word name for this specific service (e.g. "Wednesday Dinner Service", "Rainy Weekday Lunch")
- "service_window": start-end time in 24h HH:MM-HH:MM format, sensible for the current time of day
- "operational_focus": one sentence describing what the kitchen/floor should prioritize, grounded only in the real signals above
- "reason": 1-2 sentences explaining the pick, referencing the specific signals above
- "confidence": "high", "medium", or "low"
"""
        return await self.llm.complete_json(
            prompt=prompt,
            system_prompt=(
                "You are CareOps AI's live-signal scenario composer. Write an "
                "operational profile grounded strictly in the real signals given -- "
                "never invent a day type or condition that isn't stated."
            ),
        )

    def _fallback(
        self,
        target_date: str,
        is_weekend: Optional[bool] = None,
        is_holiday: bool = False,
        holiday_name: Optional[str] = None,
        shortage_count: int = 0,
        current_time_str: Optional[str] = None,
    ) -> dict:
        """Deterministic fallback -- composed directly from real signals, so it
        can never produce a mismatched label (no fixed preset names involved
        at all, unlike ScenarioRecommender's fallback)."""
        calc_weekend, calc_is_holiday, calc_holiday_name = get_date_context(target_date)
        is_weekend = calc_weekend if is_weekend is None else is_weekend
        is_holiday = is_holiday or calc_is_holiday
        holiday_name = holiday_name or calc_holiday_name

        try:
            day_label = datetime.strptime(target_date, "%Y-%m-%d").strftime("%A")
        except (ValueError, TypeError):
            day_label = date.today().strftime("%A")

        if current_time_str is None:
            current_time_str = datetime.now(_RESTAURANT_TZ).strftime("%H:%M")
        hour = int(current_time_str.split(":")[0])

        if hour < 11:
            window, window_label = "11:00-22:00", "Full Day"
        elif hour < 16:
            window, window_label = "12:00-15:00", "Lunch Service"
        else:
            window, window_label = "18:00-22:00", "Dinner Service"

        if is_holiday:
            label = f"{holiday_name or 'Holiday'} Service"
            focus = f"{holiday_name or 'A public holiday'} today -- expect a significant demand surge."
            reason = focus
        else:
            label = f"{day_label} {window_label}"
            focus_parts = [f"Standard {day_label.lower()} {window_label.lower()}"]
            if shortage_count:
                focus_parts.append(f"{shortage_count} ingredient{'s' if shortage_count != 1 else ''} running low")
            focus = " -- ".join(focus_parts) + "."
            reason = focus

        return {
            "profile": {
                "id": "live-composed",
                "label": label,
                "description": focus,
                "service_window": window,
                "operational_focus": focus,
                "cuisine": None,
            },
            "reason": reason,
            "confidence": "low",
            "signals_used": ["fallback_signal_based"],
        }

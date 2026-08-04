"""ScenarioRecommender — P6-MI10.

Proactively suggests which planning scenario preset (friday_rush / weekday_lunch /
holiday_spike / low_stock_weekend) an owner should run next, using signals already
available elsewhere in CareOps AI: recent run history, live Swiggy market intel,
calendar context (weekend/holiday), and current inventory shortage pressure.

One LLM call ties these signals together into a scenario + short reason + confidence.
Never raises — falls back to a deterministic rule-based pick on any failure (LLM
down, Swiggy unavailable, DB error) so the dashboard suggestion chip always has
something to render.
"""

import json
from datetime import date, datetime
from typing import Optional

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

_VALID_SCENARIOS = {"friday_rush", "weekday_lunch", "holiday_spike", "low_stock_weekend"}
_SHORTAGE_FALLBACK_THRESHOLD = 3


class ScenarioRecommender:
    """Suggests a planning scenario preset before the owner picks one manually.

    Instantiate once per request. recommend() never raises — any internal
    failure degrades to a deterministic rule-based recommendation instead.
    """

    def __init__(self, db: Session, swiggy_client: SwiggyMCPClient, llm: BaseLLMProvider) -> None:
        self.db = db
        self.swiggy_client = swiggy_client
        self.llm = llm

    # ── public ───────────────────────────────────────────────────────────────

    async def recommend(self, org_id: int, target_date: str) -> dict:
        """Return {recommended_scenario, reason, confidence, signals_used}."""
        try:
            return await self._recommend(org_id, target_date)
        except Exception as exc:
            log.warning("scenario_recommender_error", error=str(exc))
            return self._fallback(target_date)

    # ── internal ─────────────────────────────────────────────────────────────

    async def _recommend(self, org_id: int, target_date: str) -> dict:
        recent_runs = RunService(self.db).list_runs(org_id, limit=3)
        recent_runs_summary = [
            {
                "scenario": r.scenario,
                "critic_verdict": r.critic_verdict,
                "critic_score": r.critic_score,
            }
            for r in recent_runs
        ]

        market_context = await self._get_market_context(org_id)
        occupancy_signal = market_context.get("area_occupancy")
        is_weekend, is_holiday, holiday_name = self._date_context(target_date)
        shortage_count = await self._shortage_count()
        weather_signal = await self._get_weather_signal(target_date)

        approved_count = sum(1 for r in recent_runs if r.critic_verdict == "approved")
        signals_used = [f"recent_approved_runs: {approved_count}"]
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
            is_weekend=is_weekend,
            is_holiday=is_holiday,
            holiday_name=holiday_name,
            occupancy_signal=occupancy_signal,
            shortage_count=shortage_count,
            weather_signal=weather_signal,
            recent_runs_summary=recent_runs_summary,
        )

        scenario = llm_result.get("recommended_scenario") if isinstance(llm_result, dict) else None
        if scenario not in _VALID_SCENARIOS:
            fallback = self._fallback(
                target_date, shortage_count=shortage_count,
                is_holiday=is_holiday, holiday_name=holiday_name, is_weekend=is_weekend,
            )
            fallback["signals_used"] = signals_used
            return fallback

        confidence = llm_result.get("confidence")
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"

        return {
            "recommended_scenario": scenario,
            "reason": str(llm_result.get("reason") or "").strip() or "Based on current operational signals.",
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

    def _date_context(self, target_date: str) -> tuple[bool, bool, Optional[str]]:
        return get_date_context(target_date)

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
        is_weekend: bool,
        is_holiday: bool,
        holiday_name: Optional[str],
        occupancy_signal: Optional[str],
        shortage_count: int,
        recent_runs_summary: list[dict],
        weather_signal: Optional[dict] = None,
    ) -> dict:
        date_desc = "holiday" if is_holiday else ("weekend" if is_weekend else "weekday")
        holiday_suffix = f" ({holiday_name})" if holiday_name else ""
        weather_line = f"\nWeather: {weather_signal['signal']}" if weather_signal else ""
        prompt = f"""
## Date context
Target date: {target_date} — {date_desc}{holiday_suffix}{weather_line}

## Market context
Area Dineout occupancy signal: {occupancy_signal or "unavailable"}

## Inventory context
Actionable shortage ingredients right now: {shortage_count}

## Recent planning runs (most recent first)
{json.dumps(recent_runs_summary) if recent_runs_summary else "No prior runs."}

## Task
Recommend exactly one planning scenario for the owner to run next:
- "friday_rush": high-demand dinner service, reservation pressure, fast-turn execution.
- "weekday_lunch": predictable midday demand, lean staffing, prep efficiency.
- "holiday_spike": exceptionally heavy demand from a holiday or festival — 40-60% surge expected.
- "low_stock_weekend": weekend service under tight ingredient constraints.

Respond with a JSON object containing:
- "recommended_scenario": one of "friday_rush", "weekday_lunch", "holiday_spike", "low_stock_weekend"
- "reason": string — 1-2 sentences explaining why, referencing the specific signals above
- "confidence": "high", "medium", or "low"
"""
        return await self.llm.complete_json(
            prompt=prompt,
            system_prompt=(
                "You are CareOps AI's scenario recommendation assistant. "
                "Pick the single best-fitting planning scenario preset from the signals given."
            ),
        )

    def _fallback(
        self,
        target_date: str,
        shortage_count: int = 0,
        is_holiday: bool = False,
        holiday_name: Optional[str] = None,
        is_weekend: Optional[bool] = None,
    ) -> dict:
        """Deterministic rule-based pick used when the LLM call fails or returns garbage."""
        calc_weekend, calc_is_holiday, calc_holiday_name = self._date_context(target_date)
        is_weekend = calc_weekend if is_weekend is None else is_weekend
        is_holiday = is_holiday or calc_is_holiday
        holiday_name = holiday_name or calc_holiday_name

        if is_holiday:
            scenario = "holiday_spike"
            reason = f"{target_date} is {holiday_name or 'a public holiday'} — expect a significant demand surge."
        elif shortage_count >= _SHORTAGE_FALLBACK_THRESHOLD:
            scenario = "low_stock_weekend"
            reason = f"{shortage_count} ingredients are running low — plan around current stock constraints."
        elif is_weekend:
            scenario = "friday_rush"
            reason = f"{target_date} falls on a weekend — expect elevated dinner demand."
        else:
            scenario = "weekday_lunch"
            reason = f"{target_date} is a regular weekday — standard lunch-service planning applies."

        return {
            "recommended_scenario": scenario,
            "reason": reason,
            "confidence": "low",
            "signals_used": ["fallback_rule_based"],
        }

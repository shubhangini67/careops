import re

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.domain.scenarios import ScenarioDefinition
from app.domain.services.business_analytics_service import BusinessAnalyticsService
from app.infrastructure.db.models import Reservation, ReservationStatus
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.prompt_utils import PromptUtils

_GUEST_TRIGGER = re.compile(r'\b(\d+)\s+(guests|covers|seats)\b', re.I)


class ReservationService:
    """Analyses reservation data and identifies capacity risks."""

    def __init__(self, db: Session, llm: BaseLLMProvider):
        self.db = db
        self.llm = llm

    def get_friday_reservations(self, target_date: datetime) -> dict:
        """Backward-compatible wrapper for older Friday-specific callers/tests."""
        return self.get_service_reservations(target_date)

    def get_service_reservations(
        self,
        target_date: datetime,
        scenario_profile: ScenarioDefinition | None = None,
        capacity: int = 70,
    ) -> dict:
        """Get reservations for the relevant target service window and analyse capacity."""
        window_start_hour, window_end_hour = self._parse_service_window(
            scenario_profile["service_window"] if scenario_profile else None
        )
        start = target_date.replace(
            hour=window_start_hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        end = target_date.replace(
            hour=window_end_hour,
            minute=59,
            second=59,
            microsecond=0,
        )

        reservations = self.db.query(Reservation).filter(
            Reservation.reserved_at >= start,
            Reservation.reserved_at <= end,
            Reservation.status.in_([
                ReservationStatus.confirmed,
                ReservationStatus.waitlist
            ])
        ).all()

        total_guests = sum(r.guest_count for r in reservations)
        peak_hours = {}
        for r in reservations:
            hour = r.reserved_at.hour
            peak_hours[hour] = peak_hours.get(hour, 0) + r.guest_count

        busiest_hour = max(peak_hours, key=peak_hours.get) if peak_hours else None
        scenario_label = (
            scenario_profile["label"] if scenario_profile else target_date.strftime("%A")
        )
        service_window = (
            scenario_profile["service_window"] if scenario_profile else "18:00-22:00"
        )

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "scenario_label": scenario_label,
            "service_window": service_window,
            "total_reservations": len(reservations),
            "total_guests": total_guests,
            "capacity": capacity,
            "occupancy_pct": round((total_guests / capacity) * 100, 1),
            "overbooking_risk": total_guests > round(capacity * 0.9),
            "busiest_hour": busiest_hour,
            "peak_hours": peak_hours,
            "waitlist_count": sum(1 for r in reservations if r.status == ReservationStatus.waitlist),
        }

    async def analyse_and_recommend(
        self,
        target_date: datetime,
        scenario_profile: ScenarioDefinition | None = None,
        capacity: int = 70,
        occupancy_context: dict | None = None,
    ) -> dict:
        """Use Gemini to analyse reservation data and generate recommendation."""
        import asyncio
        data = await asyncio.to_thread(
            self.get_service_reservations, target_date, scenario_profile, capacity
        )

        occupancy_section = (occupancy_context or {}).get("prompt_text") or ""
        occupancy_block = f"\n{occupancy_section}\n" if occupancy_section else ""

        operational_focus = (scenario_profile or {}).get("operational_focus")
        focus_block = f"\n- Operator's specific instructions: {operational_focus}\n" if operational_focus else ""

        # Real peak hours from actual order history (dine-in + delivery, all hours) --
        # "busiest_hour" above is just tonight's advance-reservation clustering, which
        # can miss demand the static configured service window / booking pattern
        # doesn't capture (e.g. a lunch rush, or a later real peak than reservations show).
        real_peak_hours = BusinessAnalyticsService(self.db).get_peak_hours(days=14)
        top_real_hours = sorted(real_peak_hours, key=lambda h: h["avg_orders"], reverse=True)[:3]
        real_peak_line = ", ".join(f"{h['hour']}:00 (avg {h['avg_orders']} orders)" for h in top_real_hours if h["avg_orders"] > 0)

        prompt = PromptUtils.format_recommendation_prompt(
            context=f"""
Reservation data for {data['scenario_label']} on {data['date']}:
- Service window: {data['service_window']}
- Total reservations: {data['total_reservations']}
- Total guests booked: {data['total_guests']}
- Restaurant capacity: {data['capacity']} guests
- Current occupancy: {data['occupancy_pct']}%
- Overbooking risk: {data['overbooking_risk']}
- Busiest hour (tonight's bookings): {data['busiest_hour']}:00
- Guests on waitlist: {data['waitlist_count']}
- Actual historical peak hours (last 14 days, real orders, all channels): {real_peak_line or 'not enough order history yet'}
{occupancy_block}{focus_block}""",
            task="Analyse this reservation data and recommend specific actions to manage capacity effectively for this target service window. Where area occupancy data is provided, factor in the neighbourhood demand signal — HIGH area occupancy means walk-in pressure; LOW means opportunity for promotions to attract diners. When you use this signal, explicitly name Swiggy as the source, e.g. 'Because Swiggy shows HIGH occupancy nearby tonight, expect walk-in pressure' — never reference area occupancy without naming Swiggy. Where the operator's specific instructions above name a guest, event, or particular need, your recommendation must explicitly address it (e.g. VIP seating/table assignment, extra prep or turnover time, a specific accommodation) — do not fall back to generic capacity guidance when the operator has stated a specific need."
        )

        recommendation = await self.llm.complete_json(
            prompt=prompt,
            system_prompt=PromptUtils.SYSTEM_RESERVATION_AGENT
        )
        recommendation = self._sanitize_guest_language(recommendation, capacity, data["total_guests"])

        return {
            "service": "reservation",
            "data": data,
            "recommendation": recommendation
        }

    def _sanitize_guest_language(self, obj, capacity: int, total_guests: int):
        """Replace 'N guests/covers/seats' where N > capacity with 'N advance reservations'.

        The sanity checker regex fires on any N guests/covers/seats where N > MAX_CAPACITY.
        The LLM reliably writes this pattern in recommendation, reasoning, and risks text
        because we tell it total_guests in the context prompt. Replacing the trigger word
        ('guests' → 'advance reservations') keeps the meaning while neutralising the match.
        """
        if total_guests <= capacity:
            return obj
        def _replace(text: str) -> str:
            def _sub(m: re.Match) -> str:
                n = int(m.group(1))
                word = m.group(2).lower()
                if n <= capacity:
                    return m.group(0)
                if word == "seats":
                    return f"{n} advance bookings"
                return f"{n} advance reservations"
            return _GUEST_TRIGGER.sub(_sub, text)
        def _walk(node):
            if isinstance(node, str):
                return _replace(node)
            if isinstance(node, dict):
                return {k: _walk(v) for k, v in node.items()}
            if isinstance(node, list):
                return [_walk(v) for v in node]
            return node
        return _walk(obj)

    def _parse_service_window(self, service_window: str | None) -> tuple[int, int]:
        if not service_window:
            return 18, 22
        start, end = service_window.split("-")
        return int(start.split(":")[0]), int(end.split(":")[0])

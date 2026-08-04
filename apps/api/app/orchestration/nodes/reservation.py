"""
Reservation Agent node.

Wraps ReservationService — analyses table capacity and booking pressure
for the target Friday, then writes to `reservation_output`.
"""

from datetime import datetime, timedelta
from typing import Callable

from app.orchestration.state import OrchestratorState
from app.domain.services.reservation_service import ReservationService
from app.infrastructure.llm.base import BaseLLMProvider


def _parse_target_date(date_str: str | None) -> datetime:
    """Parse ISO date string or fall back to the next Friday."""
    if date_str:
        return datetime.fromisoformat(date_str)

    # Default: roll forward to the next Friday
    today = datetime.utcnow()
    days_ahead = (4 - today.weekday()) % 7 or 7  # weekday 4 = Friday
    return (today + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)


async def reservation_node(
    state: OrchestratorState,
    db_factory: Callable,
    llm: BaseLLMProvider,
) -> OrchestratorState:
    """
    Analyses reservations and capacity risk for the target date.
    Writes to state['reservation_output'].

    Uses db_factory (not a shared Session) so the sync DB query inside
    ReservationService.analyse_and_recommend() can run in asyncio.to_thread()
    without competing with other parallel fan-out nodes.
    """
    if state.get("error"):
        return state

    llm = (state.get("llm_registry") or {}).get("fast") or llm

    session = db_factory()
    try:
        target_date = _parse_target_date(state.get("target_date"))
        service = ReservationService(db=session, llm=llm)
        result = await service.analyse_and_recommend(
            target_date=target_date,
            scenario_profile=state.get("scenario_profile"),
            capacity=state.get("org_capacity") or 70,
            occupancy_context=state.get("swiggy_occupancy_context"),
        )
        data = result.get("data") or {}
        return {
            **state,
            "reservation_output": result,
            "reservation_assumptions": {
                "assumed_peak_occupancy_pct": data.get("occupancy_pct"),
                "assumed_waitlist_active": (data.get("waitlist_count") or 0) > 0,
            },
        }

    except Exception as exc:
        return {
            **state,
            "reservation_output": {
                "service": "reservation",
                "error": str(exc),
                "data": None,
                "recommendation": None,
            },
            "reservation_assumptions": None,
        }
    finally:
        session.close()

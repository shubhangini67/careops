"""Demand Forecast Agent node."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.services.forecast_service import ForecastService
from app.infrastructure.llm.base import BaseLLMProvider
from app.orchestration.state import OrchestratorState


def _parse_target_date(date_str: str | None) -> datetime | None:
    if date_str:
        return datetime.fromisoformat(date_str)
    return None


async def demand_forecast_node(
    state: OrchestratorState,
    db: Session,
    llm: BaseLLMProvider,
) -> OrchestratorState:
    """Predict demand and peak windows for the selected planning scenario."""
    if state.get("error"):
        return state

    llm = (state.get("llm_registry") or {}).get("fast") or llm

    if state.get("debug") and state.get("execution_trace") is not None:
        state["execution_trace"].append("demand_forecast")

    try:
        scenario_profile = state.get("scenario_profile") or {}

        if state.get("simulation_mode", False):
            target_date = state.get("target_date") or "next planning window"
            simulated_result = {
                "service": "forecast",
                "data": {
                    "predicted_covers": 180,
                    "peak_window": scenario_profile.get("service_window", "18:00-22:00"),
                    "confidence": 0.87,
                    "service_day_label": scenario_profile.get("label", "Friday Rush"),
                    "service_window": scenario_profile.get("service_window", "18:00-22:00"),
                },
                "recommendation": {
                    "expected_demand": "High",
                    "staffing_level": "Increase staffing by 20%",
                    "prep_strategy": "Pre-prep high-demand menu items",
                },
                "target_date": target_date,
            }
            return {**state, "forecast_output": simulated_result}

        target_date = _parse_target_date(state.get("target_date"))

        # Live-intelligence signals (P6-A21/A22/A23) — weather + holiday,
        # industry trends, regulatory alerts. None is Swiggy MCP, so no
        # consent/compliance gating applies. All independently fail open: any
        # one being None just means no adjustment/context from it, the
        # forecast still runs on Prophet's raw output. Only weather actually
        # shifts the predicted number (_apply_signal_adjustments) --
        # trends/compliance are narrative context for the LLM recommendation
        # only. Fetched by live_signals_node, which runs before this node
        # (not fetched here anymore) -- read back from state rather than
        # fetching. market_intel_node also reads them back from state rather
        # than re-fetching (P6-A24).
        weather_signal            = state.get("weather_signal")
        trends_signal             = state.get("trends_signal")
        compliance_alerts_signal  = state.get("compliance_alerts_signal")
        holiday_context           = state.get("holiday_context") or {}
        is_holiday                = holiday_context.get("is_holiday", False)
        holiday_name              = holiday_context.get("holiday_name")

        service = ForecastService(db=db, llm=llm)
        result = await service.analyse_and_recommend(
            target_date=target_date,
            org_capacity=state.get("org_capacity"),
            weather_signal=weather_signal,
            is_holiday=is_holiday,
            holiday_name=holiday_name,
            trends_signal=trends_signal,
            compliance_alerts_signal=compliance_alerts_signal,
        )
        result.setdefault("data", {})
        result["data"]["service_window"] = scenario_profile.get("service_window", "18:00-22:00")
        result["data"]["scenario_label"] = scenario_profile.get("label", state.get("scenario"))
        # weather_signal/trends_signal/compliance_alerts_signal are already in
        # state (written by live_signals_node) -- **state carries them through
        # unchanged, nothing to re-set here.
        return {
            **state,
            "forecast_output": result,
        }

    except Exception as exc:
        return {
            **state,
            "forecast_output": {
                "service": "forecast",
                "error": str(exc),
                "data": None,
                "recommendation": None,
            },
        }

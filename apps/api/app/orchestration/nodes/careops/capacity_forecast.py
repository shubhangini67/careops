"""Capacity Forecast Agent — 24–48h OPD/admission workload projection."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.infrastructure.db import models as db
from app.infrastructure.healthcare.mcp_tools import HealthcareMCPTools
from app.orchestration.state import OrchestratorState


async def capacity_forecast_node(state: OrchestratorState, db_session: Session) -> OrchestratorState:
    if state.get("simulation_mode"):
        return {
            **state,
            "forecast_output": {
                "data": {
                    "forecast_24h": 95,
                    "forecast_48h": 110,
                    "capacity_snapshot": {"facility_occupancy_pct": 82.0},
                    "generated_at": datetime.utcnow().isoformat(),
                },
                "recommendation": "Simulation: moderate admission surge expected over the next 24–48 hours.",
            },
            "forecast_assumptions": {"horizon_hours": 48, "method": "simulation"},
        }

    org_id = state.get("org_id") or 1
    tools = HealthcareMCPTools(db_session)
    capacity = tools.get_capacity_snapshot(org_id=org_id)
    workload = tools.get_department_workload()

    appt_count = sum(w["count"] for w in workload.get("appointments_by_department", []))
    base_load = appt_count or 12
    forecast_24h = int(base_load * 1.15)
    forecast_48h = int(base_load * 1.28)

    recommendation = (
        f"Projected operational workload: {forecast_24h} visits/admissions in 24h, "
        f"{forecast_48h} in 48h. Facility occupancy {capacity.get('facility_occupancy_pct', 0)}%."
    )
    return {
        **state,
        "forecast_output": {
            "data": {
                "forecast_24h": forecast_24h,
                "forecast_48h": forecast_48h,
                "capacity_snapshot": capacity,
                "workload_window": workload,
                "generated_at": datetime.utcnow().isoformat(),
            },
            "recommendation": recommendation,
        },
        "forecast_assumptions": {"horizon_hours": 48, "method": "appointment_backlog_heuristic"},
    }

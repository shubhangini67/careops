"""FHIR Operations Agent — encounter and appointment aggregates via local MCP."""

from sqlalchemy.orm import Session

from app.infrastructure.healthcare.mcp_tools import HealthcareMCPTools
from app.orchestration.state import OrchestratorState


async def fhir_operations_node(state: OrchestratorState, db_factory) -> OrchestratorState:
    if state.get("simulation_mode"):
        return {
            **state,
            "reservation_output": {
                "data": {
                    "fhir_encounters": {"departments": [{"department": "Emergency", "active": 3}]},
                    "appointments_48h": {"appointments_by_department": [{"department": "Emergency", "count": 18}]},
                },
                "recommendation": "Simulation: monitor Emergency department encounter volume.",
            },
            "reservation_assumptions": {"source": "simulation"},
        }

    db = db_factory()
    try:
        tools = HealthcareMCPTools(db)
        fhir_summary = tools.get_fhir_encounter_summary()
        workload = tools.get_department_workload()
        high_pressure = [d for d in fhir_summary.get("departments", []) if d.get("active", 0) >= 2]
        rec = (
            "Monitor departments with active encounters: "
            + ", ".join(d["department"] for d in high_pressure)
            if high_pressure
            else "Encounter volume within expected operational range."
        )
        return {
            **state,
            "reservation_output": {
                "data": {"fhir_encounters": fhir_summary, "appointments_48h": workload},
                "recommendation": rec,
            },
            "reservation_assumptions": {"source": "synthetic_fhir_fixtures", "phi_exposed": False},
        }
    finally:
        db.close()

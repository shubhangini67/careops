"""Resource Allocation Agent — staffing and supply coordination."""

from sqlalchemy.orm import Session

from app.infrastructure.healthcare.mcp_tools import HealthcareMCPTools
from app.orchestration.state import OrchestratorState


async def resource_allocation_node(state: OrchestratorState, db_factory) -> OrchestratorState:
    if state.get("simulation_mode"):
        return {
            **state,
            "inventory_output": {
                "data": {"staffing": {"departments": []}, "supply_shortages": {"shortages": [], "count": 0}},
                "recommendation": "Simulation: review staffing for peak departments.",
            },
            "menu_output": {
                "data": {"departments": []},
                "recommendation": "Simulation: align nurse coverage with ED volume.",
            },
            "inventory_assumptions": {"shortage_count": 0},
            "menu_assumptions": {"allocation_basis": "simulation"},
        }

    db = db_factory()
    try:
        org_id = state.get("org_id") or 1
        tools = HealthcareMCPTools(db)
        staffing = tools.get_staffing_summary(org_id=org_id)
        shortages = tools.get_supply_shortages()
        shortage_names = [s["supply"] for s in shortages.get("shortages", [])]
        rec_parts = ["Review staffing by department for next 24h shift windows."]
        if shortage_names:
            rec_parts.append(f"Prioritize resupply for: {', '.join(shortage_names[:5])}.")
        return {
            **state,
            "inventory_output": {
                "data": {"staffing": staffing, "supply_shortages": shortages},
                "recommendation": " ".join(rec_parts),
            },
            "menu_output": {
                "data": staffing,
                "recommendation": "Align nurse and support staff with departments showing highest occupancy.",
            },
            "inventory_assumptions": {"shortage_count": shortages.get("count", 0)},
            "menu_assumptions": {"allocation_basis": "department_occupancy"},
        }
    finally:
        db.close()

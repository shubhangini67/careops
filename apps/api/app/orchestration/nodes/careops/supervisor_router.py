"""Supervisor/router — validates scenario and initializes hospital ops state."""

from app.domain.scenarios import get_scenario_definition, normalize_scenario
from app.orchestration.state import OrchestratorState


async def supervisor_router_node(state: OrchestratorState) -> OrchestratorState:
    custom_profile = state.get("custom_profile")
    scenario = normalize_scenario(state.get("scenario") or "ed_surge")

    if custom_profile:
        profile = {
            **custom_profile,
            "disclaimer": "Operational planning only — not diagnosis or treatment advice.",
        }
        profile.setdefault("id", scenario or "custom")
        return {
            **state,
            "scenario": profile["id"],
            "scenario_profile": profile,
            "error": None,
        }

    definition = get_scenario_definition(scenario)
    if not definition:
        return {**state, "error": f"Unknown scenario: {scenario}"}

    profile = {
        "id": definition["id"],
        "label": definition["label"],
        "description": definition["description"],
        "operational_focus": definition["operational_focus"],
        "service_window": definition["service_window"],
        "disclaimer": "Operational planning only — not diagnosis or treatment advice.",
    }
    return {
        **state,
        "scenario": scenario,
        "scenario_profile": profile,
        "error": None,
    }

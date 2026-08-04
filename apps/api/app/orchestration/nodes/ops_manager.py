"""
Ops Manager Agent node.

Responsibilities:
- Validate incoming scenario type
- Set up any missing state defaults
- Attach reusable scenario profile metadata
- (Future) decide which agents should run based on scenario config

This node runs first in every graph execution.

P6-A25: the 4 presets in SUPPORTED_SCENARIOS remain the fast path (unchanged
behavior), but a scenario id outside that set is no longer an automatic
reject -- if state["custom_profile"] is present (an ad-hoc profile derived
from natural language via ScenarioProfileService), scenario_profile is built
from that instead of get_scenario_definition(). Only an unrecognized
scenario with no custom_profile is still a hard error.
"""

from app.orchestration.state import OrchestratorState
from app.domain.scenarios import SCENARIO_DEFINITIONS, get_scenario_definition, normalize_scenario, resolve_default_target_date


SUPPORTED_SCENARIOS = set(SCENARIO_DEFINITIONS.keys())


def ops_manager_node(state: OrchestratorState) -> OrchestratorState:
    """
    Entry node — validates scenario and prepares orchestration state.
    Does not call the LLM directly; it coordinates other agents.
    """
    scenario = normalize_scenario(state.get("scenario") or "")
    custom_profile = state.get("custom_profile")

    if scenario in SUPPORTED_SCENARIOS:
        scenario_profile = dict(get_scenario_definition(scenario))
    elif custom_profile:
        # ScenarioProfileService always fills label/service_window/
        # operational_focus, so this is safe for the direct dict-key access
        # complaint_service/inventory_service/reservation_service do once
        # scenario_profile is truthy -- no .get() needed on their end.
        scenario_profile = dict(custom_profile)
        scenario_profile.setdefault("id", scenario or "custom")
    else:
        return {
            **state,
            "error": (
                f"Unknown scenario '{scenario}'. Supported: {SUPPORTED_SCENARIOS}, "
                "or provide a custom_profile."
            ),
        }

    # Stamp restaurant profile context into scenario_profile so all downstream
    # nodes can read cuisine/name without needing a separate state key lookup.
    restaurant_profile = state.get("restaurant_profile")
    if restaurant_profile:
        scenario_profile["restaurant_name"]    = restaurant_profile.get("name", "Restaurant")
        scenario_profile["restaurant_cuisine"] = restaurant_profile.get("cuisine", "")
        scenario_profile["restaurant_timezone"] = restaurant_profile.get("timezone", "Asia/Kolkata")

    return {
        **state,
        "scenario": scenario,
        "scenario_profile": scenario_profile,
        "target_date": state.get("target_date") or resolve_default_target_date(scenario),
        "error": None,
    }

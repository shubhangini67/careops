from datetime import datetime

import pytest

from app.domain.scenarios import get_scenario_definition, list_scenarios, resolve_default_target_date
from app.domain.services.reservation_service import ReservationService
from app.orchestration.graph import run_planning_scenario
from app.orchestration.nodes.ops_manager import ops_manager_node


def test_scenario_registry_lists_expected_presets():
    scenario_ids = {item["id"] for item in list_scenarios()}
    assert scenario_ids == {
        "ed_surge",
        "opd_peak",
        "icu_capacity",
        "supply_shortage",
    }


def test_default_target_resolution_varies_by_scenario():
    reference = datetime(2026, 4, 27)  # Monday

    assert resolve_default_target_date("ed_surge", now=reference) == "2026-05-01"
    assert resolve_default_target_date("opd_peak", now=reference) == "2026-04-29"
    assert resolve_default_target_date("icu_capacity", now=reference) == "2026-04-28"
    assert resolve_default_target_date("supply_shortage", now=reference) == "2026-05-03"


def test_legacy_scenario_aliases_normalize():
    assert get_scenario_definition("friday_rush")["id"] == "ed_surge"
    assert get_scenario_definition("weekday_lunch")["id"] == "opd_peak"


def test_ops_manager_attaches_scenario_profile():
    state = ops_manager_node(
        {
            "scenario": "opd_peak",
            "scenario_profile": None,
            "target_date": None,
            "requested_at": None,
            "simulation_mode": False,
            "force_critic_decision": None,
            "debug": False,
            "forecast_output": None,
            "reservation_output": None,
            "complaint_output": None,
            "menu_output": None,
            "inventory_output": None,
            "aggregated_recommendation": None,
            "critic_output": None,
            "final_response": None,
            "execution_trace": None,
            "error": None,
        }
    )

    assert state["error"] is None
    assert state["scenario"] == "opd_peak"
    assert state["scenario_profile"]["label"] == "OPD Peak Load"
    assert state["target_date"] is not None


@pytest.mark.asyncio
async def test_run_planning_scenario_supports_non_friday_presets():
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    mock_llm.drain_usage.return_value = []
    mock_llm.provider_metadata = {}
    mock_llm.last_provider_used = "groq"
    mock_llm.last_fallback_used = False
    deps = {"db": object(), "llm": mock_llm, "memory": object()}

    result = await run_planning_scenario(
        deps=deps,
        scenario="opd_peak",
        target_date="2026-04-29",
        simulation_mode=True,
        force_critic_decision="approved",
    )

    assert result["scenario"] == "opd_peak"
    assert result["target_date"] == "2026-04-29"
    assert result["status"] == "ready"


def _bare_state(**overrides) -> dict:
    state = {
        "scenario": "ed_surge",
        "scenario_profile": None,
        "custom_profile": None,
        "target_date": None,
        "requested_at": None,
        "simulation_mode": False,
        "force_critic_decision": None,
        "debug": False,
        "forecast_output": None,
        "reservation_output": None,
        "complaint_output": None,
        "menu_output": None,
        "inventory_output": None,
        "aggregated_recommendation": None,
        "critic_output": None,
        "final_response": None,
        "execution_trace": None,
        "restaurant_profile": None,
        "error": None,
    }
    state.update(overrides)
    return state


def test_ops_manager_builds_scenario_profile_from_custom_profile():
    custom_profile = {
        "id": "custom", "label": "Mass Casualty Drill", "description": "Hospital-wide drill.",
        "service_window": "08:00-20:00", "operational_focus": "Coordinate drill response teams.",
        "cuisine": None,
    }
    state = ops_manager_node(_bare_state(scenario="custom", custom_profile=custom_profile))

    assert state["error"] is None
    assert state["scenario_profile"]["label"] == "Mass Casualty Drill"
    assert state["scenario_profile"]["service_window"] == "08:00-20:00"


def test_ops_manager_rejects_unknown_scenario_without_custom_profile():
    state = ops_manager_node(_bare_state(scenario="mystery_scenario", custom_profile=None))
    assert state["error"] is not None
    assert "mystery_scenario" in state["error"]
    assert "custom_profile" in state["error"]


def test_ops_manager_presets_unaffected_by_custom_profile_support():
    state = ops_manager_node(_bare_state(
        scenario="icu_capacity",
        custom_profile={"label": "should be ignored", "service_window": "00:00-01:00", "operational_focus": "x"},
    ))
    assert state["scenario_profile"]["label"] == "ICU Capacity Watch"


@pytest.mark.asyncio
async def test_run_planning_scenario_accepts_custom_profile_end_to_end():
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    mock_llm.drain_usage.return_value = []
    mock_llm.provider_metadata = {}
    mock_llm.last_provider_used = "groq"
    mock_llm.last_fallback_used = False
    deps = {"db": object(), "llm": mock_llm, "memory": object()}

    custom_profile = {
        "id": "custom", "label": "Mass Casualty Drill", "description": "",
        "service_window": "08:00-20:00", "operational_focus": "Coordinate drill response teams.",
        "cuisine": None,
    }

    result = await run_planning_scenario(
        deps=deps,
        scenario="custom",
        target_date="2026-04-29",
        simulation_mode=True,
        force_critic_decision="approved",
        custom_profile=custom_profile,
    )

    assert result["scenario"] == "custom"
    assert result["status"] == "ready"


def test_reservation_service_uses_scenario_service_window():
    service = ReservationService(db=None, llm=None)

    lunch_window = service._parse_service_window("12:00-15:00")
    spike_window = service._parse_service_window("17:00-22:00")

    assert lunch_window == (12, 15)
    assert spike_window == (17, 22)

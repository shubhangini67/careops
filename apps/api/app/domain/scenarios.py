"""CareOps AI — hospital operational scenario presets."""

from datetime import datetime, timedelta, timezone
from typing import TypedDict


class ScenarioDefinition(TypedDict):
    id: str
    label: str
    description: str
    default_weekday: int
    service_window: str
    operational_focus: str


SCENARIO_DEFINITIONS: dict[str, ScenarioDefinition] = {
    "ed_surge": {
        "id": "ed_surge",
        "label": "Emergency Surge",
        "description": "High emergency department volume with bed pressure and staffing strain over the next 24–48 hours.",
        "default_weekday": 4,
        "service_window": "00:00-23:59",
        "operational_focus": "Triage flow, bed availability, critical supply readiness, escalation policies.",
    },
    "opd_peak": {
        "id": "opd_peak",
        "label": "OPD Peak Load",
        "description": "Outpatient clinics running above baseline with appointment backlog and wait-time risk.",
        "default_weekday": 2,
        "service_window": "08:00-18:00",
        "operational_focus": "Clinic throughput, nurse allocation, appointment smoothing.",
    },
    "icu_capacity": {
        "id": "icu_capacity",
        "label": "ICU Capacity Watch",
        "description": "Intensive care nearing occupancy thresholds requiring proactive resource planning.",
        "default_weekday": 1,
        "service_window": "00:00-23:59",
        "operational_focus": "Bed management, staffing ratios, supply continuity — no clinical treatment advice.",
    },
    "supply_shortage": {
        "id": "supply_shortage",
        "label": "Supply Shortage Response",
        "description": "Operational supplies below reorder thresholds during sustained admission volume.",
        "default_weekday": 6,
        "service_window": "08:00-20:00",
        "operational_focus": "Procurement prioritization, department redistribution, human-reviewed reorder actions.",
    },
}

# Backward-compatible aliases for legacy scenario ids in tests/migrations
SCENARIO_ALIASES = {
    "friday_rush": "ed_surge",
    "weekday_lunch": "opd_peak",
    "holiday_spike": "icu_capacity",
    "low_stock_weekend": "supply_shortage",
}


def normalize_scenario(scenario: str) -> str:
    return SCENARIO_ALIASES.get(scenario, scenario)


def get_scenario_definition(scenario: str) -> ScenarioDefinition | None:
    return SCENARIO_DEFINITIONS.get(normalize_scenario(scenario))


def list_scenarios() -> list[ScenarioDefinition]:
    return list(SCENARIO_DEFINITIONS.values())


def resolve_default_target_date(scenario: str, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    definition = get_scenario_definition(scenario) or SCENARIO_DEFINITIONS["ed_surge"]
    days_ahead = (definition["default_weekday"] - current.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 1
    target = current + timedelta(days=days_ahead)
    return target.strftime("%Y-%m-%d")

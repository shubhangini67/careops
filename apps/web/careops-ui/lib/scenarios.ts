// lib/scenarios.ts
// Hospital operational scenario presets for CareOps AI.

import { PlanningScenarioOption } from "@/types/planning";

export const SCENARIO_OPTIONS: PlanningScenarioOption[] = [
  {
    id: "ed_surge",
    label: "Emergency Surge",
    description: "High ED volume with bed pressure and staffing strain over the next 24–48 hours.",
    default_weekday: 4,
    service_window: "00:00-23:59",
    operational_focus: "Triage flow, bed availability, critical supply readiness.",
  },
  {
    id: "opd_peak",
    label: "OPD Peak Load",
    description: "Outpatient clinics above baseline with appointment backlog and wait-time risk.",
    default_weekday: 2,
    service_window: "08:00-18:00",
    operational_focus: "Clinic throughput, nurse allocation, appointment smoothing.",
  },
  {
    id: "icu_capacity",
    label: "ICU Capacity Watch",
    description: "Intensive care nearing occupancy thresholds requiring proactive resource planning.",
    default_weekday: 1,
    service_window: "00:00-23:59",
    operational_focus: "Bed management, staffing ratios, supply continuity.",
  },
  {
    id: "supply_shortage",
    label: "Supply Shortage Response",
    description: "Operational supplies below reorder thresholds during sustained admission volume.",
    default_weekday: 6,
    service_window: "08:00-20:00",
    operational_focus: "Procurement prioritization, department redistribution, human-reviewed reorders.",
  },
];

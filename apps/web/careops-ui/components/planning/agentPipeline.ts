// CareOps AI — agent pipeline copy for PlanShiftModal and PlanningIdleState.

export interface AgentCapability {
  label: string;
  capability: string;
  capabilities: string[];
  iconPath: string;
  tone: "good" | "info" | "rose" | "purple" | "amber" | "teal" | "swiggy";
  swiggy?: boolean;
  live?: boolean;
}

export const AGENT_PIPELINE: AgentCapability[] = [
  {
    label: "Capacity Forecast",
    capability: "Projects admission volume and bed pressure for the scenario.",
    capabilities: ["Admission volume forecast", "Bed utilization projection", "Weather-adjusted demand"],
    iconPath: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
    tone: "purple",
  },
  {
    label: "FHIR Operations",
    capability: "Reads encounters, appointments, and observations from FHIR data.",
    capabilities: ["Active encounters", "Appointment backlog", "Observation trends"],
    iconPath: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
    tone: "teal",
    live: true,
  },
  {
    label: "Policy RAG",
    capability: "Retrieves hospital SOPs and regulatory guidance with citations.",
    capabilities: ["Policy document search", "SOP citations", "Regulatory compliance context"],
    iconPath: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
    tone: "info",
  },
  {
    label: "Resource Allocation",
    capability: "Plans beds, staff shifts, and supply redistribution.",
    capabilities: ["Bed allocation", "Staff shift coverage", "Supply prioritization"],
    iconPath: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
    tone: "good",
  },
  {
    label: "Safety Critic",
    capability: "A second opinion on safety, feasibility, and policy alignment.",
    capabilities: ["Safety & feasibility scoring", "Evidence-based review", "Flags plans needing human review"],
    iconPath: "M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z",
    tone: "amber",
  },
  {
    label: "Approval Queue",
    capability: "Routes sensitive actions for explicit human sign-off.",
    capabilities: ["Supply reorder review", "Operations plan approval", "Audit trail"],
    iconPath: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4",
    tone: "rose",
  },
];

export const AGENT_TONE_CLASS: Record<AgentCapability["tone"], { bg: string; text: string; fill: string }> = {
  good:    { bg: "var(--color-good-soft)",    text: "var(--color-good)", fill: "#5f9b81" },
  info:    { bg: "rgba(56,189,248,0.10)",     text: "#38bdf8",           fill: "#5f8ba8" },
  rose:    { bg: "rgba(251,113,133,0.10)",    text: "#fb7185",           fill: "#b97676" },
  purple:  { bg: "rgba(139,92,246,0.10)",     text: "#8b5cf6",           fill: "#8577a8" },
  amber:   { bg: "rgba(217,119,6,0.10)",      text: "#d97706",           fill: "#b98548" },
  teal:    { bg: "rgba(20,184,166,0.10)",     text: "#14b8a6",           fill: "#4f8f88" },
  swiggy:  { bg: "rgba(252,128,25,0.10)",     text: "#fc8019",           fill: "#fc8019" },
};

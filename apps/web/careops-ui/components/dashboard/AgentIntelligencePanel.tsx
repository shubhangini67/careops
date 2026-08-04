"use client";

import { useState } from "react";
import { AGENT_META, CompactComplaintView } from "./AgentCard";
import { CardHeader, ICONS, HeaderChip } from "./AgentStatStrip";
import ForecastChart from "./ForecastChart";
import InventoryAlerts from "./InventoryAlerts";
import { MenuInsightsBody } from "./MenuInsights";
import ReservationSummary from "./ReservationSummary";
import { FridayRushResponse } from "@/types/planning";
import { toSupplyLabel } from "@/lib/careopsDisplay";

// Settings-page pattern: a nav list on the left, one detail panel on the
// right that swaps in place when a row is clicked. Every agent's body
// (ForecastChart/ReservationSummary/InventoryAlerts/MenuInsightsBody/
// CompactComplaintView) now follows one fixed section order internally --
// KPI strip, then Recommendation, then Reasoning, then the itemized
// breakdown/actions, then a Sources footer (with Swiggy attribution badge
// when that agent's result was genuinely shaped by live Swiggy data) -- so
// this file only supplies the nav chrome and the per-agent tagline/priority,
// nothing duplicated from what the body already shows.

function asObject(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

function toNum(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

type AgentKey = "forecast" | "reservation" | "complaint" | "inventory" | "menu";
type PriorityTone = "critical" | "high" | "medium" | "low";

interface RowSpec {
  agentKey: AgentKey;
  status: string;
  takeaway: string;
  priorityLabel: string;
  priorityTone: PriorityTone;
}

const PRIORITY_CLASS: Record<PriorityTone, string> = {
  critical: "bg-rose-500/10 text-rose-500 ring-1 ring-rose-400/30",
  high: "bg-rose-500/10 text-rose-500 ring-1 ring-rose-400/25",
  medium: "bg-amber-500/10 text-amber-600 dark:text-amber-300 ring-1 ring-amber-400/25",
  low: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 ring-1 ring-emerald-400/25",
};

const TAGLINE: Record<AgentKey, string> = {
  forecast: "Projecting admission volume and bed pressure for the scenario window.",
  reservation: "Appointment load, bed utilization, and throughput context.",
  complaint: "Safety incidents, recurring issues, and recommended operational fixes.",
  inventory: "Supply pressure, reorder actions, and critical shortage risk.",
  menu: "Department priorities and resource focus for the current run.",
};

// One warm-to-cool identity color per agent, used for its header icon
// badge -- literal hex (not var(--color-accent)) since CardHeader appends
// an alpha suffix directly to build its gradient.
const AGENT_COLOR: Record<AgentKey, string> = {
  forecast: "#FF5200",
  reservation: "#06B6D4",
  complaint: "#F43F5E",
  inventory: "#10B981",
  menu: "#F59E0B",
};

function priorityFromString(p: string | null | undefined): { label: string; tone: PriorityTone } {
  const v = (p ?? "").toLowerCase();
  if (v === "critical") return { label: "Critical", tone: "critical" };
  if (v === "high") return { label: "High priority", tone: "high" };
  if (v === "low") return { label: "Low priority", tone: "low" };
  return { label: "Medium priority", tone: "medium" };
}

// Same field reads as RunHistorySection.tsx's computeSwiggySignal, so the
// "insights also came from Swiggy" attribution matches between the live
// Planning view and the /data run-history view rather than diverging.
function computeSwiggySignal(agentKey: AgentKey, data: FridayRushResponse): string | undefined {
  if (agentKey === "reservation") {
    // Real key is "occupancy_signal" (OccupancyEnricher.enrich()'s raw
    // output, passed through unchanged as swiggy_occupancy_context) --
    // types/planning.ts's SwiggyOccupancyContext.signal field name is stale
    // relative to the actual payload; matching RunHistorySection.tsx's
    // already-correct read here rather than the stale type.
    const occ = data.swiggy_occupancy_context as Record<string, unknown> | null | undefined;
    const sig = occ?.occupancy_signal as string | undefined;
    return sig ? `area tonight: ${sig}` : undefined;
  }
  if (agentKey === "inventory") {
    const proc = data.swiggy_procurement_options;
    const opts = proc?.procurement_options;
    return opts && opts.length > 0 ? `${opts.length} Instamart prices live` : undefined;
  }
  if (agentKey === "menu") {
    const comp = data.swiggy_competitor_context as Record<string, unknown> | null | undefined;
    const alerts = comp?.alerts as unknown[] | undefined;
    const avgMap = comp?.area_avg as Record<string, number> | undefined;
    const dishCount = avgMap ? Object.keys(avgMap).length : 0;
    if (alerts && alerts.length > 0) return `${alerts.length} pricing alert${alerts.length !== 1 ? "s" : ""} · ${dishCount} dishes`;
    if (dishCount > 0) return `${dishCount} competitor dishes tracked`;
    return undefined;
  }
  return undefined;
}

// ---- Row summaries (left nav) ----

function buildRowSpec(agentKey: AgentKey, data: FridayRushResponse): RowSpec {
  const forecast = asObject(data.recommendations.forecast);
  const forecastData = asObject(forecast?.data) ?? forecast;

  if (agentKey === "forecast") {
    const forecast24 = toNum(forecastData?.forecast_24h ?? forecastData?.predicted_orders);
    const forecast48 = toNum(forecastData?.forecast_48h);
    const occupancy = toNum(asObject(forecastData?.capacity_snapshot)?.facility_occupancy_pct);
    const diffPct = forecast24 !== null && forecast48 && forecast24 > 0
      ? Math.round(((forecast48 - forecast24) / forecast24) * 100)
      : null;
    const priority = diffPct !== null && diffPct >= 15 ? { label: "High priority", tone: "high" as const }
      : occupancy !== null && occupancy >= 90 ? { label: "High priority", tone: "high" as const }
      : { label: "Medium priority", tone: "medium" as const };
    return {
      agentKey,
      status: forecast24 !== null ? `${Math.round(forecast24)} admissions in 24h` : "Forecast unavailable",
      takeaway: occupancy !== null && occupancy >= 90 ? "Bed utilization is near capacity — plan overflow protocols."
        : diffPct !== null && diffPct >= 15 ? "Admission volume is rising into the 48h window."
        : "Workload within expected operational range.",
      priorityLabel: priority.label, priorityTone: priority.tone,
    };
  }

  const rec = data.recommendations[agentKey] as Record<string, unknown> | null;
  if (!rec) return { agentKey, status: "No output", takeaway: "Agent did not return output.", priorityLabel: "Medium priority", priorityTone: "medium" };
  if (rec.error) return { agentKey, status: "Error", takeaway: String(rec.error), priorityLabel: "Medium priority", priorityTone: "medium" };
  const nested = asObject(rec.data) ?? rec;

  if (agentKey === "reservation") {
    const fhir = asObject(nested?.fhir_encounters);
    const appts = asObject(nested?.appointments_48h);
    const activeDepts = Array.isArray(fhir?.departments)
      ? (fhir.departments as Record<string, unknown>[]).filter((d) => Number(d.active) >= 2).length
      : 0;
    const apptTotal = Array.isArray(appts?.appointments_by_department)
      ? (appts.appointments_by_department as Record<string, unknown>[]).reduce((s, d) => s + Number(d.count ?? 0), 0)
      : toNum(nested?.total_reservations) ?? 0;
    const occ = toNum(nested?.occupancy_pct);
    const priority = activeDepts > 0 ? { label: "High priority", tone: "high" as const }
      : occ !== null && occ > 85 ? { label: "High priority", tone: "high" as const }
      : { label: "Medium priority", tone: "medium" as const };
    return {
      agentKey,
      status: `${apptTotal} appointments · ${activeDepts} high-load dept${activeDepts !== 1 ? "s" : ""}`,
      takeaway: activeDepts > 0 ? "Active encounters elevated — monitor ED throughput."
        : occ !== null && occ > 85 ? "Bed utilization running hot."
        : "Encounter volume within expected range.",
      priorityLabel: priority.label, priorityTone: priority.tone,
    };
  }

  if (agentKey === "complaint") {
    const citations = Array.isArray(rec?.citations) ? rec.citations as Record<string, unknown>[] : [];
    const policyHits = Array.isArray(nested?.results) ? nested.results as unknown[] : [];
    const count = citations.length || policyHits.length;
    const priority = count === 0 ? { label: "Medium priority", tone: "medium" as const } : { label: "High priority", tone: "high" as const };
    return {
      agentKey,
      status: `${count} policy citation${count !== 1 ? "s" : ""}`,
      takeaway: count > 0 ? "Review cited SOPs before executing the plan." : "No policy excerpts retrieved for this scenario.",
      priorityLabel: priority.label, priorityTone: priority.tone,
    };
  }

  if (agentKey === "inventory") {
    const shortages = asObject(nested?.supply_shortages)?.shortages;
    const shortageList = Array.isArray(shortages) ? shortages as Record<string, unknown>[] : (
      Array.isArray(nested?.shortage_alerts) ? nested.shortage_alerts as Record<string, unknown>[] : []
    );
    const critical = shortageList[0];
    const criticalName = critical ? toSupplyLabel(String(critical.supply ?? critical.ingredient ?? "")) : null;
    const staffing = asObject(nested?.staffing);
    const deptCount = Array.isArray(staffing?.departments) ? staffing.departments.length : 0;
    const priority = critical ? { label: "Critical", tone: "critical" as const } : shortageList.length > 0 ? { label: "High priority", tone: "high" as const } : { label: "Low priority", tone: "low" as const };
    return {
      agentKey,
      status: criticalName ? `${criticalName} critically low` : shortageList.length > 0 ? `${shortageList.length} supply alert${shortageList.length !== 1 ? "s" : ""}` : "Supply levels healthy",
      takeaway: criticalName ? `${criticalName} needs reorder before next shift.`
        : deptCount > 0 ? `Staffing reviewed across ${deptCount} departments.`
        : "No restock action needed.",
      priorityLabel: priority.label, priorityTone: priority.tone,
    };
  }

  const staffingDepts = Array.isArray(nested?.departments) ? nested.departments.length : 0;
  const recText = typeof rec.recommendation === "string" ? rec.recommendation : null;
  const priority = priorityFromString(typeof rec.priority === "string" ? rec.priority : "medium");
  return {
    agentKey,
    status: staffingDepts > 0 ? `${staffingDepts} departments staffed` : "Resource plan ready",
    takeaway: recText ? recText.slice(0, 90) + (recText.length > 90 ? "…" : "") : "Align nurse and support coverage with peak departments.",
    priorityLabel: priority.label, priorityTone: priority.tone,
  };
}

function buildRows(data: FridayRushResponse): RowSpec[] {
  const order: AgentKey[] = ["forecast", "reservation", "complaint", "inventory", "menu"];
  return order.map((k) => buildRowSpec(k, data));
}

// Header context chips -- Service window (real, from each agent's own data)
// and the Swiggy attribution (same computeSwiggySignal used in the body's
// footer/card sources) surfaced right in the header, matching the
// reference layout's top-right chip row.
function buildHeaderChips(agentKey: AgentKey, data: FridayRushResponse): HeaderChip[] {
  const chips: HeaderChip[] = [];

  const rec = agentKey === "forecast" ? asObject(data.recommendations.forecast) : asObject(data.recommendations[agentKey]);
  const nested = asObject(rec?.data) ?? rec;
  const serviceWindow = typeof nested?.service_window === "string" ? nested.service_window : undefined;
  if (serviceWindow) {
    chips.push({ icon: <ICONS.clock className="h-4 w-4" strokeWidth={1.8} />, label: "Planning window", value: serviceWindow });
  }

  if (agentKey === "complaint") {
    const count = Array.isArray(rec?.citations) ? rec.citations.length : 0;
    if (count > 0) {
      chips.push({ icon: <ICONS.mapPin className="h-4 w-4" strokeWidth={1.8} />, label: "Policy index", value: `${count} citation${count !== 1 ? "s" : ""}` });
    }
  }

  if (agentKey === "forecast") {
    const occ = asObject(nested?.capacity_snapshot)?.facility_occupancy_pct;
    if (occ !== undefined) {
      chips.push({ icon: <ICONS.shieldCheck className="h-4 w-4" strokeWidth={1.8} />, label: "Bed utilization", value: `${Math.round(Number(occ))}%` });
    }
  }

  return chips;
}

function DetailBody({ agentKey, data }: { agentKey: AgentKey; data: FridayRushResponse }) {
  if (agentKey === "forecast") {
    return <ForecastChart forecast={data.recommendations.forecast} scenario={data.scenario} />;
  }
  const rec = data.recommendations[agentKey] as Record<string, unknown> | null;
  if (!rec) return <p className="text-sm text-[var(--color-text-ghost)] italic">Agent did not return output.</p>;
  if (rec.error) return <p className="text-sm text-rose-400">! {String(rec.error)}</p>;

  // Full (non-compact) detail on purpose -- this panel's whole point is
  // showing the real, complete backend output (every risk, every menu
  // section list, every shortage/overstock alert with its full stock/
  // threshold/spoilage detail), not a truncated "+N more" preview with
  // nothing behind it to expand into. A previous pass switched these two to
  // compact mode to keep card heights even with the sparser agents, but
  // that hid real data with no way to actually see it -- min-height +
  // vertical centering on the shorter cards is the right fix for that, not
  // truncating the richer ones.
  if (agentKey === "inventory") return <InventoryAlerts inventory={rec} />;
  if (agentKey === "menu") return <MenuInsightsBody data={rec} />;
  if (agentKey === "reservation") return <ReservationSummary data={rec as Record<string, unknown>} />;
  return <CompactComplaintView data={rec} />;
}

export default function AgentIntelligencePanel({ data }: { data: FridayRushResponse }) {
  const rows = buildRows(data);
  const [selected, setSelected] = useState<AgentKey>(rows[0]?.agentKey ?? "forecast");
  const selectedMeta = AGENT_META[selected];

  return (
    <div>
      <div className="flex items-center gap-1.5">
        <svg className="h-3.5 w-3.5 shrink-0 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v18M3 9h18M3 15h18" />
        </svg>
        <p className="text-[10.5px] font-bold uppercase tracking-[0.18em] text-[var(--color-accent)]">Agent intelligence</p>
      </div>
      <p className="mt-1 text-[19px] font-bold text-[var(--color-text-primary)]">Detailed analysis from each specialist agent</p>

      <div className="@container mt-3">
        {/* Tab row -- one horizontal strip of all 5 agents; only the
            selected one's full detail renders below. Replaces the old
            sidebar + panel split, which wasted width on a nav list and
            forced awkward height-matching between a short list and a tall,
            variable-height detail panel. */}
        <div className="flex flex-wrap gap-1.5 rounded-2xl bg-[var(--color-surface-sunken)] p-1.5">
          {rows.map((row) => {
            const meta = AGENT_META[row.agentKey];
            const isSelected = row.agentKey === selected;
            return (
              <button
                key={row.agentKey}
                onClick={() => setSelected(row.agentKey)}
                className={`flex flex-1 min-w-[150px] items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors ${
                  isSelected ? "card shadow-sm" : "hover:bg-[var(--color-surface-raised)]/60"
                }`}
              >
                <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${meta.iconColor}`} style={{ background: isSelected ? "var(--color-surface-raised)" : "transparent" }}>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={meta.iconPath} />
                  </svg>
                </span>
                <span className="min-w-0 flex-1">
                  <span className={`block truncate text-[12.5px] font-semibold ${isSelected ? "text-[var(--color-text-primary)]" : "text-[var(--color-text-soft)]"}`}>{meta.label}</span>
                </span>
                <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[8.5px] font-bold ${PRIORITY_CLASS[row.priorityTone]}`}>{row.priorityLabel}</span>
              </button>
            );
          })}
        </div>

        {/* Detail panel -- full width now that there's no sidebar taking
            space, which also gives the redesigned recommendation/stats
            two-column layout more room to breathe. */}
        <div className="card card-lift mt-3 flex min-w-0 flex-col rounded-2xl p-5 sm:p-6">
          <CardHeader
            icon={
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d={selectedMeta.iconPath} />
              </svg>
            }
            color={AGENT_COLOR[selected]}
            title={selectedMeta.label}
            subtitle={TAGLINE[selected]}
            chips={buildHeaderChips(selected, data)}
          />

          <div className="mt-4">
            <DetailBody agentKey={selected} data={data} />
          </div>
        </div>
      </div>
    </div>
  );
}

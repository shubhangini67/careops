"use client";

import { FridayRushResponse } from "@/types/planning";
import { toSupplyLabel } from "@/lib/careopsDisplay";

function asObject(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

function toNum(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

interface DriverCard {
  key: string;
  label: string;
  icon: string;
  status: string;
  takeaway: string;
  tone?: "rose" | "amber" | "emerald";
}

function buildDrivers(data: FridayRushResponse): DriverCard[] {
  const drivers: DriverCard[] = [];

  const forecast = asObject(data.recommendations.forecast);
  const forecastData = asObject(forecast?.data) ?? forecast;
  const forecast24 = toNum(forecastData?.forecast_24h ?? forecastData?.predicted_orders);
  const forecast48 = toNum(forecastData?.forecast_48h);
  const occupancy = toNum(asObject(forecastData?.capacity_snapshot)?.facility_occupancy_pct);
  if (forecast24 !== null) {
    const diffPct = forecast48 && forecast24 > 0 ? Math.round(((forecast48 - forecast24) / forecast24) * 100) : null;
    drivers.push({
      key: "capacity", label: "Capacity Forecast", icon: "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6",
      status: `${Math.round(forecast24)} admissions in 24h${diffPct !== null ? ` (${diffPct >= 0 ? "+" : ""}${diffPct}% into 48h)` : ""}`,
      takeaway: occupancy !== null && occupancy >= 90 ? "Bed utilization is near capacity — activate overflow protocols."
        : diffPct !== null && diffPct >= 15 ? "Admission volume is rising — pre-stage staffing and supplies."
        : "Workload projection is within normal operational range.",
      tone: occupancy !== null && occupancy >= 90 ? "amber" : undefined,
    });
  }

  const reservation = asObject(data.recommendations.reservation);
  const reservationData = asObject(reservation?.data) ?? reservation;
  const fhir = asObject(reservationData?.fhir_encounters);
  const activeDepts = Array.isArray(fhir?.departments)
    ? (fhir.departments as Record<string, unknown>[]).filter((d) => Number(d.active) >= 2)
    : [];
  if (activeDepts.length > 0 || reservationData) {
    drivers.push({
      key: "fhir", label: "FHIR Operations", icon: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
      status: activeDepts.length > 0
        ? `${activeDepts.length} dept${activeDepts.length !== 1 ? "s" : ""} with active encounters`
        : "Encounter volume within expected range",
      takeaway: activeDepts.length > 0
        ? `Monitor ${activeDepts.slice(0, 2).map((d) => String(d.department ?? "department")).join(", ")} closely.`
        : "No unusual encounter pressure from FHIR aggregates.",
    });
  }

  const inventory = asObject(data.recommendations.inventory);
  const inventoryData = asObject(inventory?.data) ?? inventory;
  const supplyShortages = asObject(inventoryData?.supply_shortages)?.shortages;
  const shortageList = Array.isArray(supplyShortages) ? supplyShortages as Record<string, unknown>[]
    : Array.isArray(inventoryData?.shortage_alerts) ? inventoryData.shortage_alerts as Record<string, unknown>[] : [];
  const firstShortage = shortageList[0];
  const supplyName = firstShortage ? toSupplyLabel(String(firstShortage.supply ?? firstShortage.ingredient ?? "")) : null;
  drivers.push({
    key: "supply", label: "Supply & Staffing", icon: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
    status: supplyName ? `${supplyName} below reorder threshold` : "Supply levels healthy",
    takeaway: supplyName ? "Reorder before next shift handoff to avoid care delays." : "No critical supply action needed.",
    tone: supplyName ? "rose" : undefined,
  });

  const complaint = asObject(data.recommendations.complaint);
  const citations = Array.isArray(complaint?.citations) ? complaint.citations.length : 0;
  if (citations > 0 || complaint) {
    drivers.push({
      key: "policy", label: "Policy RAG", icon: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
      status: `${citations} policy citation${citations !== 1 ? "s" : ""} attached`,
      takeaway: citations > 0 ? "Plan actions must align with cited hospital SOPs." : "No policy excerpts retrieved for this run.",
    });
  }

  const menu = asObject(data.recommendations.menu);
  const menuRec = typeof menu?.recommendation === "string" ? menu.recommendation : null;
  if (menuRec) {
    drivers.push({
      key: "staffing", label: "Resource Allocation", icon: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1z",
      status: "Staffing plan generated",
      takeaway: menuRec.length > 100 ? `${menuRec.slice(0, 100)}…` : menuRec,
    });
  }

  return drivers;
}

const TONE_CLASS: Record<string, string> = {
  rose: "text-rose-500",
  amber: "text-amber-500",
  emerald: "text-emerald-500",
};

const DRIVER_COLOR: Record<string, string> = {
  capacity: "#818cf8",
  fhir: "#06B6D4",
  supply: "#C2410C",
  policy: "#F43F5E",
  staffing: "#D97706",
};

export default function SituationDrivers({ data }: { data: FridayRushResponse }) {
  const drivers = buildDrivers(data);
  if (drivers.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-1.5">
        <svg className="h-3.5 w-3.5 shrink-0 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        <p className="text-[10.5px] font-bold uppercase tracking-[0.18em] text-[var(--color-accent)]">Situation drivers</p>
      </div>
      <p className="mt-1 text-[19px] font-bold text-[var(--color-text-primary)]">Why the AI is planning this scenario this way</p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {drivers.map((d) => {
          const color = DRIVER_COLOR[d.key] ?? "#FF5200";
          return (
            <div key={d.key} className="card card-lift rounded-2xl p-4">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white shadow-sm" style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={d.icon} />
                  </svg>
                </span>
                <p className="text-[13px] font-bold text-[var(--color-text-primary)]">{d.label}</p>
              </div>
              <p className={`mt-2.5 text-[13px] font-medium ${d.tone ? TONE_CLASS[d.tone] : "text-[var(--color-text-primary)]"}`}>{d.status}</p>
              <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--color-text-faint)]">{d.takeaway}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

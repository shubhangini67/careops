// components/dashboard/ReservationSummary.tsx
"use client";

import { CardFooter, ICONS, PriorityGauge, RecommendationBlock, StatGrid } from "./AgentStatStrip";

interface ReservationData {
  data?: {
    total_reservations?: number;
    total_guests?: number;
    capacity?: number;
    occupancy_pct?: number;
    overbooking_risk?: boolean;
    busiest_hour?: number | null;
    date?: string;
    waitlist_count?: number;
  };
  // final_assembler.py's _safe_rec() flattens ReservationService's LLM
  // recommendation object (recommendation/reasoning/priority/risks) up to
  // the top level, merged with "data" -- so these are sibling keys here,
  // never a nested object under a "recommendation" key.
  recommendation?: string;
  reasoning?: string;
  priority?: string;
  risks?: string[];
  [key: string]: unknown;
}

function asNumber(value: unknown, fallback = 0) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

export default function ReservationSummary({ data, swiggySignal }: { data: ReservationData; compact?: boolean; swiggySignal?: string }) {
  const source = data as Record<string, unknown>;
  const dataObj = (source.data as Record<string, unknown> | undefined) || source;
  const recommendationText = typeof source.recommendation === "string" ? source.recommendation : null;
  const reasoning = typeof source.reasoning === "string" ? source.reasoning : null;
  const priority = typeof source.priority === "string" ? source.priority : undefined;
  const risks = Array.isArray(source.risks) ? source.risks.filter((r): r is string => typeof r === "string") : undefined;

  if (!dataObj || Object.keys(dataObj).length === 0) {
    return <p className="text-sm text-[var(--color-text-ghost)] italic">No reservation data available.</p>;
  }

  const total_reservations = asNumber(dataObj.total_reservations);
  const total_guests = asNumber(dataObj.total_guests);
  const capacity = asNumber(dataObj.capacity, 70);
  const occupancy_pct = asNumber(dataObj.occupancy_pct);
  const overbooking_risk = dataObj.overbooking_risk === true;
  const busiest_hour = dataObj.busiest_hour === null || dataObj.busiest_hour === undefined ? null : asNumber(dataObj.busiest_hour);
  const date = asString(dataObj.date);
  const waitlist_count = asNumber(dataObj.waitlist_count);

  const occupancyColor = occupancy_pct > 85 ? "#F43F5E" : occupancy_pct > 70 ? "#F59E0B" : "#10B981";
  const occupancyTone = occupancy_pct > 85 ? "text-rose-600 dark:text-rose-300"
    : occupancy_pct > 70 ? "text-amber-600 dark:text-amber-300"
    : "text-emerald-600 dark:text-emerald-300";

  return (
    <div className="@container flex flex-col gap-5">
      {/* Recommendation (left) + stat grid & priority gauge (right) side by side */}
      <div className="grid grid-cols-1 gap-4 @3xl:grid-cols-[1.3fr_1fr] @3xl:items-stretch">
        <RecommendationBlock
          recommendation={recommendationText}
          reasoning={reasoning}
          priority={priority}
          risks={risks}
        />
        <div className="flex flex-col gap-3">
          <StatGrid stats={[
            { icon: <ICONS.chartBar className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#06B6D4", value: String(total_reservations), label: "Bookings", caption: date ? `for ${date}` : undefined },
            { icon: <ICONS.trendUp className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#06B6D4", value: String(total_guests), label: "Total guests", caption: `of ${capacity} capacity` },
            {
              icon: <ICONS.gauge className="h-4 w-4" strokeWidth={1.8} />, iconColor: occupancyColor, value: `${occupancy_pct}%`, valueClass: occupancyTone,
              label: "Occupancy", caption: overbooking_risk ? "above target · risk" : occupancy_pct > 85 ? "above target" : "within target",
            },
            {
              icon: <ICONS.clock className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#8B5CF6",
              value: busiest_hour !== null && busiest_hour !== undefined ? `${String(busiest_hour).padStart(2, "0")}:00` : "--",
              label: "Peak hour", caption: waitlist_count > 0 ? `${waitlist_count} on waitlist` : "No waitlist",
            },
          ]} />
          <PriorityGauge priority={priority} />
        </div>
      </div>

      <CardFooter label="Service date" value={date || "--"} swiggySignal={swiggySignal} />
    </div>
  );
}

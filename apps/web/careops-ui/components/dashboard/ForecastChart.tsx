"use client";

import { useState, useRef, useEffect } from "react";
import {
  BarChart, Bar,
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine,
} from "recharts";
import { CardFooter, ICONS, PriorityGauge, RecommendationBlock, SectionTitle, StatGrid } from "./AgentStatStrip";

interface Props {
  forecast: Record<string, unknown> | null;
  scenario?: string | null;
}

type HourBar = { hour: string; visits: number; inWindow: boolean };

const CHART_COLOR = "#818cf8";

const SCENARIO_PROFILES: Record<string, number[]> = {
  ed_surge: [0.04, 0.08, 0.14, 0.22, 0.2, 0.16, 0.1, 0.06],
  opd_peak: [0.06, 0.12, 0.2, 0.22, 0.18, 0.12, 0.06, 0.04],
  icu_capacity: [0.05, 0.09, 0.14, 0.18, 0.2, 0.18, 0.1, 0.06],
  supply_shortage: [0.05, 0.1, 0.16, 0.2, 0.19, 0.15, 0.1, 0.05],
  default: [0.05, 0.08, 0.12, 0.18, 0.19, 0.15, 0.11, 0.07, 0.05],
};

function toNumber(value: unknown): number | undefined {
  if (value === null || value === undefined) return undefined;
  const num = Number(value);
  return Number.isFinite(num) ? num : undefined;
}

function asObject(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

function extractRecommendation(raw: Record<string, unknown>): {
  recommendation?: string;
  reasoning?: string;
  priority?: string;
  risks?: string[];
} {
  if (typeof raw.recommendation === "string") {
    return {
      recommendation: raw.recommendation,
      reasoning: typeof raw.reasoning === "string" ? raw.reasoning : undefined,
      priority: typeof raw.priority === "string" ? raw.priority : undefined,
      risks: Array.isArray(raw.risks) ? raw.risks.filter((r): r is string => typeof r === "string") : undefined,
    };
  }
  const nested = asObject(raw.recommendation);
  return {
    recommendation: nested && typeof nested.recommendation === "string" ? nested.recommendation : undefined,
    reasoning: nested && typeof nested.reasoning === "string" ? nested.reasoning : undefined,
    priority: nested && typeof nested.priority === "string" ? nested.priority : undefined,
    risks: nested && Array.isArray(nested.risks) ? nested.risks.filter((r): r is string => typeof r === "string") : undefined,
  };
}

function parseServiceWindow(serviceWindow?: string): { start: number; end: number } {
  if (!serviceWindow || !serviceWindow.includes("-")) return { start: 8, end: 20 };
  const [startText, endText] = serviceWindow.split("-");
  return { start: Number(startText.split(":")[0]), end: Number(endText.split(":")[0]) };
}

function buildHourlyBars(total: number, serviceWindow?: string, scenario?: string | null): HourBar[] {
  const { start, end } = parseServiceWindow(serviceWindow);
  const earliest = Math.max(0, start - 1);
  const latest = Math.min(23, end + 1);
  const hours: string[] = [];
  for (let h = earliest; h <= latest; h += 1) {
    hours.push(`${String(h).padStart(2, "0")}:00`);
  }
  const profile = (scenario && SCENARIO_PROFILES[scenario]) || SCENARIO_PROFILES.default;
  const weights = profile.slice(0, hours.length);
  const weightSum = weights.reduce((s, w) => s + w, 0) || 1;
  const distributed = weights.map((w) => Math.round((total * w) / weightSum));

  return hours.map((hour, i) => ({
    hour,
    visits: distributed[i] ?? 0,
    inWindow: Number(hour.split(":")[0]) >= start && Number(hour.split(":")[0]) <= end,
  }));
}

export default function ForecastChart({ forecast, scenario }: Props) {
  const [chartType, setChartType] = useState<"bar" | "line">("bar");
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(800);

  useEffect(() => {
    const el = chartContainerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => setChartWidth(entries[0].contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (!forecast) return null;

  const payload = asObject(forecast.data) ?? forecast;
  const recommendation = extractRecommendation(forecast);

  const forecast24 = toNumber(payload.forecast_24h ?? payload.predicted_orders ?? payload.predicted_covers);
  const forecast48 = toNumber(payload.forecast_48h);
  const occupancy = toNumber(
    asObject(payload.capacity_snapshot)?.facility_occupancy_pct ??
    payload.facility_occupancy_pct
  );
  const serviceWindow = typeof payload.service_window === "string" ? payload.service_window : "08:00-20:00";

  if (forecast24 === undefined) {
    return (
      <p className="text-sm text-[var(--color-text-ghost)] italic">
        Capacity forecast unavailable for this run.
      </p>
    );
  }

  const data = buildHourlyBars(Math.round(forecast24), serviceWindow, scenario);
  const peak = Math.max(...data.map((d) => d.visits), 0);
  const avg = data.length ? Math.round(data.reduce((s, d) => s + d.visits, 0) / data.length) : 0;
  const peakHourLabel = data.find((d) => d.visits === peak)?.hour ?? "--";
  const growth48 = forecast48 && forecast24 > 0
    ? Math.round(((forecast48 - forecast24) / forecast24) * 100)
    : null;

  const deptRows = Array.isArray(asObject(payload.capacity_snapshot)?.departments)
    ? (asObject(payload.capacity_snapshot)?.departments as Array<Record<string, unknown>>).slice(0, 3)
    : [];

  return (
    <div className="@container flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 @3xl:grid-cols-[1.3fr_1fr] @3xl:items-stretch">
        <RecommendationBlock
          recommendation={recommendation.recommendation ?? (typeof forecast.recommendation === "string" ? forecast.recommendation : null)}
          reasoning={recommendation.reasoning}
          priority={recommendation.priority}
          risks={recommendation.risks}
        />
        <div className="flex flex-col gap-3">
          <StatGrid stats={[
            {
              icon: <ICONS.chartBar className="h-4 w-4" strokeWidth={1.8} />,
              iconColor: "#818cf8",
              value: String(Math.round(forecast24)),
              label: "24h admissions",
              caption: forecast48 ? `48h projection: ${Math.round(forecast48)}` : "Next-day workload",
            },
            {
              icon: <ICONS.trendUp className="h-4 w-4" strokeWidth={1.8} />,
              iconColor: growth48 !== null && growth48 > 10 ? "#F43F5E" : "#10B981",
              value: growth48 !== null ? `${growth48 >= 0 ? "+" : ""}${growth48}%` : "--",
              label: "48h vs 24h",
              caption: "Admission volume trend",
            },
            {
              icon: <ICONS.clock className="h-4 w-4" strokeWidth={1.8} />,
              iconColor: "#8B5CF6",
              value: peakHourLabel,
              label: "Peak hour",
              caption: `${peak} visits expected`,
            },
            {
              icon: <ICONS.shieldCheck className="h-4 w-4" strokeWidth={1.8} />,
              iconColor: occupancy !== undefined && occupancy >= 85 ? "#F43F5E" : "#10B981",
              value: occupancy !== undefined ? `${Math.round(occupancy)}%` : "--",
              label: "Bed utilization",
              caption: occupancy !== undefined && occupancy >= 90 ? "Near capacity" : "Facility snapshot",
            },
          ]} />
          <PriorityGauge priority={recommendation.priority} />
        </div>
      </div>

      {deptRows.length > 0 && (
        <div className="grid grid-cols-1 gap-2.5 @lg:grid-cols-3">
          {deptRows.map((row, index) => (
            <div
              key={`${row.department}-${index}`}
              className="flex items-center justify-between gap-3 rounded-xl bg-[var(--color-surface-raised)] px-4 py-3 ring-1 ring-[var(--color-border-soft)]"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] font-semibold text-[var(--color-text-primary)]">
                  {String(row.department ?? "Department")}
                </p>
                <p className="text-[10.5px] text-[var(--color-text-faint)]">
                  {String(row.occupied_beds ?? "—")}/{String(row.total_beds ?? "—")} beds occupied
                </p>
              </div>
              <span className="shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-semibold ring-1 bg-indigo-500/10 text-indigo-300 ring-indigo-400/25">
                {Math.round(Number(row.occupancy_pct ?? 0))}%
              </span>
            </div>
          ))}
        </div>
      )}

      <div>
        <SectionTitle
          title="Admission pacing"
          right={
            <div className="flex items-center gap-1 rounded-lg bg-[var(--color-surface-raised)] p-0.5 ring-1 ring-[var(--color-border-soft)]">
              {(["bar", "line"] as const).map((type) => (
                <button
                  key={type}
                  onClick={() => setChartType(type)}
                  className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-[10.5px] font-medium capitalize transition-colors ${chartType === type ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] shadow-sm" : "text-[var(--color-text-faint)]"}`}
                >
                  {type}
                </button>
              ))}
            </div>
          }
        />

        <div ref={chartContainerRef} style={{ height: 200 }}>
          {chartType === "bar" ? (
            <BarChart width={chartWidth} height={200} data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-soft)" vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "var(--color-text-faint)" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "var(--color-text-faint)" }} axisLine={false} tickLine={false} />
              <ReferenceLine y={avg} stroke="var(--color-border-default)" strokeDasharray="4 4"
                label={{ value: "avg", position: "right", fontSize: 10, fill: "var(--color-text-faint)" }} />
              <Tooltip
                contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border-default)", borderRadius: 10, fontSize: 12 }}
                formatter={(value: unknown) => [`${value} visits`, "Expected"]}
              />
              <Bar dataKey="visits" radius={[3, 3, 0, 0]}>
                {data.map((entry) => (
                  <Cell
                    key={entry.hour}
                    fill={entry.visits === peak ? CHART_COLOR : entry.inWindow ? `${CHART_COLOR}90` : `${CHART_COLOR}35`}
                  />
                ))}
              </Bar>
            </BarChart>
          ) : (
            <LineChart width={chartWidth} height={200} data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-soft)" vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "var(--color-text-faint)" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "var(--color-text-faint)" }} axisLine={false} tickLine={false} />
              <ReferenceLine y={avg} stroke="var(--color-border-default)" strokeDasharray="4 4" />
              <Tooltip formatter={(value: unknown) => [`${value} visits`, "Expected"]} />
              <Line type="monotone" dataKey="visits" stroke={CHART_COLOR} strokeWidth={2} dot={false} />
            </LineChart>
          )}
        </div>
      </div>

      <CardFooter label="Planning window" value={serviceWindow} />
    </div>
  );
}

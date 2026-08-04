"use client";

import { CardFooter, CategoryColumn, ICONS, PriorityGauge, RecommendationBlock, StatGrid } from "./AgentStatStrip";

interface Alert {
  ingredient:        string;
  unit:              string;
  quantity_in_stock: number;
  reorder_threshold: number;
  shortfall?:        number;
  excess?:           number;
  spoilage_risk:     boolean;
  severity:          "critical" | "warning" | "info";
}

interface InventoryData {
  total_items_checked: number;
  shortage_alerts:     Alert[];
  overstock_alerts:    Alert[];
  high_demand_week:    boolean;
  demand_ratio:        number;
  scenario_label?:     string;
  service_window?:     string;
  recommendation: {
    restock_actions: string[];
    waste_reduction_actions: string[];
    priority?: string;
    reasoning?: string;
    risks: string[];
  } | null;
}

interface Props {
  inventory: Record<string, unknown> | null;
  compact?: boolean;
  swiggySignal?: string;
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-rose-500/10 ring-1 ring-rose-500/25 text-rose-600 dark:text-rose-300",
  warning:  "bg-amber-500/10 ring-1 ring-amber-500/25 text-amber-600 dark:text-amber-300",
  info:     "bg-blue-500/10  ring-1 ring-blue-500/25  text-blue-600 dark:text-blue-300",
};

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-rose-500/15 text-rose-600 dark:text-rose-300",
  warning:  "bg-amber-500/15 text-amber-600 dark:text-amber-300",
  info:     "bg-blue-500/15  text-blue-600 dark:text-blue-300",
};

function normalizeInventoryData(
  raw: Record<string, unknown> | null
): InventoryData | null {
  if (!raw) return null;
  const nested = raw.data as Record<string, unknown> | undefined;
  const payload = nested && typeof nested === "object" ? nested : raw;
  const recommendationSource =
    raw.recommendation && typeof raw.recommendation === "object"
      ? (raw.recommendation as Record<string, unknown>)
      : raw;

  const shortage  = Array.isArray(payload.shortage_alerts)  ? payload.shortage_alerts  : [];
  const overstock = Array.isArray(payload.overstock_alerts) ? payload.overstock_alerts : [];

  return {
    total_items_checked: Number(payload.total_items_checked ?? 0),
    shortage_alerts:     shortage  as Alert[],
    overstock_alerts:    overstock as Alert[],
    high_demand_week:    Boolean(payload.high_demand_week),
    demand_ratio:        Number(payload.demand_ratio ?? 1.0),
    scenario_label:      typeof payload.scenario_label === "string" ? String(payload.scenario_label) : undefined,
    service_window:      typeof payload.service_window === "string" ? String(payload.service_window) : undefined,
    recommendation:
      recommendationSource && typeof recommendationSource === "object"
        ? {
            restock_actions: Array.isArray(recommendationSource.restock_actions)
              ? (recommendationSource.restock_actions as string[])
              : [],
            waste_reduction_actions: Array.isArray(recommendationSource.waste_reduction_actions)
              ? (recommendationSource.waste_reduction_actions as string[])
              : [],
            priority: typeof recommendationSource.priority === "string"
              ? String(recommendationSource.priority)
              : undefined,
            reasoning: typeof recommendationSource.reasoning === "string"
              ? String(recommendationSource.reasoning)
              : undefined,
            risks: Array.isArray(recommendationSource.risks)
              ? (recommendationSource.risks as string[])
              : [],
          }
        : null,
  };
}

function AlertRow({ alert, type }: { alert: Alert; type: "shortage" | "overstock" }) {
  const sev = alert.severity ?? "info";
  return (
    <div className={`rounded-xl px-4 py-3 ${SEVERITY_STYLES[sev]}`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          {sev === "critical" && (
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-rose-500" />
            </span>
          )}
          <span className="text-sm font-semibold text-[var(--color-text-primary)]">{alert.ingredient}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {alert.spoilage_risk && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-600 dark:text-rose-300 font-medium">
              spoilage risk
            </span>
          )}
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${SEVERITY_BADGE[sev]}`}>
            {sev}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-text-soft)]">
        <span>stock: {alert.quantity_in_stock} {alert.unit}</span>
        <span>threshold: {alert.reorder_threshold} {alert.unit}</span>
        {type === "shortage"  && alert.shortfall !== undefined && (
          <span className="text-rose-600 dark:text-rose-300 font-medium">shortfall: {alert.shortfall} {alert.unit}</span>
        )}
        {type === "overstock" && alert.excess !== undefined && (
          <span className="text-amber-600 dark:text-amber-300 font-medium">excess: {alert.excess} {alert.unit}</span>
        )}
      </div>
    </div>
  );
}

function AlertGroup({ icon, color, label, alerts, type }: { icon: React.ReactNode; color: string; label: string; alerts: Alert[]; type: "shortage" | "overstock" }) {
  if (alerts.length === 0) return null;
  return (
    <div className="rounded-2xl ring-1 ring-[var(--color-border-soft)] bg-[var(--color-surface-raised)] p-4">
      <div className="flex items-center gap-1.5">
        <span style={{ color }}>{icon}</span>
        <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color }}>{label} &middot; {alerts.length}</p>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 @lg:grid-cols-2">
        {alerts.map((a, i) => <AlertRow key={i} alert={a} type={type} />)}
      </div>
    </div>
  );
}

export default function InventoryAlerts({ inventory, swiggySignal }: Props) {
  const data = normalizeInventoryData(inventory);
  if (!data) return null;

  const hasShortage  = data.shortage_alerts.length  > 0;
  const hasOverstock = data.overstock_alerts.length > 0;
  const allClear     = !hasShortage && !hasOverstock;
  const recommendation = data.recommendation;
  const serviceWindow = data.service_window ?? "this service window";
  const criticalCount = data.shortage_alerts.filter((a) => a.severity === "critical").length;

  const shortageSorted = [...data.shortage_alerts].sort((a, b) => {
    const score = (sev: Alert["severity"]) =>
      sev === "critical" ? 2 : sev === "warning" ? 1 : 0;
    return score(b.severity) - score(a.severity);
  });

  // No single "recommendation" text field in this schema -- the top restock
  // action is the real headline equivalent (same substitute-with-real-data
  // convention used for Menu's highlight item). The rest of restock_actions
  // renders below as the itemized breakdown, so this one isn't dropped, just
  // also surfaced as the headline.
  const headlineAction = recommendation?.restock_actions[0] ?? null;
  const restockRest = recommendation?.restock_actions.slice(headlineAction ? 1 : 0) ?? [];
  const wastePreview = recommendation?.waste_reduction_actions ?? [];

  return (
    <div className="@container flex flex-col gap-5">
      {/* Recommendation (left) + stat grid & priority gauge (right) side by side */}
      <div className="grid grid-cols-1 gap-4 @3xl:grid-cols-[1.3fr_1fr] @3xl:items-stretch">
        <RecommendationBlock
          recommendation={headlineAction}
          reasoning={recommendation?.reasoning}
          priority={recommendation?.priority}
          risks={recommendation?.risks}
        />
        <div className="flex flex-col gap-3">
          <StatGrid stats={[
            { icon: <ICONS.warning className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#F43F5E", value: String(data.shortage_alerts.length), label: "Active shortages", caption: criticalCount > 0 ? `${criticalCount} critical` : "None critical" },
            { icon: <ICONS.cube className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#8B5CF6", value: String(data.total_items_checked), label: "Items checked", caption: "Across full stock list" },
            { icon: <ICONS.trendUp className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#F59E0B", value: `${data.demand_ratio.toFixed(2)}x`, label: "Demand ratio", caption: data.high_demand_week ? "High demand week" : "Normal demand" },
            { icon: <ICONS.chartBar className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#10B981", value: String(data.overstock_alerts.length), label: "Overstock alerts", caption: "Excess to redistribute" },
          ]} />
          <PriorityGauge priority={recommendation?.priority} />
        </div>
      </div>

      {/* All clear */}
      {allClear && (
        <div className="rounded-2xl ring-1 ring-emerald-400/25 bg-emerald-500/[0.05] px-4 py-3">
          <p className="text-sm text-emerald-600 dark:text-emerald-300 font-semibold">
            All stock levels are within safe range.
          </p>
          <p className="text-xs text-[var(--color-text-faint)] mt-1">
            No restocking or waste-reduction actions required before {serviceWindow.toLowerCase()}.
          </p>
        </div>
      )}

      {/* Shortage + overstock alert groups */}
      <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2">
        <AlertGroup icon={<ICONS.warning className="h-3.5 w-3.5" strokeWidth={1.8} />} color="#F43F5E" label="Shortage Alerts" alerts={shortageSorted} type="shortage" />
        <AlertGroup icon={<ICONS.trendUp className="h-3.5 w-3.5" strokeWidth={1.8} />} color="#F59E0B" label="Overstock Alerts" alerts={data.overstock_alerts} type="overstock" />
      </div>

      {/* Remaining actions -- restock_actions beyond the headline one, plus waste reduction */}
      <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2">
        <CategoryColumn
          icon={<ICONS.shieldCheck className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Other Restock Actions"
          items={restockRest}
          tone="warn"
        />
        <CategoryColumn
          icon={<ICONS.noEntry className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Waste Reduction"
          items={wastePreview.map((a) => a)}
          tone="good"
        />
      </div>

      <CardFooter label="Service window" value={serviceWindow} swiggySignal={swiggySignal} />
    </div>
  );
}

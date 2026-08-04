"use client";

import { CardFooter, CategoryColumn, ICONS, PriorityGauge, RecommendationBlock, SectionTitle, StatGrid } from "./AgentStatStrip";

interface TopItem {
  item: string;
  category?: string;
  total_ordered?: number;
}

interface MenuInsightsData {
  data?: {
    top_items?: TopItem[];
    forecast_snapshot?: {
      predicted_orders?: number;
      predicted_peak_orders?: number;
      avg_friday_orders?: number;
      target_date?: string;
    };
    complaint_themes?: string[];
    shortage_ingredients?: string[];
    overstock_ingredients?: string[];
    scenario_label?: string;
    service_window?: string;
    scenario_watchouts?: string[];
    note?: string;
  };
  top_items?: TopItem[];
  highlight_items?: string[];
  deprioritize_items?: string[];
  promo_candidates?: string[];
  inventory_blockers?: string[];
  complaint_watchouts?: string[];
  operational_notes?: string[];
  reasoning?: string;
  priority?: string;
  risks?: string[];
}

export default function MenuInsights({ data }: { data: MenuInsightsData }) {
  return <MenuInsightsBody data={data} compact={false} />;
}

export function MenuInsightsBody({
  data,
  swiggySignal,
}: {
  data: MenuInsightsData;
  compact?: boolean;
  swiggySignal?: string;
}) {
  const detail = data.data ?? {};
  const topItems = detail.top_items ?? data.top_items ?? [];
  const complaintThemes = detail.complaint_themes ?? [];
  const shortageIngredients = detail.shortage_ingredients ?? [];
  const overstockIngredients = detail.overstock_ingredients ?? [];
  const scenarioLabel = detail.scenario_label ?? "service";
  const serviceWindow = detail.service_window ?? "this service window";
  const scenarioWatchouts = detail.scenario_watchouts ?? [];
  const highlightItems = data.highlight_items ?? [];
  const promoCandidates = data.promo_candidates ?? [];
  const inventoryBlockers = data.inventory_blockers ?? shortageIngredients;
  const complaintWatchouts = data.complaint_watchouts ?? complaintThemes;
  const watchoutCount = inventoryBlockers.length + complaintWatchouts.length;

  return (
    <div className="@container flex flex-col gap-5">
      {/* Recommendation (left) + stat grid & priority gauge (right) side by side */}
      <div className="grid grid-cols-1 gap-4 @3xl:grid-cols-[1.3fr_1fr] @3xl:items-stretch">
        <RecommendationBlock
          recommendation={highlightItems[0] ? `Feature ${highlightItems[0]} tonight.` : null}
          reasoning={data.reasoning}
          priority={data.priority}
          risks={data.risks}
        />
        <div className="flex flex-col gap-3">
          <StatGrid stats={[
            { icon: <ICONS.trendUp className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#10B981", value: String(highlightItems.length), label: "Items to push", caption: "High impact tonight" },
            { icon: <ICONS.star className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#F59E0B", value: String(topItems.length), label: "Historic sellers", caption: "Proven demand consistency" },
            { icon: <ICONS.tag className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#8B5CF6", value: String(promoCandidates.length), label: "Promo candidates", caption: "Drive incremental orders" },
            { icon: <ICONS.warning className="h-4 w-4" strokeWidth={1.8} />, iconColor: "#F43F5E", value: String(watchoutCount), label: "Watchouts", caption: "Inventory + complaints" },
          ]} />
          <PriorityGauge priority={data.priority} />
        </div>
      </div>

      {/* Best sellers + category columns, one flowing grid */}
      <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2 @4xl:grid-cols-4">
        {topItems.length > 0 && (
          <div className="rounded-2xl ring-1 ring-[var(--color-border-soft)] bg-[var(--color-surface-raised)] p-4">
            <SectionTitle title={`Best Sellers for ${scenarioLabel}`} />
            <div className="space-y-2">
              {topItems.map((item, index) => (
                <div key={`top-item-${index}`} className="flex items-center gap-3">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[var(--color-surface-sunken)] text-[10px] font-bold text-[var(--color-text-faint)]">{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-semibold text-[var(--color-text-primary)]">{item.item}</p>
                    {item.category && <p className="text-[10.5px] text-[var(--color-text-faint)]">{item.category}</p>}
                  </div>
                  {typeof item.total_ordered === "number" && (
                    <span className="shrink-0 text-[11px] font-semibold text-amber-700 dark:text-amber-300">{item.total_ordered} ordered</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <CategoryColumn
          icon={<ICONS.star className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Highlight Items"
          items={highlightItems}
          tone="good"
          callout={highlightItems.length > 0 ? "Proven demand -- safe to push tonight." : undefined}
        />
        <CategoryColumn
          icon={<ICONS.tag className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Promo Candidates"
          items={promoCandidates}
          tone="info"
          callout={promoCandidates.length > 0 ? "Good opportunity to increase basket size and explore new preferences." : undefined}
        />
        <CategoryColumn
          icon={<ICONS.noEntry className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Deprioritize Items"
          items={data.deprioritize_items ?? []}
          tone="warn"
          callout={(data.deprioritize_items?.length ?? 0) > 0 ? "High prep time, lower margins, or a higher complaint rate." : undefined}
        />
      </div>

      {/* Operational + risk breakdown, one flowing grid */}
      <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2 @4xl:grid-cols-3">
        <CategoryColumn
          icon={<ICONS.shieldCheck className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Operational Notes"
          items={data.operational_notes ?? []}
          tone="info"
        />
        <CategoryColumn
          icon={<ICONS.cube className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Inventory Blockers"
          items={inventoryBlockers}
          tone="warn"
        />
        <CategoryColumn
          icon={<ICONS.chat className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Complaint Watchouts"
          items={complaintWatchouts}
          tone="warn"
        />
        <CategoryColumn
          icon={<ICONS.warning className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Scenario Watchouts"
          items={scenarioWatchouts}
          tone="warn"
        />
        <CategoryColumn
          icon={<ICONS.trendUp className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="Overstock Opportunities"
          items={overstockIngredients}
          tone="good"
          callout={overstockIngredients.length > 0 ? "Use in specials or promotions before the buffer window closes." : undefined}
        />
      </div>

      <CardFooter label="Service window" value={serviceWindow} swiggySignal={swiggySignal} />
    </div>
  );
}

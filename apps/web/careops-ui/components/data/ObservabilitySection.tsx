"use client";

import { Fragment, useEffect, useState } from "react";
import { getObservabilitySummary, getPlanningRun, listPlanningRuns, ObservabilitySummary } from "@/lib/api";
import { PlanningRunDetail, PlanningRunMetadata, PlanningRunSummary } from "@/types/planning";
import ObservabilityStrip from "@/components/planning/ObservabilityStrip";

// Same visual system as RunHistorySection.tsx / DataHealthSection.tsx: icon
// badge header, .card .card-lift containers, distinct warm-family color per
// tile/section instead of a single repeated grey box.

function IconPulse(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M3 12h4l2-8 4 16 2-8h6" /></svg>;
}
function IconCheckCircle(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
function IconStar(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.562.562 0 00-.586 0L6.982 21.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" /></svg>;
}
function IconClock(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 7v5l3.5 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
function IconGauge(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9 9 0 100-18 9 9 0 000 18z" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 12l3.5-3.5M8 12a4 4 0 118 0" /></svg>;
}
function IconChip(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2.25M15 3v2.25M9 18.75V21M15 18.75V21M3 9h2.25M3 15h2.25M18.75 9H21M18.75 15H21M7.5 6h9a1.5 1.5 0 011.5 1.5v9a1.5 1.5 0 01-1.5 1.5h-9A1.5 1.5 0 016 16.5v-9A1.5 1.5 0 017.5 6z" /></svg>;
}
function IconWallet(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M21 12V7H5a2 2 0 010-4h14v4M3 5v14a2 2 0 002 2h16v-5M18 12a2 2 0 000 4h4v-4h-4z" /></svg>;
}
function IconTag(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z" /><path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6z" /></svg>;
}
function IconLayers(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 3l9 4.5-9 4.5-9-4.5L12 3zm-9 9l9 4.5 9-4.5" /></svg>;
}
function IconChevronDown(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>;
}

const SECTION_COLOR = {
  observability: "#10B981",
  infra: "#7C3AED",
} as const;

function SectionHeading({ title, sub, icon, color }: { title: string; sub?: string; icon: React.ReactNode; color: string }) {
  return (
    <div className="mb-4 flex items-center gap-3">
      <span
        className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white shadow-sm"
        style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</h2>
        {sub && <p className="mt-0.5 text-xs text-[var(--color-text-faint)]">{sub}</p>}
      </div>
    </div>
  );
}

// Horizontal row (icon left, value/label right) -- stacked in a column of 4,
// not a wide 4-across grid, so a tall icon-on-top tile would waste width and
// look cramped.
function StatTile({ icon, color, value, label, valueClass }: { icon: React.ReactNode; color: string; value: string; label: string; valueClass?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-[var(--color-surface-raised)] p-3.5 shadow-sm ring-1 ring-[var(--color-border-soft)]">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full" style={{ background: `${color}18`, color }}>
        {icon}
      </span>
      <div className="min-w-0">
        <p className={`text-xl font-bold leading-tight ${valueClass ?? "text-[var(--color-text-primary)]"}`}>{value}</p>
        <p className="text-[11px] font-semibold text-[var(--color-text-soft)]">{label}</p>
      </div>
    </div>
  );
}

function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return "--";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

const SCENARIO_LABELS: Record<string, string> = {
  ed_surge:          "Emergency Surge",
  opd_peak:          "OPD Peak Load",
  icu_capacity:      "ICU Capacity Watch",
  supply_shortage:   "Supply Shortage Response",
  friday_rush:       "Emergency Surge",
  weekday_lunch:     "OPD Peak Load",
  holiday_spike:     "ICU Capacity Watch",
  low_stock_weekend: "Supply Shortage Response",
};

function scenarioTitle(run: { scenario: string; scenario_label: string | null }): string {
  return run.scenario_label || SCENARIO_LABELS[run.scenario] || run.scenario.replace(/_/g, " ");
}

export default function ObservabilitySection() {
  const [obs, setObs] = useState<ObservabilitySummary | null>(null);
  const [runs, setRuns] = useState<PlanningRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Per-run node breakdown -- lazy-fetched only when a row is expanded
  // (the list view never carries node_traces, only the full run detail
  // does), then cached so re-expanding the same row doesn't refetch.
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [detailCache, setDetailCache] = useState<Record<number, PlanningRunDetail>>({});
  const [detailLoading, setDetailLoading] = useState<number | null>(null);

  useEffect(() => {
    getObservabilitySummary(7)
      .then(setObs)
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load observability summary"));
    listPlanningRuns(50)
      .then(setRuns)
      .catch(() => { /* cost table is non-blocking */ });
  }, []);

  async function toggleExpand(runId: number) {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }
    setExpandedRunId(runId);
    if (!detailCache[runId]) {
      setDetailLoading(runId);
      try {
        const detail = await getPlanningRun(runId);
        setDetailCache(prev => ({ ...prev, [runId]: detail }));
      } catch {
        // non-blocking -- row just stays without a breakdown
      } finally {
        setDetailLoading(null);
      }
    }
  }

  // Cost/token aggregates -- only runs that actually recorded infra metadata
  // count (older runs, or ones where the meta write failed, have nulls; a
  // run with no data shouldn't silently read as $0).
  const costed = runs.filter((r) => r.total_cost_usd != null);
  const totalCost = costed.reduce((sum, r) => sum + (r.total_cost_usd ?? 0), 0);
  const totalTokens = costed.reduce((sum, r) => sum + (r.total_tokens ?? 0), 0);
  const cachedCount = runs.filter((r) => r.cache_hit === true).length;

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      {/* Observability + AI Infrastructure -- two columns of 4 stacked stat
          rows side by side, instead of two separate full-width 4-across
          grids one below the other. */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {obs && (
          <section>
            <SectionHeading
              title="Observability"
              sub={
                obs.latest_run_at
                  ? `Your last ${obs.period_days} days · latest ${new Date(obs.latest_run_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`
                  : `Your last ${obs.period_days} days of planning`
              }
              icon={<IconPulse className="h-4 w-4" />}
              color={SECTION_COLOR.observability}
            />

            <div className="space-y-3">
              <StatTile icon={<IconLayers className="h-4 w-4" />} color="#10B981" value={String(obs.total_runs)} label="Total runs" />
              <StatTile
                icon={<IconCheckCircle className="h-4 w-4" />}
                color={obs.success_rate != null && obs.success_rate >= 0.8 ? "#10B981" : "#F59E0B"}
                value={obs.success_rate != null ? `${Math.round(obs.success_rate * 100)}%` : "--"}
                label="Success rate"
                valueClass={obs.success_rate != null && obs.success_rate >= 0.8 ? "text-emerald-600 dark:text-emerald-300" : "text-[var(--color-accent)]"}
              />
              <StatTile icon={<IconStar className="h-4 w-4" />} color="#D97706" value={obs.avg_critic_score != null ? `${Math.round(obs.avg_critic_score * 100)}/100` : "--"} label="Avg critic score" />
              <StatTile icon={<IconClock className="h-4 w-4" />} color="#0891B2" value={obs.avg_duration_ms != null ? `${(obs.avg_duration_ms / 1000).toFixed(1)}s` : "--"} label="Avg duration" />
            </div>
          </section>
        )}

        {/* AI infrastructure cost breakdown -- per-run LLM cost/tokens/model,
            read from each run's stored metadata (no per-row detail fetch). */}
        <section>
          <SectionHeading title="AI Infrastructure" sub="Cost & token usage per run" icon={<IconChip className="h-4 w-4" />} color={SECTION_COLOR.infra} />

          <div className="space-y-3">
            <StatTile icon={<IconWallet className="h-4 w-4" />} color="#7C3AED" value={`$${totalCost.toFixed(4)}`} label={`Total cost -- ${costed.length} run${costed.length !== 1 ? "s" : ""}`} />
            <StatTile icon={<IconTag className="h-4 w-4" />} color="#7C3AED" value={totalTokens.toLocaleString()} label="Total tokens" />
            <StatTile icon={<IconGauge className="h-4 w-4" />} color="#7C3AED" value={`$${costed.length > 0 ? (totalCost / costed.length).toFixed(4) : "0.0000"}`} label="Avg cost / run" />
            <StatTile icon={<IconCheckCircle className="h-4 w-4" />} color="#0891B2" value={`${cachedCount} / ${runs.length}`} label="Cache hits" valueClass="text-cyan-600 dark:text-cyan-300" />
          </div>
        </section>
      </div>

      {/* Per-run breakdown table */}
      <section>
        <p className="mb-2 text-[11px] text-[var(--color-text-faint)]">Click a row to see which node used which model/tier and what it cost -- per-node breakdown, not just the run total.</p>
        <div className="overflow-hidden rounded-2xl bg-[var(--color-surface-raised)] shadow-sm ring-1 ring-[var(--color-border-soft)]">
          <table className="w-full text-left text-sm">
            <thead className="bg-[var(--color-surface-sunken)] text-xs uppercase tracking-[0.14em] text-[var(--color-text-faint)]">
              <tr>
                <th className="w-8 px-3 py-3" />
                <th className="px-3 py-3">Run</th>
                <th className="px-3 py-3">Scenario</th>
                <th className="px-3 py-3">Model</th>
                <th className="px-3 py-3">Tokens</th>
                <th className="px-3 py-3">Cost</th>
                <th className="px-3 py-3">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border-soft)]">
              {runs.length === 0 ? (
                <tr><td colSpan={7} className="px-3 py-6 text-center text-xs text-[var(--color-text-faint)] italic">No runs yet.</td></tr>
              ) : (
                runs.map((run) => {
                  const isExpanded = expandedRunId === run.id;
                  return (
                    <Fragment key={run.id}>
                      <tr
                        onClick={() => toggleExpand(run.id)}
                        className="cursor-pointer hover:bg-[var(--color-surface-sunken)] transition-colors duration-150"
                      >
                        <td className="px-3 py-3">
                          <IconChevronDown className={`h-3.5 w-3.5 text-[var(--color-text-faint)] transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                        </td>
                        <td className="px-3 py-3 text-xs tabular-nums text-[var(--color-text-faint)]">#{run.id}</td>
                        <td className="px-3 py-3 truncate max-w-[180px]">{scenarioTitle(run)}</td>
                        <td className="px-3 py-3">
                          {run.llm_model ? (
                            <span className="inline-flex items-center gap-1.5">
                              <span className="h-1.5 w-1.5 rounded-full bg-ember-400/70" />
                              <span className="text-[12px] text-[var(--color-text-soft)]">{run.llm_model}</span>
                              {run.llm_provider && <span className="text-[11px] text-[var(--color-text-ghost)]">· {run.llm_provider}</span>}
                            </span>
                          ) : "--"}
                        </td>
                        <td className="px-3 py-3 text-xs tabular-nums">{run.total_tokens != null ? run.total_tokens.toLocaleString() : "--"}</td>
                        <td className="px-3 py-3 text-xs tabular-nums">
                          {run.cache_hit ? (
                            <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-cyan-600 dark:text-cyan-300 ring-1 ring-cyan-400/20">cached</span>
                          ) : run.total_cost_usd != null ? `$${run.total_cost_usd.toFixed(5)}` : "--"}
                        </td>
                        <td className="px-3 py-3 text-xs tabular-nums">{fmtDuration(run.total_duration_ms)}</td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} className="bg-[var(--color-surface-sunken)] p-3">
                            {detailLoading === run.id ? (
                              <p className="py-4 text-center text-xs text-[var(--color-text-faint)] italic">Loading per-node breakdown...</p>
                            ) : detailCache[run.id]?.metadata ? (
                              <ObservabilityStrip metadata={detailCache[run.id].metadata as PlanningRunMetadata} />
                            ) : (
                              <p className="py-4 text-center text-xs text-[var(--color-text-ghost)] italic">No per-node trace recorded for this run.</p>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

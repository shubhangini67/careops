"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { getPlanningRun, listPlanningRuns } from "@/lib/api";
import { downloadRunPdf, downloadRunExcel } from "@/lib/exportRun";
import { PlanningRunDetail, PlanningRunSummary } from "@/types/planning";
import EvidencePanel from "@/components/planning/EvidencePanel";
import { ICONS } from "@/components/dashboard/AgentStatStrip";

// ── Small chrome icons (page-level, not agent-specific -- AgentStatStrip's
// ICONS set covers the agent-card vocabulary; these cover list/detail chrome) ──

function CalendarIcon(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" /></svg>;
}
function SearchIcon(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" /></svg>;
}
function FunnelIcon(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 01-.659 1.591l-5.432 5.432a2.25 2.25 0 00-.659 1.591v2.927a2.25 2.25 0 01-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 00-.659-1.591L3.659 7.409A2.25 2.25 0 013 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0112 3z" /></svg>;
}
function CheckCircleIcon(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
function ExportIcon(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>;
}
function ScaleIcon(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M3 7l6.75-3 6.75 3M3 7l6.75 3M3 7v10.5m6.75-4.5L3 17.5m6.75-4.5l6.75-3m0 0L21 7m-4.5 3v10.5M21 7l-6.75 3m6.75-3v10.5m-9-3l-1.5 3.75a1.5 1.5 0 001.5 1.5h0a1.5 1.5 0 001.5-1.5L9 13.5m9 0l-1.5 3.75a1.5 1.5 0 001.5 1.5h0a1.5 1.5 0 001.5-1.5L18 13.5" /></svg>;
}

// ── Circular score gauge -- reused at 3 sizes: small (list rows), large
// (detail header critic score), medium (cost/tradeoff panel) ──────────────

function ScoreRing({ value, size = 64, thickness = 6, color }: { value: number; size?: number; thickness?: number; color?: string }) {
  const r = (size - thickness) / 2;
  const circumference = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value));
  const dashOffset = circumference * (1 - pct);
  const c = color ?? "var(--color-accent)";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-border-soft)" strokeWidth={thickness} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c} strokeWidth={thickness} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={dashOffset}
          style={{ transition: "stroke-dashoffset 0.4s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="num-display" style={{ fontSize: size * 0.32, color: "var(--color-text-primary)" }}>{Math.round(pct * 100)}</span>
        <span style={{ fontSize: Math.max(8, size * 0.12) }} className="text-[var(--color-text-faint)]">/100</span>
      </div>
    </div>
  );
}

// ── Constants ────────────────────────────────────────────────────────────────

const SCENARIOS = [
  { value: "", label: "All scenarios" },
  { value: "ed_surge",          label: "Emergency Surge" },
  { value: "opd_peak",          label: "OPD Peak Load" },
  { value: "icu_capacity",      label: "ICU Capacity Watch" },
  { value: "supply_shortage",   label: "Supply Shortage Response" },
];

const VERDICTS = [
  { value: "", label: "All verdicts" },
  { value: "approved", label: "Approved" },
  { value: "revision", label: "Revision" },
  { value: "rejected", label: "Rejected" },
];

const VERDICT_STYLE: Record<string, string> = {
  approved: "text-emerald-600 dark:text-emerald-300 border-emerald-500/30 bg-emerald-500/10",
  rejected: "text-rose-600 dark:text-rose-300 border-rose-500/30 bg-rose-500/10",
  revision: "text-amber-600 dark:text-amber-300 border-amber-500/30 bg-amber-500/10",
  unknown:  "text-[var(--color-text-soft)] border-[var(--color-border-default)] bg-[var(--color-surface-sunken)]",
};

const STATUS_LABEL: Record<string, string> = {
  ready: "Ready", needs_review: "Needs Review", blocked: "Blocked", unknown: "Unknown",
};
const STATUS_STYLE: Record<string, string> = {
  ready:        "text-[var(--color-accent)] border-ember-400/30 bg-ember-500/10",
  needs_review: "text-amber-600 dark:text-amber-300 border-amber-500/30 bg-amber-500/10",
  blocked:      "text-rose-600 dark:text-rose-300 border-rose-500/30 bg-rose-500/10",
  unknown:      "text-[var(--color-text-soft)] border-[var(--color-border-default)] bg-[var(--color-surface-sunken)]",
};

const VERDICT_DOT: Record<string, string> = {
  approved: "#34d399",
  revision: "#fbbf24",
  rejected: "#f87171",
  unknown:  "#94a3b8",
};

const DIMENSIONS = ["safety", "feasibility", "evidence", "actionability", "clarity"];

// scenario_label is the real resolved title (e.g. "Anniversary Dinner") --
// for a custom (natural-language-derived) run, `scenario` itself is just the
// literal id "custom", indistinguishable from every other custom run without
// this. Falls back to the prettified id for runs recorded before this field
// existed.
function scenarioTitle(run: { scenario: string; scenario_label?: string | null }): string {
  return run.scenario_label || run.scenario.replace(/_/g, " ");
}

const PRESET_SCENARIO_IDS = new Set(["ed_surge", "opd_peak", "icu_capacity", "supply_shortage", "friday_rush", "weekday_lunch", "holiday_spike", "low_stock_weekend"]);

function isCustomScenario(scenario: string): boolean {
  return !PRESET_SCENARIO_IDS.has(scenario);
}

// created_at is the actual wall-clock moment the run happened -- distinct
// from target_date (the date the plan is FOR). Two runs targeting the same
// date only differ by this.
function relativeTime(createdAt: string | null): string {
  if (!createdAt) return "-";
  const then = new Date(createdAt).getTime();
  if (Number.isNaN(then)) return "-";
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(createdAt).toLocaleDateString();
}

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "--";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

// ── Cost & Tradeoffs captions -- threshold-based descriptions of the real
// cost_analysis scores, same pattern as AgentStatStrip's PriorityGauge copy ──

function costPressureCaption(v: number): string {
  if (v >= 0.6) return "High ingredient cost volatility";
  if (v >= 0.35) return "Moderate cost pressure";
  return "Low cost pressure this run";
}
function benefitCaption(v: number): string {
  if (v >= 0.6) return "Strong revenue uplift opportunity";
  if (v >= 0.35) return "Revenue uplift opportunity";
  return "Limited upside this run";
}
function tradeoffCaption(v: number): string {
  if (v >= 0.5) return "Balanced risk vs reward";
  if (v >= 0.3) return "Moderate risk vs reward";
  return "Risk outweighs reward";
}

// ── Trend chart ───────────────────────────────────────────────────────────────

function TrendChart({ runs }: { runs: PlanningRunSummary[] }) {
  const data = [...runs]
    .reverse()
    .filter(r => r.critic_score != null)
    .map(r => ({
      label: `#${r.id}`,
      score: Math.round((r.critic_score ?? 0) * 100),
      verdict: r.critic_verdict ?? "unknown",
      scenario: r.scenario,
    }));

  if (data.length < 2) return (
    <p className="text-xs text-[var(--color-text-faint)] px-1">Need at least 2 runs to show trend.</p>
  );

  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
        <defs>
          <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#818cf8" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#64748b" }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#64748b" }} />
        <Tooltip
          contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={(v: any, _: any, props: any) => [
            `${v}/100`,
            `${props.payload?.scenario ?? ""}  -  ${props.payload?.verdict ?? ""}`,
          ]}
          labelStyle={{ color: "#94a3b8" }}
        />
        <Area
          type="monotone"
          dataKey="score"
          stroke="#818cf8"
          strokeWidth={2}
          fill="url(#scoreGrad)"
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          dot={(props: any) => (
            <circle
              key={`dot-${props.cx}-${props.cy}`}
              cx={props.cx ?? 0} cy={props.cy ?? 0} r={4}
              fill={VERDICT_DOT[props.payload?.verdict ?? "unknown"]}
              stroke="#0f172a" strokeWidth={2}
            />
          )}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Diff modal ────────────────────────────────────────────────────────────────

function DiffModal({
  runA, runB, onClose,
}: {
  runA: PlanningRunDetail;
  runB: PlanningRunDetail;
  onClose: () => void;
}) {
  const dimA = runA.critic?.dimension_scores ?? {};
  const dimB = runB.critic?.dimension_scores ?? {};

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-3xl rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-[var(--color-border-default)] px-6 py-4">
          <h2 className="text-sm font-semibold">Run Comparison</h2>
          <button onClick={onClose} className="text-[var(--color-text-faint)] hover:text-[var(--color-text-primary)] text-lg leading-none">✕</button>
        </div>

        {/* Summary row */}
        <div className="grid grid-cols-2 gap-px bg-[var(--color-surface-raised)] border-b border-[var(--color-border-default)]">
          {[runA, runB].map((run, i) => (
            <div key={i} className="bg-[var(--color-surface-raised)] px-6 py-4">
              <p className="font-mono text-xs text-[var(--color-text-faint)]">Run #{run.id}</p>
              <p className="mt-1 text-sm font-medium">{scenarioTitle(run)}</p>
              <div className="mt-2 flex items-center gap-3">
                <span className={`rounded-full border px-2 py-0.5 text-xs ${VERDICT_STYLE[run.critic_verdict ?? "unknown"]}`}>
                  {run.critic_verdict ?? "unknown"}
                </span>
                <span className="text-sm font-bold text-[var(--color-text-primary)]">
                  {run.critic_score != null ? `${Math.round(run.critic_score * 100)}/100` : "--"}
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--color-text-faint)]">target {run.target_date ?? "-"}</p>
            </div>
          ))}
        </div>

        {/* Dimension comparison */}
        <div className="px-6 py-5 space-y-4">
          <p className="text-xs uppercase tracking-[0.16em] text-[var(--color-text-faint)]">Critic Dimension Scores</p>
          {DIMENSIONS.map(dim => {
            const a = (dimA[dim] ?? 0) * 100;
            const b = (dimB[dim] ?? 0) * 100;
            const diff = a - b;
            return (
              <div key={dim} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="capitalize text-[var(--color-text-soft)]">{dim}</span>
                  <span className={`font-mono ${diff > 3 ? "text-emerald-400" : diff < -3 ? "text-rose-400" : "text-[var(--color-text-faint)]"}`}>
                    {diff > 0 ? "+" : ""}{Math.round(diff)}
                  </span>
                </div>
                <div className="flex gap-2 items-center">
                  {/* Run A bar */}
                  <div className="flex-1 h-2 rounded-full bg-[var(--color-surface-sunken)] overflow-hidden">
                    <div className="h-full rounded-full bg-ember-500" style={{ width: `${a}%` }} />
                  </div>
                  <div className="w-16 text-center">
                    <span className="text-xs text-[var(--color-text-soft)] font-mono">
                      {Math.round(a)} <span className="text-[var(--color-text-ghost)]">vs</span> {Math.round(b)}
                    </span>
                  </div>
                  {/* Run B bar */}
                  <div className="flex-1 h-2 rounded-full bg-[var(--color-surface-sunken)] overflow-hidden">
                    <div className="h-full rounded-full bg-cyan-500" style={{ width: `${b}%` }} />
                  </div>
                </div>
              </div>
            );
          })}

          <div className="flex items-center gap-4 pt-2 text-xs text-[var(--color-text-faint)]">
            <span className="flex items-center gap-1.5"><span className="w-3 h-1.5 rounded-full bg-ember-500 inline-block" /> Run #{runA.id}</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-1.5 rounded-full bg-cyan-500 inline-block" /> Run #{runB.id}</span>
          </div>
        </div>

        {/* Revision reasons diff */}
        {(runA.critic?.revision_reasons?.length || runB.critic?.revision_reasons?.length) ? (
          <div className="grid grid-cols-2 gap-px bg-[var(--color-surface-raised)] border-t border-[var(--color-border-default)]">
            {[runA, runB].map((run, i) => (
              <div key={i} className="bg-[var(--color-surface-raised)] px-6 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-[var(--color-text-faint)] mb-2">Revision reasons</p>
                {run.critic?.revision_reasons?.length ? (
                  <ul className="space-y-1.5">
                    {run.critic.revision_reasons.map((r, j) => (
                      <li key={j} className="text-xs text-amber-300/80 bg-amber-500/5 border border-amber-500/10 rounded px-2 py-1.5">{r}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-[var(--color-text-ghost)]">None</p>
                )}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── Main section ─────────────────────────────────────────────────────────────

export default function RunHistorySection({ initialRunId, onRunChange }: { initialRunId?: number; onRunChange?: (id: number) => void }) {
  const [runs,     setRuns]     = useState<PlanningRunSummary[]>([]);
  const [selected, setSelected] = useState<PlanningRunDetail | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  // Keep the parent page's URL in sync with whichever run is on screen --
  // this is what makes a refresh (or a bookmark/share of the URL) land back
  // on the same run instead of resetting to the newest one.
  useEffect(() => {
    if (selected) onRunChange?.(selected.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  // Filter state
  const [filtersOpen,    setFiltersOpen]    = useState(false);
  const [filterScenario, setFilterScenario] = useState("");
  const [filterVerdict,  setFilterVerdict]  = useState("");
  const [filterFrom,     setFilterFrom]     = useState("");
  const [filterTo,       setFilterTo]       = useState("");
  const [search,         setSearch]         = useState("");
  const [showChart,      setShowChart]      = useState(false);
  const [sortDesc,       setSortDesc]       = useState(true);

  // Compare state
  const [compareIds, setCompareIds]             = useState<number[]>([]);
  const [diffRuns,   setDiffRuns]               = useState<[PlanningRunDetail, PlanningRunDetail] | null>(null);
  const [diffLoading, setDiffLoading]           = useState(false);

  // Export helpers
  const [exportingPdf,   setExportingPdf]   = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);

  async function downloadPdf(runId: number, scenario: string) {
    setExportingPdf(true);
    try {
      await downloadRunPdf(runId, scenario);
    } catch (err) {
      console.error("PDF export error:", err);
    } finally {
      setExportingPdf(false);
    }
  }

  async function downloadExcel(runId: number, scenario: string) {
    setExportingExcel(true);
    try {
      await downloadRunExcel(runId, scenario);
    } catch (err) {
      console.error("Excel export error:", err);
    } finally {
      setExportingExcel(false);
    }
  }

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        // 200 is the backend's max (Query(..., le=200)) -- previously capped
        // at 50, which silently hid older runs with no way to page past them.
        const rows = await listPlanningRuns(200);
        setRuns(rows);
        // Deep-link a specific run via ?run=<id> (fixes the old /runs/{id}
        // 404 -- there's no dynamic route for it, this page reads the id
        // from a query param instead, same convention as /dashboard's ?run=).
        if (initialRunId) {
          setSelected(await getPlanningRun(initialRunId));
        } else if (rows[0]) {
          setSelected(await getPlanningRun(rows[0].id));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load runs");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [initialRunId]);

  // Client-side filtering. Search matches the resolved title -- this is the
  // only way to find a specific custom-profile run, since every one of
  // those shares the same `scenario` id ("custom") and is invisible to the
  // scenario dropdown above.
  const filteredRuns = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = runs.filter(r => {
      if (filterScenario && r.scenario !== filterScenario) return false;
      if (filterVerdict  && r.critic_verdict !== filterVerdict) return false;
      if (filterFrom && r.created_at && r.created_at < filterFrom) return false;
      if (filterTo   && r.created_at && r.created_at.slice(0, 10) > filterTo) return false;
      if (q && !scenarioTitle(r).toLowerCase().includes(q)) return false;
      return true;
    });
    // Runs already arrive newest-first from the API -- only re-sort when the
    // user flips to oldest-first.
    return sortDesc ? rows : [...rows].reverse();
  }, [runs, filterScenario, filterVerdict, filterFrom, filterTo, search, sortDesc]);

  function toggleCompare(id: number) {
    setCompareIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : prev.length < 2 ? [...prev, id] : [prev[1], id]
    );
  }

  async function openDiff() {
    if (compareIds.length !== 2) return;
    setDiffLoading(true);
    try {
      const [a, b] = await Promise.all([getPlanningRun(compareIds[0]), getPlanningRun(compareIds[1])]);
      setDiffRuns([a, b]);
    } finally {
      setDiffLoading(false);
    }
  }

  const selectEl = "rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-2.5 py-1.5 text-xs text-[var(--color-text-soft)] focus:outline-none focus:ring-1 focus:ring-ember-500/50";

  // ── Derived detail-panel content ──────────────────────────────────────────
  const critic = selected?.critic;
  const staleAssumptions = critic?.stale_assumptions ?? [];
  const costAnalysis = critic?.cost_analysis;

  return (
    <div className="space-y-5">
      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>
      )}

      {/* Main split */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">

        {/* Run list */}
        <section className="xl:col-span-4">
          <div className="card card-lift rounded-2xl p-4">
            <div className="flex items-center gap-3">
              <span
                className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-white shadow-sm"
                style={{ background: "linear-gradient(135deg, #FF5200, #FF5200cc)" }}
              >
                <ICONS.clock className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <h2 className="text-[18px] font-bold leading-tight text-[var(--color-text-primary)]">Run History</h2>
                <p className="mt-0.5 text-[12px] text-[var(--color-text-faint)]">Every AI planning session generated for your hospital.</p>
              </div>
            </div>

            {/* Search + filter toggle */}
            <div className="mt-4 flex items-center gap-2">
              <div className="relative flex-1 min-w-0">
                <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]" />
                <input
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search by scenario name..."
                  className="w-full rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] py-2 pl-9 pr-3 text-[13px] text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-ember-500/50"
                />
              </div>
              <button
                onClick={() => setFiltersOpen(v => !v)}
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg border transition-colors ${filtersOpen ? "border-ember-500/40 bg-ember-500/10 text-[var(--color-accent)]" : "border-[var(--color-border-default)] text-[var(--color-text-faint)] hover:text-[var(--color-text-primary)]"}`}
                title="Filters"
              >
                <FunnelIcon className="h-4 w-4" />
              </button>
            </div>

            {filtersOpen && (
              <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-[var(--color-surface-sunken)] p-2.5">
                <select value={filterScenario} onChange={e => setFilterScenario(e.target.value)} className={selectEl}>
                  {SCENARIOS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
                <select value={filterVerdict} onChange={e => setFilterVerdict(e.target.value)} className={selectEl}>
                  {VERDICTS.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                </select>
                <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-faint)]">
                  <span>from</span>
                  <input type="date" value={filterFrom} onChange={e => setFilterFrom(e.target.value)} className={selectEl + " w-32"} />
                  <span>to</span>
                  <input type="date" value={filterTo} onChange={e => setFilterTo(e.target.value)} className={selectEl + " w-32"} />
                </div>
                <button onClick={() => setShowChart(v => !v)} className="text-[11px] text-[var(--color-text-faint)] hover:text-[var(--color-text-primary)] underline">
                  {showChart ? "hide" : "show"} score trend
                </button>
                {(filterScenario || filterVerdict || filterFrom || filterTo || search) && (
                  <button onClick={() => { setFilterScenario(""); setFilterVerdict(""); setFilterFrom(""); setFilterTo(""); setSearch(""); }}
                    className="text-[11px] text-[var(--color-text-faint)] hover:text-[var(--color-text-primary)] underline">
                    clear all
                  </button>
                )}
              </div>
            )}

            {/* Trend chart */}
            {showChart && (
              <div className="mt-3 rounded-lg bg-[var(--color-surface-sunken)] p-3">
                <p className="mb-2 text-[10px] uppercase tracking-[0.16em] text-[var(--color-text-faint)]">
                  Critic Score Trend
                  <span className="ml-2 normal-case text-[var(--color-text-ghost)]">
                    <span className="text-emerald-400">●</span> approved
                    <span className="text-amber-400"> ●</span> revision
                    <span className="text-rose-400"> ●</span> rejected
                  </span>
                </p>
                <TrendChart runs={filteredRuns} />
              </div>
            )}

            {/* List */}
            <div className="mt-4 max-h-[640px] space-y-2.5 overflow-y-auto pr-0.5">
              {loading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="animate-pulse rounded-2xl bg-[var(--color-surface-sunken)] p-4 space-y-2.5">
                    <div className="h-2 w-10 rounded bg-[var(--color-border-soft)]" />
                    <div className="h-3.5 w-32 rounded bg-[var(--color-border-soft)]" />
                    <div className="h-2 w-24 rounded bg-[var(--color-border-soft)]" />
                  </div>
                ))
              ) : filteredRuns.length === 0 ? (
                <p className="px-1 py-6 text-sm text-[var(--color-text-faint)]">No runs match the current filters.</p>
              ) : (
                filteredRuns.map(run => {
                  const isActive   = selected?.id === run.id;
                  const isCompared = compareIds.includes(run.id);
                  const verdict    = run.critic_verdict ?? "unknown";
                  return (
                    <div
                      key={run.id}
                      onClick={() => getPlanningRun(run.id).then(setSelected)}
                      className={`cursor-pointer rounded-2xl p-4 shadow-sm ring-1 ring-[var(--color-border-soft)] transition-colors ${
                        isActive ? "bg-ember-500/[0.08]" : "bg-[var(--color-surface-raised)] hover:bg-[var(--color-surface-sunken)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 items-start gap-2.5">
                          <button
                            onClick={(e) => { e.stopPropagation(); toggleCompare(run.id); }}
                            className={`mt-0.5 grid h-[18px] w-[18px] shrink-0 place-items-center rounded-md border transition-colors ${
                              isCompared ? "border-[var(--color-accent)] bg-[var(--color-accent)] text-white" : "border-[var(--color-border-default)] hover:border-ember-500"
                            }`}
                            title="Select to compare"
                          >
                            {isCompared && <CheckCircleIcon className="h-3 w-3" strokeWidth={2.5} />}
                          </button>
                          <div className="min-w-0">
                            <p className="text-[10.5px] tabular-nums text-[var(--color-text-faint)]">#{run.id}</p>
                            <p className="mt-0.5 truncate text-[15px] font-bold text-[var(--color-text-primary)]">{scenarioTitle(run)}</p>
                            <p className="text-[11px] text-[var(--color-text-faint)]">{isCustomScenario(run.scenario) ? "Custom Scenario" : "Preset Scenario"}</p>
                          </div>
                        </div>
                        <ScoreRing value={run.critic_score ?? 0} size={52} thickness={4.5} />
                      </div>

                      <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-faint)]">
                        <CalendarIcon className="h-3.5 w-3.5" />
                        <span>Target {run.target_date ?? "-"}</span>
                      </div>

                      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                        <span className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${VERDICT_STYLE[verdict]}`}>
                          {verdict === "approved" ? "Approved" : verdict === "rejected" ? "Rejected" : verdict === "revision" ? "Revision" : "Unknown"}
                        </span>
                        <span className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${STATUS_STYLE[run.status] ?? STATUS_STYLE.unknown}`}>
                          {STATUS_LABEL[run.status] ?? run.status}
                        </span>
                      </div>

                      {run.risk_tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {run.risk_tags.map((tag, i) => (
                            <span key={i} className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-600 dark:text-violet-300">
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}

                      <p className="mt-2 text-right text-[10px] text-[var(--color-text-ghost)]">{relativeTime(run.created_at)}</p>
                    </div>
                  );
                })
              )}
            </div>

            {/* Footer */}
            <div className="mt-3 flex items-center justify-between text-[11px] text-[var(--color-text-faint)]">
              <span>{filteredRuns.length} of {runs.length} runs</span>
              <button onClick={() => setSortDesc(v => !v)} className="hover:text-[var(--color-text-primary)]">
                {sortDesc ? "Newest first" : "Oldest first"} ⌄
              </button>
            </div>

            {/* Compare panel */}
            <div className="mt-3 rounded-xl bg-[var(--color-surface-sunken)] p-3">
              <p className="text-[11.5px] text-[var(--color-text-soft)]">
                {compareIds.length === 2 ? "Ready to compare these two runs." : "Select two runs to compare their plans side by side."}
              </p>
              <div className="mt-2 flex items-center gap-2">
                <button
                  onClick={openDiff}
                  disabled={compareIds.length !== 2 || diffLoading}
                  className="flex-1 rounded-lg bg-ember-600 px-3 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-ember-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {diffLoading ? "Loading..." : `Compare Runs${compareIds.length > 0 ? ` (${compareIds.length}/2)` : ""}`}
                </button>
                {compareIds.length > 0 && (
                  <button onClick={() => setCompareIds([])} className="text-[11px] text-[var(--color-text-faint)] hover:text-[var(--color-text-primary)] underline">
                    clear
                  </button>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* Run detail */}
        <section className="space-y-5 xl:col-span-8">
          {!selected ? (
            <div className="card rounded-2xl px-5 py-12 flex flex-col items-center gap-3 text-center">
              <svg className="h-8 w-8 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p className="text-sm text-[var(--color-text-faint)]">Select a run from the list to see the full breakdown.</p>
              <p className="text-xs text-[var(--color-text-ghost)]">Critic verdict, quality scores, what each specialist found, and export buttons.</p>
            </div>
          ) : (
            <>
              {/* Header card */}
              <div className="card card-lift rounded-2xl p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-5">
                  <div className="min-w-0">
                    <h2 className="text-[26px] font-bold capitalize leading-tight text-[var(--color-text-primary)]">{scenarioTitle(selected)}</h2>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[13px] text-[var(--color-text-faint)]">
                      <CalendarIcon className="h-3.5 w-3.5" />
                      <span>Target {selected.target_date ?? "-"}</span>
                      <span>&middot;</span>
                      <span>Generated {selected.generated_at ? new Date(selected.generated_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "-"}</span>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] font-semibold ${VERDICT_STYLE[selected.critic_verdict ?? "unknown"]}`}>
                        {selected.critic_verdict === "approved" && <CheckCircleIcon className="h-3.5 w-3.5" strokeWidth={2.2} />}
                        {selected.critic_verdict === "approved" ? "Approved" : selected.critic_verdict === "rejected" ? "Rejected" : selected.critic_verdict === "revision" ? "Revision" : "Unknown"}
                      </span>
                      <span className={`rounded-full border px-3 py-1 text-[12.5px] font-semibold ${STATUS_STYLE[selected.status] ?? STATUS_STYLE.unknown}`}>
                        {STATUS_LABEL[selected.status] ?? selected.status}
                      </span>
                    </div>
                    {staleAssumptions.length > 0 && (
                      <div className="mt-2.5 flex items-center gap-1.5 text-[12px] text-amber-600 dark:text-amber-300">
                        <ICONS.warning className="h-3.5 w-3.5" />
                        <span>{staleAssumptions.length} cross-agent assumption conflict{staleAssumptions.length !== 1 ? "s" : ""} detected.</span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-5">
                    <div className="flex flex-col items-center">
                      <ScoreRing value={selected.critic_score ?? 0} size={104} thickness={9} />
                      <p className="mt-1.5 text-center text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">AI Critic Score</p>
                    </div>
                    <div className="flex w-44 flex-col gap-2">
                      <Link
                        href={`/planning?run=${selected.id}`}
                        className="flex items-center justify-center gap-1.5 rounded-lg bg-ember-600 px-3 py-2 text-[12.5px] font-semibold text-white transition-colors hover:bg-ember-500"
                      >
                        View Full Plan
                      </Link>
                      <button
                        onClick={() => toggleCompare(selected.id)}
                        className="flex items-center justify-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3 py-2 text-[12.5px] text-[var(--color-text-soft)] transition-colors hover:text-[var(--color-text-primary)]"
                      >
                        <ScaleIcon className="h-3.5 w-3.5" />
                        {compareIds.includes(selected.id) ? "Selected to compare" : "Compare Run"}
                      </button>
                      <button
                        onClick={() => downloadPdf(selected.id, selected.scenario)}
                        disabled={exportingPdf}
                        className="flex items-center justify-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3 py-2 text-[12.5px] text-[var(--color-text-soft)] transition-colors hover:text-[var(--color-text-primary)] disabled:opacity-50"
                      >
                        <ExportIcon className="h-3.5 w-3.5" />
                        {exportingPdf ? "Exporting..." : "Export PDF"}
                      </button>
                      <button
                        onClick={() => downloadExcel(selected.id, selected.scenario)}
                        disabled={exportingExcel}
                        className="flex items-center justify-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3 py-2 text-[12.5px] text-[var(--color-text-soft)] transition-colors hover:text-[var(--color-text-primary)] disabled:opacity-50"
                      >
                        <ExportIcon className="h-3.5 w-3.5" />
                        {exportingExcel ? "Exporting..." : "Export Excel"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Cost & Tradeoffs -- AI Findings, Dimension Scores, and an
                  "Evidence Used" chip summary were all deliberately dropped
                  from this view: the first two exactly duplicate what "View
                  Full Plan" already renders (AgentIntelligencePanel and
                  CriticBanner), and the chip summary duplicated the richer
                  EvidencePanel just below with less real detail. Cost &
                  Tradeoffs stays because cost_analysis isn't rendered
                  anywhere else in the app right now. */}
              <div className="card card-lift rounded-2xl p-5 md:p-6">
                <div className="mb-1 flex items-center gap-3">
                  <span
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white shadow-sm"
                    style={{ background: "linear-gradient(135deg, #C2410C, #C2410Ccc)" }}
                  >
                    <ICONS.trendUp className="h-4 w-4" />
                  </span>
                  <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Cost &amp; Tradeoffs</h3>
                </div>

                {costAnalysis ? (
                    <>
                      <div className="mt-4 grid grid-cols-3 gap-2">
                        <div className="flex flex-col items-center text-center">
                          <ScoreRing value={costAnalysis.cost_pressure_score} size={76} thickness={6} />
                          <p className="mt-2 text-[10.5px] font-semibold text-[var(--color-text-primary)]">Cost Pressure</p>
                          <p className="mt-0.5 text-[10px] leading-snug text-[var(--color-text-faint)]">{costPressureCaption(costAnalysis.cost_pressure_score)}</p>
                        </div>
                        <div className="flex flex-col items-center text-center">
                          <ScoreRing value={costAnalysis.benefit_score} size={76} thickness={6} />
                          <p className="mt-2 text-[10.5px] font-semibold text-[var(--color-text-primary)]">Expected Benefit</p>
                          <p className="mt-0.5 text-[10px] leading-snug text-[var(--color-text-faint)]">{benefitCaption(costAnalysis.benefit_score)}</p>
                        </div>
                        <div className="flex flex-col items-center text-center">
                          <ScoreRing value={costAnalysis.tradeoff_score} size={76} thickness={6} color={costAnalysis.tradeoff_score >= 0.5 ? "#10B981" : costAnalysis.tradeoff_score >= 0.3 ? "#F59E0B" : "#F43F5E"} />
                          <p className="mt-2 text-[10.5px] font-semibold text-[var(--color-text-primary)]">Operational Tradeoff</p>
                          <p className="mt-0.5 text-[10px] leading-snug text-[var(--color-text-faint)]">{tradeoffCaption(costAnalysis.tradeoff_score)}</p>
                        </div>
                      </div>

                      {costAnalysis.recommended_focus && costAnalysis.recommended_focus.length > 0 && (
                        <div className="mt-4 flex items-start gap-2 rounded-xl bg-ember-500/[0.06] p-3.5">
                          <ICONS.lightbulb className="h-4 w-4 shrink-0 text-[var(--color-accent)]" />
                          <div className="space-y-1">
                            {costAnalysis.recommended_focus.map((line, i) => (
                              <p key={i} className="text-[12px] leading-relaxed text-[var(--color-text-soft)]">{line}</p>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                ) : (
                  <p className="mt-3 text-[12.5px] italic text-[var(--color-text-ghost)]">No cost-aware scoring recorded for this run.</p>
                )}
              </div>

              {selected.final_response && <EvidencePanel data={selected.final_response} />}

              {/* Footer observability strip */}
              <div className="card rounded-2xl p-4">
                <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                  <FooterStat icon={<ICONS.clock className="h-4 w-4" />} label="Run Duration" value={fmtMs(selected.total_duration_ms)} />
                  <FooterStat icon={<ICONS.cube className="h-4 w-4" />} label="LLM Calls" value={selected.llm_call_count != null ? String(selected.llm_call_count) : "--"} />
                  <FooterStat icon={<ICONS.tag className="h-4 w-4" />} label="Total Tokens" value={selected.total_tokens != null ? selected.total_tokens.toLocaleString() : "--"} />
                  <FooterStat icon={<ICONS.gauge className="h-4 w-4" />} label="Critic Revisions" value={selected.replan_count != null ? String(selected.replan_count) : "--"} />
                  <FooterStat icon={<CalendarIcon className="h-4 w-4" />} label="Generated At" value={selected.generated_at ? new Date(selected.generated_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "-"} />
                </div>
              </div>
            </>
          )}
        </section>
      </div>

      {/* Diff modal */}
      {diffRuns && (
        <DiffModal runA={diffRuns[0]} runB={diffRuns[1]} onClose={() => setDiffRuns(null)} />
      )}
    </div>
  );
}

function FooterStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-ember-500/10 text-[var(--color-accent)]">{icon}</span>
      <div>
        <p className="text-[9.5px] uppercase tracking-wider text-[var(--color-text-faint)]">{label}</p>
        <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">{value}</p>
      </div>
    </div>
  );
}

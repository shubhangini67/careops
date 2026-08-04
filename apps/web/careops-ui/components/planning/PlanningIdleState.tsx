"use client";

import { useEffect, useState } from "react";
import PlanShiftModal from "@/components/dashboard/PlanShiftModal";
import AgentPipelineGrid from "@/components/planning/AgentPipelineGrid";
import { AGENT_TONE_CLASS } from "@/components/planning/agentPipeline";
import { usePlanTriggerData } from "@/hooks/usePlanTriggerData";
import { useScenarioRecommendation } from "@/hooks/useScenarioRecommendation";
import { getPlanningRun } from "@/lib/api";
import { downloadRunPdf } from "@/lib/exportRun";
import { relativeTime, shortDate, VERDICT_TONE } from "@/lib/formatters";
import { SCENARIO_OPTIONS } from "@/lib/scenarios";
import { PlanningRunMetadata, PlanningScenarioOption, PlanTriggerHandler, RunHistoryEntry } from "@/types/planning";

interface Props {
  onRun: PlanTriggerHandler;
  selectedScenario: PlanningScenarioOption["id"];
  history: RunHistoryEntry[];
  onSelectHistory: (entry: RunHistoryEntry) => void;
  onShowAllHistory: () => void;
}

const WEATHER_LABEL: Record<string, string> = {
  heavy_rain: "Heavy rain expected",
  light_rain: "Light rain expected",
  very_hot: "Very hot conditions",
  clear: "Clear conditions",
};

// Shared with the loading-skeleton rows below, so the placeholder and the
// real row for the same signal always show the same icon -- no shape change
// once the data actually arrives.
const CONTEXT_ICON = {
  weather: "M17.5 19H6a4 4 0 01-1-7.87A5.5 5.5 0 0116 8.5a4.5 4.5 0 011.5 10.5z",
  occupancy: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
  trends: "M2.25 18L9 11.25l4.306 4.306a11.95 11.95 0 015.814-5.518l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941",
  compliance: "M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z",
} as const;

const GRADIENT = {
  purple: "linear-gradient(135deg,#c4b5fd,#7c3aed)",
  orange: "linear-gradient(135deg,#fdba74,#ea580c)",
} as const;

const LIVE_BORDER_STYLE = (
  <style jsx global>{`
    @keyframes contextBorderSweep {
      0% { background-position: 0% 50%; }
      100% { background-position: 200% 50%; }
    }
  `}</style>
);

const SCENARIO_ICON: Record<string, { gradient: string; iconPath: string }> = {
  ed_surge: { gradient: GRADIENT.orange, iconPath: "M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" },
  opd_peak: { gradient: GRADIENT.orange, iconPath: "M12 3v1.5M12 19.5V21M4.219 4.219l1.061 1.06M18.72 18.72l1.06 1.06M3 12h1.5M19.5 12H21M4.219 19.781l1.061-1.06M18.72 5.28l1.06-1.06M16.5 12a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" },
  icu_capacity: { gradient: GRADIENT.purple, iconPath: "M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" },
  supply_shortage: { gradient: GRADIENT.orange, iconPath: "M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" },
};
const DEFAULT_SCENARIO_ICON = { gradient: GRADIENT.orange, iconPath: "M13 10V3L4 14h7v7l9-11h-7z" };

// Rotates while LiveScenarioComposer is still thinking -- names the actual
// signals it's weighing (real behavior, not filler) instead of one static
// "loading…" line, so the wait reads as work happening, not a stall.
const COMPOSING_MESSAGES = [
  "Checking admission forecasts…",
  "Reading supply shortage alerts…",
  "Reviewing bed utilization…",
  "Scanning regulatory notices…",
  "Weighing your recent runs…",
];

const MARKET_LOADING_MESSAGES = [
  "Checking weather impact…",
  "Reading capacity signals…",
  "Scanning healthcare headlines…",
  "Checking regulatory notices…",
];

// Stat tile, not a list row -- a 2x2 grid of these reads as live telemetry
// at a glance, caps the card's height regardless of how many signals fire on
// a given day, and matches the "AI workspace" feel elsewhere on this page
// better than a plain notification-style list did.
function ContextTile({ hue, iconPath, text, badge }: { hue: string; iconPath: string; text: string; badge?: number }) {
  return (
    <div className="relative flex flex-col items-center gap-1.5 rounded-xl p-2.5 text-center" style={{ background: "var(--color-surface-raised)" }}>
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full" style={{ background: `${hue}1F`, color: hue }}>
        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d={iconPath} /></svg>
      </span>
      <p className="line-clamp-2 text-[11px] font-bold leading-tight text-[var(--color-text-primary)]">{text}</p>
      {badge != null && (
        <span className="absolute -right-1 -top-1 grid h-4.5 min-w-[18px] shrink-0 place-items-center rounded-full px-1 text-[9px] font-bold text-white" style={{ background: hue }}>{badge}</span>
      )}
    </div>
  );
}

const DELIVERABLES: { label: string; iconPath: string; tone: keyof typeof AGENT_TONE_CLASS }[] = [
  { label: "Executive Brief",  tone: "purple", iconPath: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" },
  { label: "PDF Export",       tone: "amber",  iconPath: "M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" },
  { label: "Customer Experience", tone: "info", iconPath: "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" },
  { label: "Risk Assessment",  tone: "rose",   iconPath: "M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" },
  { label: "Action Queue",     tone: "good",   iconPath: "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" },
];

// Aligned visually with the agent cards (same icon-badge language, muted
// tone palette) but deliberately not repeating what those cards already say
// -- Demand Forecast/Inventory/Menu Strategy are agent names already shown
// above, so this only lists the *other* things a run produces: the brief,
// a real PDF export (downloadRunPdf, already live on every run card),
// guest-facing notes, risk flags, and the action queue. No "Staffing Plan"
// -- no node actually produces a structured staffing recommendation, only a
// one-line note folded into the forecast's own text (see agentPipeline.ts).
function DeliverablesCard() {
  return (
    <div
      className="card p-3"
      style={{
        borderWidth: "1.5px",
        background: "linear-gradient(160deg, rgba(56,132,255,0.07) 0%, var(--color-surface-raised) 70%)",
      }}
    >
      <p className="text-[11.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-primary)]">Walk Away With More.</p>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        {DELIVERABLES.map(({ label }, i) => {
          const isLast = i === DELIVERABLES.length - 1 && DELIVERABLES.length % 2 === 1;
          return (
            <div
              key={label}
              className={`flex items-center justify-center rounded-lg border p-1.5 text-center transition-transform duration-150 hover:-translate-y-0.5 hover:shadow-sm ${isLast ? "col-span-2" : ""}`}
              style={{ background: "rgba(56,132,255,0.08)", borderColor: "rgba(56,132,255,0.18)" }}
            >
              <span className="text-[11px] font-semibold leading-tight text-[var(--color-text-primary)]">{label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Compact horizontal row (not a card) -- several fit in one line, matching
// how little space a "recent activity" glance actually deserves next to the
// agent showcase above it.
function RunCard({ entry, onSelect, onExport }: { entry: RunHistoryEntry; onSelect: () => void; onExport: () => void }) {
  const opt = SCENARIO_OPTIONS.find((s) => s.id === entry.scenario);
  const icon = SCENARIO_ICON[entry.scenario] ?? DEFAULT_SCENARIO_ICON;
  const tone = VERDICT_TONE[entry.verdict ?? "unknown"] ?? VERDICT_TONE.unknown;
  return (
    <button type="button" onClick={onSelect} className="card flex min-w-[220px] flex-1 items-center gap-3 p-3 text-left">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-white" style={{ background: icon.gradient }}>
        <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d={icon.iconPath} /></svg>
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-[13.5px] font-bold text-[var(--color-text-primary)]">{entry.scenarioLabel || opt?.label || entry.scenario}</p>
          <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[9.5px] font-bold uppercase" style={{ background: tone.bg, color: tone.text }}>{tone.label}</span>
        </div>
        <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">{shortDate(entry.runAt)} · {relativeTime(entry.runAt)}</p>
      </div>
      <span
        onClick={(e) => { e.stopPropagation(); onExport(); }}
        role="button"
        title="Export PDF"
        className="shrink-0 rounded-md p-1.5 text-[var(--color-text-faint)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-accent)]"
      >
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" /></svg>
      </span>
      <svg className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
    </button>
  );
}

function ViewHistoryCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-w-[160px] items-center gap-2 rounded-xl border px-3.5 py-3 text-left transition-colors"
      style={{ borderColor: "rgba(252,128,25,0.25)", background: "rgba(252,128,25,0.04)" }}
    >
      <p className="text-[13.5px] font-bold" style={{ color: "var(--color-accent)" }}>View all runs</p>
      <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="var(--color-accent)" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
    </button>
  );
}

// The idle state for the flagship /planning page: a compact control panel
// (trigger card + live-signals card + a fun-fact card) beside the agent
// showcase (flow strip + 3x3 specialist grid), then a compact recent-runs
// row underneath. "Run a plan" opens PlanShiftModal -- the same run-today /
// choose-a-scenario / describe-it-yourself flow Dashboard's quick-trigger
// uses -- rather than expanding an inline chooser on this page.
export default function PlanningIdleState({
  onRun, selectedScenario, history, onSelectHistory, onShowAllHistory,
}: Props) {
  const { activeProfile, marketPulse, marketLoaded, marketRefreshing, refreshMarketPulse } = usePlanTriggerData();
  const scenario = SCENARIO_OPTIONS.find((s) => s.id === selectedScenario) ?? SCENARIO_OPTIONS[0];
  const [modalOpen, setModalOpen] = useState(false);

  // "Run today's plan" no longer just reuses whatever scenario was last
  // manually selected -- ScenarioRecommender (already built server-side,
  // never previously called from the frontend) picks the shift shape that
  // actually fits today: holiday -> Holiday Spike, 3+ shortages -> Low-Stock
  // Weekend, weekend -> dinner-rush pattern, weekday -> Weekday Lunch. Fetched
  // once on mount so the hero caption reflects the real pick before the user
  // even clicks, not just at click time.
  const { composition, loaded: compositionLoaded } = useScenarioRecommendation();

  // Cycles COMPOSING_MESSAGES while waiting, so the loading state feels like
  // active work rather than a stuck spinner.
  const [composingMessageIndex, setComposingMessageIndex] = useState(0);
  useEffect(() => {
    if (compositionLoaded) return;
    const interval = setInterval(() => {
      setComposingMessageIndex((i) => (i + 1) % COMPOSING_MESSAGES.length);
    }, 1600);
    return () => clearInterval(interval);
  }, [compositionLoaded]);

  // Same idea for the Today's Context card's /market/pulse fetch.
  const [marketMessageIndex, setMarketMessageIndex] = useState(0);
  useEffect(() => {
    if (marketLoaded) return;
    const interval = setInterval(() => {
      setMarketMessageIndex((i) => (i + 1) % MARKET_LOADING_MESSAGES.length);
    }, 1600);
    return () => clearInterval(interval);
  }, [marketLoaded]);

  // Honest expectation-setter -- averaged from the last few real runs
  // (duration_ms from each run's stored metadata), not a fabricated pre-run
  // guess. A bounded fan-out (at most 5 detail fetches, once) rather than
  // one call per historical run.
  const [estimateSeconds, setEstimateSeconds] = useState<number | null>(null);
  useEffect(() => {
    if (history.length === 0) return;
    let cancelled = false;
    Promise.all(history.slice(0, 5).map((h) => getPlanningRun(Number(h.id)).catch(() => null)))
      .then((details) => {
        if (cancelled) return;
        const durations: number[] = [];
        for (const d of details) {
          const meta = d?.metadata as PlanningRunMetadata | undefined;
          if (typeof meta?.total_duration_ms === "number") durations.push(meta.total_duration_ms);
        }
        if (durations.length > 0) {
          setEstimateSeconds(Math.round(durations.reduce((a, b) => a + b, 0) / durations.length / 1000));
        }
      });
    return () => { cancelled = true; };
  }, [history]);

  async function handleExportRow(entry: RunHistoryEntry) {
    try { await downloadRunPdf(Number(entry.id), entry.scenario); } catch { /* best-effort */ }
  }

  return (
    <>
      {LIVE_BORDER_STYLE}
      <div className="space-y-8 py-6">
      {/* ═══ Side by side: a compact control panel (trigger + live signals +
          how-to-plan) next to the agent showcase -- both visible in one
          viewport. The left panel triggers a run, the right side sells the
          team. ═══ */}
      <div className="flex flex-col gap-6 xl:grid xl:grid-cols-[340px_1fr] xl:items-stretch">
        {/* ── Left: control panel -- one real grid track (340px, not a
            flex-basis floating free of the right column's own layout), so
            the two sides read as one coherent grid instead of two
            independently-sized blocks. items-stretch on the row makes this
            column match the right column's actual rendered height, and
            justify-between spreads the extra space as breathing room
            between the 3 cards (on top of the gap-4 minimum) instead of
            manually guessing paddings until the heights happen to match. ── */}
        <div className="flex w-full flex-col gap-4 xl:justify-between">
          <div
            className="relative overflow-hidden rounded-2xl bg-cover bg-[center_30%] p-3.5 shadow-[0_20px_44px_-16px_rgba(196,110,27,0.5)]"
            style={{
              backgroundImage:
                "linear-gradient(180deg, rgba(20,12,8,0.12) 0%, rgba(20,12,8,0.18) 60%, rgba(15,9,6,0.55) 100%), url(/planning-hero.png)",
            }}
          >
            <p className="relative text-[11.5px] font-bold uppercase tracking-[0.14em] text-white">From Signals to Operations.</p>
            <button
              type="button"
              onClick={() => setModalOpen(true)}
              className="relative mt-3 flex w-full items-center justify-center gap-2 rounded-full px-4 py-2.5 text-[14.5px] font-bold text-white transition-transform hover:scale-[1.02]"
              style={{
                background: "linear-gradient(180deg, #f0a648 0%, #de7e1d 100%)",
                boxShadow: "0 0 0 1px rgba(255,255,255,0.25), 0 10px 24px -6px rgba(0,0,0,0.45), 0 0 26px rgba(255,180,90,0.5)",
              }}
            >
              <span className="grid h-5 w-5 place-items-center rounded-full bg-white/25">
                <svg className="h-2.5 w-2.5" fill="white" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
              </span>
              Run a plan
            </button>
            <div className="relative mt-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12px] font-semibold text-white/90">
              <span className="inline-flex items-center gap-1">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><circle cx="12" cy="12" r="9" /><path strokeLinecap="round" d="M12 7v5l3 3" /></svg>
                ~{estimateSeconds ?? 20}s
              </span>
              <span className="text-white/40">•</span>
              {!compositionLoaded ? (
                <span className="inline-flex items-center gap-1.5 font-medium text-white/80">
                  <span className="flex gap-0.5">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white/70" style={{ animationDelay: "0ms" }} />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white/70" style={{ animationDelay: "150ms" }} />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white/70" style={{ animationDelay: "300ms" }} />
                  </span>
                  {COMPOSING_MESSAGES[composingMessageIndex]}
                </span>
              ) : (
                <span>{composition?.profile.label ?? scenario.label}</span>
              )}
              <span className="text-white/40">•</span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-white" />
                {activeProfile?.name ?? "Your hospital"}
              </span>
            </div>
          </div>

          <div
            className="rounded-2xl p-[1px]"
            style={{
              background: "linear-gradient(90deg, rgba(56,132,255,0.15), rgba(249,115,22,0.55), rgba(56,132,255,0.15))",
              backgroundSize: "200% 100%",
              animation: "contextBorderSweep 2.2s linear infinite",
            }}
          >
            <div
              className="rounded-[15px] border p-4"
              style={{ borderColor: "var(--context-card-border)", background: "var(--context-card-gradient)" }}
            >
            <div className="flex items-center justify-between">
              <p className="text-[11.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-primary)]">Today&apos;s context</p>
              <button
                type="button"
                onClick={refreshMarketPulse}
                disabled={marketRefreshing}
                className="flex items-center gap-1 text-[10.5px] font-semibold text-[var(--color-text-faint)] transition hover:text-[var(--color-text-primary)] disabled:opacity-60"
              >
                <svg className={`h-3 w-3 ${marketRefreshing ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                {marketRefreshing ? "Refreshing…" : "Refresh"}
              </button>
            </div>
            <div className="mt-2.5 min-h-[136px]">
              {!marketLoaded ? (
                <div className="flex h-full min-h-[136px] flex-col items-center justify-center gap-2 py-4">
                  <svg className="h-6 w-6 animate-spin" style={{ color: "var(--color-accent)" }} fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-[12px] font-semibold text-[var(--color-text-soft)]">{MARKET_LOADING_MESSAGES[marketMessageIndex]}</span>
                </div>
              ) : !marketPulse?.weather && !marketPulse?.area_occupancy?.signal ? (
                <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">Nothing unusual today.</p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {marketPulse?.weather && (
                    <ContextTile hue="#38bdf8" iconPath={CONTEXT_ICON.weather} text={WEATHER_LABEL[marketPulse.weather.condition] ?? marketPulse.weather.signal} />
                  )}
                  {marketPulse?.area_occupancy?.signal && (
                    <ContextTile hue="#38bdf8" iconPath={CONTEXT_ICON.occupancy} text={`Bed pressure ${marketPulse.area_occupancy.signal.toLowerCase()}`} />
                  )}
                  {marketPulse?.industry_trends && marketPulse.industry_trends.headline_count > 0 && (
                    <ContextTile hue="#fbbf24" iconPath={CONTEXT_ICON.trends} text="Industry trends noted" />
                  )}
                  {!!marketPulse?.compliance_alerts?.notice_count && (
                    <ContextTile
                      hue="#f97316"
                      iconPath={CONTEXT_ICON.compliance}
                      text="Regulatory notices"
                      badge={marketPulse.compliance_alerts.notice_count}
                    />
                  )}
                </div>
              )}
            </div>
            </div>
          </div>

          <DeliverablesCard />
        </div>

        {/* ── Right: the specialist showcase -- 9 AI agent cards, 3 per row. ── */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[28px] font-bold leading-tight text-[var(--color-text-primary)]">
                Your{" "}
                <span style={{ color: "var(--color-accent)" }}>
                  Smartest Handoff
                </span>{" "}
                Starts Here.
              </p>
              <p className="mt-1 max-w-[520px] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
                Seven AI specialists analyze capacity, FHIR data, hospital policies, and supply levels before delivering one safety-reviewed plan.
              </p>
            </div>
            <span className="mt-1 inline-flex shrink-0 items-center gap-1 text-[12px] font-semibold" style={{ color: "var(--color-accent)" }}>
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              Learn how it works
            </span>
          </div>
          <div className="mt-4">
            <AgentPipelineGrid columns={3} />
          </div>
        </div>
      </div>

      {/* ═══ Recent planning runs ═══ */}
      {history.length > 0 && (
        <div>
          <div>
            <p className="text-[16.5px] font-bold text-[var(--color-text-primary)]">Recent planning runs</p>
            <p className="mt-0.5 text-[13px] text-[var(--color-text-faint)]">A glimpse of your recent runs</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-3">
            {history.slice(0, 3).map((entry) => (
              <RunCard key={entry.id} entry={entry} onSelect={() => onSelectHistory(entry)} onExport={() => handleExportRow(entry)} />
            ))}
            <ViewHistoryCard onClick={onShowAllHistory} />
          </div>
        </div>
      )}

      <PlanShiftModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onRun={onRun}
        activeProfile={activeProfile}
      />
      </div>
    </>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FridayRushResponse } from "@/types/planning";

function asObject(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

const VERDICT_LABEL: Record<string, string> = {
  approved: "Plan Approved", rejected: "Plan Blocked", revision: "Needs Review", unknown: "Verdict Pending",
};
// text-*-300 alone reads fine on a dark card but is nearly invisible on the
// light/cream page background these badges actually sit on -- same
// light/dark-safe pattern already used by AgentIntelligencePanel's
// PRIORITY_CLASS (darker shade in light mode, pastel in dark mode).
const VERDICT_TONE: Record<string, string> = {
  approved: "text-emerald-600 dark:text-emerald-300 ring-emerald-400/30 bg-emerald-500/10",
  rejected: "text-rose-600 dark:text-rose-300 ring-rose-400/30 bg-rose-500/10",
  revision: "text-[var(--color-accent)] ring-ember-400/30 bg-ember-500/10",
  unknown:  "text-[var(--color-text-soft)] ring-[var(--color-border-default)] bg-[var(--color-surface-raised)]",
};

interface Props {
  data: FridayRushResponse;
  onExportPdf: () => void;
  onExportExcel: () => void;
  exportingPdf: boolean;
  exportingExcel: boolean;
  onWhatIf: () => void;
  onRerun: () => void;
}

export default function PlanHeader({ data, onExportPdf, onExportExcel, exportingPdf, exportingExcel, onWhatIf, onRerun }: Props) {
  const router = useRouter();
  const [exportOpen, setExportOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) setExportOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function handleCopyLink() {
    const runId = data.meta?.planning_run_id;
    const url = runId ? `${window.location.origin}/planning?run=${runId}` : window.location.href;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {});
  }

  const scenarioProfile = asObject(data.meta?.scenario_profile);
  const label = (scenarioProfile?.label as string | undefined) ?? data.scenario?.replace(/_/g, " ") ?? "Run";
  const serviceWindow = scenarioProfile?.service_window as string | undefined;
  const critic = data.critic;

  const formattedTime = (() => {
    try { return new Date(data.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
    catch { return "--:--"; }
  })();

  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        {/* Same masthead pattern as PageHeading.tsx (Market/Analytics/Action
            Center) -- bold title + short accent underline, no eyebrow pill
            -- so this reads as one consistent system with the rest of the
            app instead of its own bespoke treatment. */}
        <h1 className="text-[28px] font-bold text-[var(--color-text-primary)] capitalize">{label}</h1>
        <div className="mt-2 h-1 w-12 rounded-full" style={{ background: "var(--color-accent)" }} />
        <p className="mt-3 text-[13px] text-[var(--color-text-faint)]">
          {data.target_date}
          {serviceWindow && <> &middot; {serviceWindow}</>}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ${VERDICT_TONE[critic.verdict] ?? VERDICT_TONE.unknown}`}>
            {VERDICT_LABEL[critic.verdict] ?? "Verdict Pending"}
          </span>
          <span className="text-[11px] text-[var(--color-text-faint)]">Generated {formattedTime}</span>
        </div>
      </div>

      <div className="flex flex-col items-end gap-3">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="relative" ref={exportRef}>
            <button
              onClick={() => setExportOpen((v) => !v)}
              disabled={exportingPdf || exportingExcel}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-[var(--color-text-soft)] ring-1 ring-[var(--color-border-default)] transition-colors hover:text-[var(--color-text-primary)] disabled:opacity-40"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
              </svg>
              {exportingPdf ? "Exporting PDF…" : exportingExcel ? "Exporting Excel…" : "Export"}
              <svg className="h-3 w-3 text-[var(--color-text-faint)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {exportOpen && (
              <div className="absolute right-0 top-full mt-1.5 w-44 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-1.5 shadow-xl z-50">
                <button onClick={() => { onExportPdf(); setExportOpen(false); }} className="flex w-full items-center gap-2.5 px-3 py-2 text-xs text-[var(--color-text-soft)] hover:bg-[var(--color-surface-raised)] hover:text-[var(--color-text-primary)] transition-colors">
                  <svg className="h-3.5 w-3.5 text-rose-300/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  Chef brief — PDF
                </button>
                <button onClick={() => { onExportExcel(); setExportOpen(false); }} className="flex w-full items-center gap-2.5 px-3 py-2 text-xs text-[var(--color-text-soft)] hover:bg-[var(--color-surface-raised)] hover:text-[var(--color-text-primary)] transition-colors">
                  <svg className="h-3.5 w-3.5 text-emerald-300/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Owner workbook — Excel
                </button>
              </div>
            )}
          </div>

          <button
            onClick={handleCopyLink}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-[var(--color-text-soft)] ring-1 ring-[var(--color-border-default)] transition-colors hover:text-[var(--color-text-primary)]"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342a4.5 4.5 0 100-2.684m0 2.684a4.5 4.5 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a4.5 4.5 0 108.632-2.684 4.5 4.5 0 00-8.632 2.684zm0 9.316a4.5 4.5 0 108.632 2.684 4.5 4.5 0 00-8.632-2.684z" />
            </svg>
            {copied ? "Copied!" : "Share"}
          </button>

          <button
            onClick={() => router.push("/chat")}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-[var(--color-text-soft)] ring-1 ring-[var(--color-border-default)] transition-colors hover:text-[var(--color-text-primary)]"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            Ask the AI
          </button>

          <button
            onClick={onWhatIf}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-[var(--color-text-soft)] ring-1 ring-[var(--color-border-default)] transition-colors hover:text-[var(--color-text-primary)]"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            What-if
          </button>

          <button
            onClick={onRerun}
            className="btn-primary inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-xs font-semibold"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Re-run plan
          </button>
        </div>

        {/* Glowing score ring -- the at-a-glance version; the full "Critic
            Review" section further down the page (CriticBanner.tsx) is the
            same score with the dimension-level detail behind it. */}
        <ScoreRing score={critic.score} />
      </div>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const circumference = 2 * Math.PI * 20;
  const dashOffset = circumference * (1 - score);

  return (
    <div className="flex items-center gap-2">
      <div className="relative h-11 w-11 shrink-0">
        <svg className="h-11 w-11 -rotate-90" viewBox="0 0 44 44">
          <circle cx="22" cy="22" r="20" fill="none" stroke="var(--color-border-soft)" strokeWidth="3.5" />
          <circle
            cx="22" cy="22" r="20" fill="none" stroke="var(--color-accent)" strokeWidth="3.5" strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={dashOffset}
            style={{ filter: "drop-shadow(0 0 4px rgba(255,82,0,0.4))" }}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <span className="text-[11px] font-bold text-[var(--color-text-primary)]">{pct}</span>
        </div>
      </div>
      <span className="text-[10px] text-[var(--color-text-faint)]">/100</span>
    </div>
  );
}

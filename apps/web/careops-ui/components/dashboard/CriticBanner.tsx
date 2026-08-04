"use client";

import { useState } from "react";
import { CriticResult } from "@/types/planning";

const VERDICT_CONFIG: Record<string, { color: string; ring: string; bg: string }> = {
  approved: { color: "text-emerald-500", ring: "ring-emerald-400/30", bg: "bg-emerald-500/[0.08]" },
  rejected: { color: "text-rose-500",    ring: "ring-rose-400/30",    bg: "bg-rose-500/[0.08]" },
  revision: { color: "text-[var(--color-accent)]", ring: "ring-ember-400/30", bg: "bg-ember-500/[0.08]" },
  unknown:  { color: "text-[var(--color-text-soft)]", ring: "ring-[var(--color-border-default)]", bg: "bg-[var(--color-surface-raised)]" },
};

const VERDICT_LABEL: Record<string, string> = {
  approved: "Plan Approved", rejected: "Plan Blocked", revision: "Needs Review", unknown: "Verdict Pending",
};

const DIMENSIONS = ["safety", "feasibility", "evidence", "actionability", "clarity"] as const;
const DIMENSION_LABEL: Record<string, string> = {
  safety: "Safety", feasibility: "Feasibility", evidence: "Evidence", actionability: "Actionability", clarity: "Clarity",
};

interface Props {
  critic: CriticResult;
}

// Section 7, "Critic Review" -- the capstone of the evidence trail (Situation
// -> Drivers -> Strategy -> Actions -> Evidence -> Conversation). Full-size
// again after an earlier demotion: that demotion was about *position*
// (it was competing with the hero right after PlanBriefing), not size --
// now that it sits at the end, after all agent detail, giving it real
// presence is correct: it's the last piece of trust-establishing evidence
// before a manager acts on the plan.
export default function CriticBanner({ critic }: Props) {
  const [notesExpanded, setNotesExpanded] = useState(false);
  const config = VERDICT_CONFIG[critic.verdict] ?? VERDICT_CONFIG.unknown;
  const scorePct = Math.round(critic.score * 100);
  const conflictCount = critic.revision_reasons?.length ?? 0;

  const dims = critic.dimension_scores ?? {};
  const bars = DIMENSIONS.map((dim) => ({
    label: DIMENSION_LABEL[dim],
    pct: Math.round((typeof dims[dim] === "number" ? dims[dim] : 0) * 100),
  }));

  const circumference = 2 * Math.PI * 42;
  const dashOffset = circumference * (1 - critic.score);

  return (
    <div className="@container card card-lift rounded-3xl p-6 sm:p-7">
      <div className="flex items-center gap-1.5">
        <svg className="h-3.5 w-3.5 shrink-0 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 4.556-3.03 8.4-7.183 9.65a1.5 1.5 0 01-.634 0C8.03 20.4 5 16.556 5 12V6a1 1 0 01.594-.914l6-2.65a1 1 0 01.812 0l6 2.65A1 1 0 0121 6v6z" />
        </svg>
        <p className="text-[10.5px] font-bold uppercase tracking-[0.18em] text-[var(--color-accent)]">Critic review</p>
      </div>
      <p className="mt-1 text-[19px] font-bold text-[var(--color-text-primary)]">Why the critic scored this plan the way it did</p>

      <div className="mt-5 grid grid-cols-1 gap-6 @2xl:grid-cols-[auto_1fr]">
        {/* Score ring + verdict */}
        <div className="flex items-center gap-5">
          <div className="relative h-24 w-24 shrink-0">
            <svg className="h-24 w-24 -rotate-90" viewBox="0 0 96 96">
              <circle cx="48" cy="48" r="42" fill="none" stroke="var(--color-border-soft)" strokeWidth="6" />
              <circle
                cx="48" cy="48" r="42" fill="none" stroke="var(--color-accent)" strokeWidth="6" strokeLinecap="round"
                strokeDasharray={circumference} strokeDashoffset={dashOffset}
                style={{ filter: "drop-shadow(0 0 6px rgba(255,82,0,0.35))", transition: "stroke-dashoffset 0.6s ease-out" }}
              />
            </svg>
            <div className="absolute inset-0 grid place-items-center">
              <div className="text-center">
                <p className="text-[22px] font-bold leading-none text-[var(--color-text-primary)]">{scorePct}</p>
                <p className="text-[9px] text-[var(--color-text-faint)]">/100</p>
              </div>
            </div>
          </div>
          <div>
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ${config.color} ${config.ring} ${config.bg}`}>
              {VERDICT_LABEL[critic.verdict] ?? "Verdict Pending"}
            </span>
            {conflictCount > 0 && (
              <p className="mt-2 text-[12px] text-[var(--color-text-faint)]">
                <span className="font-semibold text-[var(--color-text-soft)]">{conflictCount}</span> cross-agent conflict{conflictCount !== 1 ? "s" : ""} detected
              </p>
            )}
          </div>
        </div>

        {/* Dimension bars */}
        <div className="min-w-0 space-y-2.5">
          {bars.map((b) => (
            <div key={b.label} className="flex items-center gap-3">
              <span className="w-24 shrink-0 text-[11.5px] text-[var(--color-text-faint)]">{b.label}</span>
              <div className="h-1.5 flex-1 rounded-full bg-[var(--color-surface-sunken)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${b.pct}%`, transition: "width 0.6s ease-out" }}
                />
              </div>
              <span className="w-9 shrink-0 text-right text-[11.5px] font-semibold text-[var(--color-text-soft)]">{b.pct}</span>
            </div>
          ))}
        </div>
      </div>

      {critic.notes && (
        <div className="mt-5 border-t border-[var(--color-border-soft)] pt-4">
          <p className={`text-[13px] leading-relaxed text-[var(--color-text-soft)] ${notesExpanded ? "" : "line-clamp-3"}`}>
            {critic.notes}
          </p>
          <button
            onClick={() => setNotesExpanded((v) => !v)}
            className="mt-1.5 text-[11px] font-semibold text-[var(--color-accent)]"
          >
            {notesExpanded ? "Show less" : "Read full reasoning"}
          </button>
        </div>
      )}
    </div>
  );
}

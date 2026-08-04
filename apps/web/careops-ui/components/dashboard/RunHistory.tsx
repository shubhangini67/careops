// components/dashboard/RunHistory.tsx
// Session run history -- last 5 runs, clickable to reload.

"use client";

import { RunHistoryEntry } from "@/types/planning";

interface Props {
  history:         RunHistoryEntry[];
  activeId?:       string | number;
  onSelect:        (entry: RunHistoryEntry) => void;
}

const VERDICT_COLOR: Record<string, string> = {
  approved: "text-emerald-400 border-emerald-500/30",
  rejected: "text-rose-400    border-rose-500/30",
  revision: "text-amber-400   border-amber-500/30",
  unknown:  "text-[var(--color-text-soft)]   border-[var(--color-border-default)]",
};

const VERDICT_DOT: Record<string, string> = {
  approved: "bg-emerald-400",
  rejected: "bg-rose-400",
  revision: "bg-amber-400",
  unknown:  "bg-slate-500",
};

export default function RunHistory({ history, activeId, onSelect }: Props) {
  if (history.length === 0) return null;

  const STAGGER = ["stagger-1","stagger-2","stagger-3","stagger-4","stagger-5"] as const;

  return (
    <div className="w-56 shrink-0">
      <p className="text-xs uppercase tracking-widest text-[var(--color-text-ghost)] mb-3 px-1">
        Run History
      </p>
      <div className="relative">
      <ul className="space-y-2 max-h-[380px] overflow-y-auto pr-0.5">
        {history.map((entry, idx) => {
          const isActive  = entry.id === activeId;
          const colors    = VERDICT_COLOR[entry.verdict] ?? VERDICT_COLOR.unknown;
          const dot       = VERDICT_DOT[entry.verdict]  ?? VERDICT_DOT.unknown;
          const scorePct  = entry.score; // RunHistoryEntry.score is already 0-100 (useFridayRush.ts)
          const time      = new Date(entry.runAt).toLocaleTimeString([], {
            hour: "2-digit", minute: "2-digit",
          });

          return (
            <li key={entry.id} className={STAGGER[Math.min(idx, 4)]}>
              <button
                onClick={() => onSelect(entry)}
                className={`w-full text-left rounded-xl border px-3 py-3
                  transition-all duration-200
                  ${isActive
                    ? "border-ember-500/50 bg-ember-500/10"
                    : "border-[var(--color-border-soft)] bg-[var(--color-surface)] hover:border-ember-500/20 hover:bg-[var(--color-surface-raised)]"
                  }
                `}
              >
                {/* Date */}
                <p className="text-xs font-mono text-[var(--color-text-soft)] truncate mb-1.5">
                  {entry.targetDate === "Next Friday"
                    ? "Next Friday"
                    : entry.targetDate}
                </p>

                {/* Verdict + score */}
                <div className={`flex items-center justify-between text-xs font-mono ${colors}`}>
                  <span className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
                    {entry.verdict}
                  </span>
                  <span>{scorePct == null ? "--" : `${scorePct}%`}</span>
                </div>

                {/* Time */}
                <p className="text-xs text-[var(--color-text-ghost)] mt-1.5 font-mono">{time}</p>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-[var(--color-surface)] to-transparent" />
      </div>
    </div>
  );
}

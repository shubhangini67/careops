"use client";

import { ConciergePlanHistoryEntry } from "@/lib/conciergeHistory";

export default function ConciergePreviousPlans({
  open,
  entries,
  activeSessionId,
  onSelect,
  onNew,
}: {
  open: boolean;
  entries: ConciergePlanHistoryEntry[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
}) {
  return (
    <div className={`${open ? "w-64" : "w-0"} shrink-0 overflow-hidden border-r border-[var(--color-border-default)] bg-[var(--color-surface-raised)] transition-all duration-200`}>
      <div className="flex h-full w-64 flex-col">
        <div className="flex items-center justify-between px-4 py-3.5 border-b border-[var(--color-border-default)]">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-text-faint)]">Previous plans</span>
          <button
            onClick={onNew}
            className="rounded-full bg-[var(--color-accent-soft)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-white"
          >
            + New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2.5 py-3 space-y-1.5">
          {entries.length === 0 && (
            <p className="px-2 py-2 text-[11px] text-[var(--color-text-faint)]">No previous plans on this device yet.</p>
          )}
          {entries.map((e) => {
            const active = e.session_id === activeSessionId;
            return (
              <button
                key={e.session_id}
                onClick={() => onSelect(e.session_id)}
                className={`flex w-full items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-all ${
                  active
                    ? "border-[var(--color-accent)]/40 bg-[var(--color-accent-soft)] shadow-[0_2px_6px_rgba(255,82,0,0.10)]"
                    : "border-[var(--color-border-default)] bg-[var(--color-surface)] shadow-[0_1px_2px_rgba(20,15,5,0.04)] hover:border-[var(--color-accent)]/30"
                }`}
              >
                <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
                  active ? "bg-[var(--color-accent)] text-white" : "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                }`}>
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                </span>
                <span className={`min-w-0 truncate text-[12.5px] ${active ? "font-bold text-[var(--color-accent)]" : "font-medium text-[var(--color-text-primary)]"}`}>
                  {e.title}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

"use client";

import { AlertTriangleIcon, CheckIcon, HourglassIcon, XIcon } from "./actionQueueMeta";

export type StatusKey = "pending" | "executed" | "failed" | "rejected";

// Label color stays the original vivid hue (still needs to read clearly as
// text); the icon badge fill is a muted/desaturated version of the same
// hue -- a solid fill, just not the neon-bright version, since white icon
// on the full-saturation color read as too poppy for a resting dashboard.
const STAT_META: Record<StatusKey, { label: string; color: string; fill: string }> = {
  pending:  { label: "Pending",  color: "#d97706", fill: "#b45309" },
  executed: { label: "Executed", color: "#059669", fill: "#3f8f70" },
  failed:   { label: "Failed",   color: "#e11d48", fill: "#be123c" },
  rejected: { label: "Rejected", color: "#64748b", fill: "#64748b" },
};

const STAT_ORDER: StatusKey[] = ["pending", "executed", "failed", "rejected"];

function StatIcon({ status }: { status: StatusKey }) {
  const cls = "h-3.5 w-3.5";
  if (status === "pending") return <HourglassIcon className={cls} strokeWidth={2} />;
  if (status === "executed") return <CheckIcon className={cls} strokeWidth={2.6} />;
  if (status === "failed") return <AlertTriangleIcon className={cls} strokeWidth={2} />;
  return <XIcon className={cls} strokeWidth={2.6} />;
}

export default function ActionQueueStats({
  counts,
  activeStatus,
  onSelect,
}: {
  counts: Record<StatusKey, number>;
  activeStatus?: StatusKey | "all";
  onSelect?: (status: StatusKey) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {STAT_ORDER.map((key) => {
        const meta = STAT_META[key];
        const active = activeStatus === key;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onSelect?.(key)}
            className="card flex items-center justify-between gap-3 px-4 py-4 text-left"
            style={{
              borderColor: active ? meta.color : undefined,
              borderWidth: active ? 1.5 : undefined,
            }}
          >
            <div className="flex min-w-0 items-center gap-3">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-white"
                style={{ background: meta.fill }}
              >
                <StatIcon status={key} />
              </span>
              <div className="flex min-w-0 items-baseline gap-2">
                <p className="text-[13px] font-semibold uppercase tracking-wide" style={{ color: meta.color }}>{meta.label}</p>
                <p className="text-[16px] font-bold leading-none text-[var(--color-text-primary)]">{counts[key]}</p>
              </div>
            </div>
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4 shrink-0 text-[var(--color-text-ghost)]" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        );
      })}
    </div>
  );
}

"use client";

import { MarketSlotAvailability } from "@/lib/api";

const SIGNAL_STYLE: Record<string, { bar: string; text: string }> = {
  HIGH:   { bar: "bg-rose-400",    text: "text-rose-600 dark:text-rose-300" },
  MEDIUM: { bar: "bg-amber-400",   text: "text-amber-600 dark:text-amber-400" },
  LOW:    { bar: "bg-emerald-400", text: "text-emerald-600 dark:text-emerald-400" },
};

export default function OccupancyBySlotChart({ data }: { data: MarketSlotAvailability[] }) {
  if (data.length === 0) return null;

  return (
    <div>
      <p className="mb-3 text-[9px] uppercase tracking-widest text-[var(--color-text-ghost)]">
        Occupancy by dinner slot tonight
      </p>
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        {data.map((s) => {
          const style = SIGNAL_STYLE[s.signal] ?? { bar: "bg-blue-300", text: "text-blue-500 dark:text-blue-300" };
          return (
            <div key={s.time} className="text-center">
              <p className="mb-1.5 text-[10px] font-medium text-[var(--color-text-faint)]">{s.time}</p>
              <div className={`mx-auto mb-2 h-1.5 w-full max-w-[48px] rounded-full ${style.bar}`} />
              <p className="text-sm font-semibold text-[var(--color-text-primary)]">{s.avg_availability} avg</p>
              <p className={`text-[10px] font-semibold uppercase tracking-wide ${style.text}`}>{s.signal}</p>
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex items-center gap-4 border-t border-[var(--color-border-soft)] pt-3 text-[10px] text-[var(--color-text-faint)]">
        {(["HIGH", "MEDIUM", "LOW"] as const).map((sig) => (
          <span key={sig} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${SIGNAL_STYLE[sig].bar}`} />
            {sig}
          </span>
        ))}
      </div>
    </div>
  );
}

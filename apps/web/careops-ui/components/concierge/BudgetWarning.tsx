"use client";

interface BudgetBreakdown {
  budget_inr?: number | null;
  spent_total?: number;
  remaining?: number | null;
  breakdown?: { venue_estimate?: number; food?: number; supplies?: number };
}

export function BudgetSummaryCard({ data }: { data: BudgetBreakdown }) {
  const over = data.remaining != null && data.remaining < 0;
  return (
    <div className="card w-full max-w-sm px-4 py-3.5">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-ghost)]">Budget</p>
        {data.budget_inr != null && <p className="text-[12.5px] font-bold text-[var(--color-text-primary)]">Rs.{Math.round(data.budget_inr)}</p>}
      </div>

      {data.budget_inr != null && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
          <div
            className={`h-full rounded-full ${over ? "bg-[var(--color-critical)]" : "bg-[var(--color-accent)]"}`}
            style={{ width: `${Math.min(100, ((data.spent_total ?? 0) / data.budget_inr) * 100)}%` }}
          />
        </div>
      )}

      <div className="mt-2.5 space-y-1 text-[11px] text-[var(--color-text-soft)]">
        {data.breakdown?.venue_estimate ? <div className="flex justify-between"><span>Venue</span><span>Rs.{Math.round(data.breakdown.venue_estimate)}</span></div> : null}
        {data.breakdown?.food ? <div className="flex justify-between"><span>Food</span><span>Rs.{Math.round(data.breakdown.food)}</span></div> : null}
        {data.breakdown?.supplies ? <div className="flex justify-between"><span>Supplies</span><span>Rs.{Math.round(data.breakdown.supplies)}</span></div> : null}
      </div>

      <p className={`mt-2 text-[12px] font-semibold ${over ? "text-[var(--color-critical)]" : "text-[var(--color-text-primary)]"}`}>
        {over ? `Rs.${Math.abs(data.remaining ?? 0)} over budget` : `Rs.${Math.round(data.remaining ?? 0)} remaining`}
      </p>
    </div>
  );
}

export function ErrorNote({ text, note }: { text: string; note?: string }) {
  return (
    <div className="w-full max-w-sm rounded-xl border border-[var(--color-critical)]/25 bg-[var(--color-critical-soft)] px-3.5 py-2.5">
      <p className="text-[12px] font-medium leading-snug text-[var(--color-critical)]">{text}</p>
      {note && <p className="mt-1 text-[11px] text-[var(--color-text-faint)]">{note}</p>}
    </div>
  );
}

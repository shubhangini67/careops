"use client";

import { ConciergeSessionState } from "@/types/concierge";

const OCCASION_LABEL: Record<string, string> = {
  birthday: "Birthday",
  anniversary: "Anniversary",
  corporate: "Corporate event",
  date: "Date night",
  general: "Get-together",
};

function EventSummaryCard({ session }: { session: ConciergeSessionState | null }) {
  const hasBudget = session?.budget_inr != null;
  const spent = session?.budget_spent ?? 0;
  const pct = hasBudget ? Math.min(100, (spent / (session!.budget_inr as number)) * 100) : 0;
  const over = session?.budget_remaining != null && session.budget_remaining < 0;

  return (
    <div className="card px-4 py-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-text-ghost)]">Event summary</p>

      <div className="mt-3 space-y-2 text-[12.5px]">
        <div className="flex justify-between">
          <span className="text-[var(--color-text-faint)]">Occasion</span>
          <span className="font-semibold text-[var(--color-text-primary)]">
            {session?.occasion ? OCCASION_LABEL[session.occasion] ?? session.occasion : "—"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--color-text-faint)]">Guests</span>
          <span className="font-semibold text-[var(--color-text-primary)]">{session?.headcount ?? "—"}</span>
        </div>
      </div>

      {hasBudget && (
        <div className="mt-3.5">
          <div className="flex justify-between text-[11px] text-[var(--color-text-faint)]">
            <span>Rs.{Math.round(spent)} spent</span>
            <span>of Rs.{Math.round(session!.budget_inr as number)}</span>
          </div>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
            <div
              className={`h-full rounded-full transition-all ${over ? "bg-[var(--color-critical)]" : "bg-[var(--color-accent)]"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className={`mt-1.5 text-[11.5px] font-semibold ${over ? "text-[var(--color-critical)]" : "text-[var(--color-text-primary)]"}`}>
            {over ? `Rs.${Math.abs(session!.budget_remaining as number)} over budget` : `Rs.${Math.round(session?.budget_remaining ?? 0)} remaining`}
          </p>
        </div>
      )}

      {session?.preferences && session.preferences.length > 0 && (
        <div className="mt-3.5 flex flex-wrap gap-1">
          {session.preferences.map((p) => (
            <span key={p} className="rounded-full bg-[var(--color-accent-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-accent)]">
              {p}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ActiveBookingsPanel({ session }: { session: ConciergeSessionState | null }) {
  const bookings = session?.active_bookings ?? [];
  if (bookings.length === 0) return null;

  return (
    <div className="card px-4 py-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-text-ghost)]">
        Bookings ({bookings.length})
      </p>
      <div className="mt-3 space-y-2.5">
        {bookings.map((b, i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border-soft)] px-3 py-2">
            <p className="truncate text-[12px] font-semibold text-[var(--color-text-primary)]">{b.restaurant_name ?? "Table"}</p>
            <div className="mt-0.5 flex items-center justify-between">
              <span className="text-[10.5px] text-[var(--color-text-faint)]">{b.display_time ?? ""}</span>
              <span className={`text-[10.5px] font-semibold ${b.status === "confirmed" ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}`}>
                {b.status === "confirmed" ? "Confirmed" : "Pending"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActiveOrdersPanel({ session }: { session: ConciergeSessionState | null }) {
  const food = (session?.active_food_orders ?? []).map((o) => ({ ...o, kind: "Food" as const }));
  const supplies = (session?.active_instamart_orders ?? []).map((o) => ({ ...o, kind: "Supplies" as const }));
  const orders = [...food, ...supplies];
  if (orders.length === 0) return null;

  return (
    <div className="card px-4 py-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-text-ghost)]">
        Orders ({orders.length})
      </p>
      <div className="mt-3 space-y-2.5">
        {orders.map((o, i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border-soft)] px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--color-text-ghost)]">{o.kind}</span>
              {o.total != null && <span className="text-[12px] font-semibold text-[var(--color-text-primary)]">Rs.{Math.round(o.total)}</span>}
            </div>
            <p className={`mt-0.5 text-[10.5px] font-semibold ${o.status === "confirmed" ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}`}>
              {o.status === "pending_staging" ? "Pending confirmation" : o.status ?? "Submitted"}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ConciergeSidebar({
  session,
  onReset,
}: {
  session: ConciergeSessionState | null;
  onReset: () => void;
}) {
  return (
    <aside className="hidden w-72 shrink-0 flex-col gap-3 overflow-y-auto border-l border-[var(--color-border-default)] bg-[var(--color-surface-raised)] p-4 shadow-[-1px_0_0_rgba(0,0,0,0.02),-8px_0_24px_-18px_rgba(60,40,15,0.4)] dark:shadow-[-1px_0_0_rgba(255,255,255,0.03),-8px_0_24px_-16px_rgba(0,0,0,0.6)] lg:flex">
      <EventSummaryCard session={session} />
      <ActiveBookingsPanel session={session} />
      <ActiveOrdersPanel session={session} />

      <button
        onClick={onReset}
        className="mt-auto rounded-lg border border-[var(--color-border-default)] py-2 text-[11.5px] font-semibold text-[var(--color-text-faint)] transition-colors hover:border-[var(--color-critical)]/40 hover:text-[var(--color-critical)]"
      >
        Start over
      </button>
    </aside>
  );
}

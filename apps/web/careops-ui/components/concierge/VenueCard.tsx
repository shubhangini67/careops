"use client";

import { ConciergeVenue } from "@/types/concierge";

export default function VenueCard({
  venue,
  headcount,
  onQuickMessage,
}: {
  venue: ConciergeVenue;
  headcount?: number | null;
  onQuickMessage: (text: string) => void;
}) {
  const freeDeals = (venue.deals ?? []).filter((d) => d.isFree && d.title);

  return (
    <div className="card w-full max-w-sm px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[13.5px] font-semibold text-[var(--color-text-primary)]">{venue.name ?? "Venue"}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--color-text-faint)]">
            {venue.avg_rating != null && (
              <span className="inline-flex items-center gap-0.5 font-semibold text-[var(--color-accent)]">★ {venue.avg_rating}</span>
            )}
            {venue.distance_km != null && <span>· {venue.distance_km} km away</span>}
          </div>
        </div>
        {(venue.estimated_cost ?? venue.cost_for_two) != null && (
          <div className="shrink-0 text-right">
            <p className="text-[9px] uppercase tracking-[0.14em] text-[var(--color-text-ghost)]">Est. cost</p>
            <p className="text-[13px] font-bold text-[var(--color-text-primary)]">
              Rs.{Math.round(venue.estimated_cost ?? venue.cost_for_two ?? 0)}
            </p>
          </div>
        )}
      </div>

      {venue.cuisines && venue.cuisines.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {venue.cuisines.slice(0, 4).map((c) => (
            <span key={c} className="rounded-full bg-[var(--color-surface-sunken)] px-2 py-0.5 text-[10px] text-[var(--color-text-soft)]">
              {c}
            </span>
          ))}
        </div>
      )}

      {freeDeals.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {freeDeals.slice(0, 2).map((d, i) => (
            <span key={i} className="rounded-full bg-[var(--color-accent-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-accent)]">
              {d.title}
            </span>
          ))}
        </div>
      )}

      <button
        onClick={() =>
          onQuickMessage(
            `Check table availability at ${venue.name ?? "this venue"}${headcount ? ` for ${headcount} people` : ""}.`
          )
        }
        className="mt-3 w-full rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-1.5 text-[11.5px] font-semibold text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
      >
        Check availability
      </button>
    </div>
  );
}

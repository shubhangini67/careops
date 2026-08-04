"use client";

import { ConciergeSlot } from "@/types/concierge";

export default function SlotCard({
  slot,
  restaurantName,
  onQuickMessage,
}: {
  slot: ConciergeSlot;
  restaurantName?: string;
  onQuickMessage: (text: string) => void;
}) {
  return (
    <div className="card flex w-full max-w-sm items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">{slot.display_time ?? "Slot"}</p>
        {slot.deal_title && (
          <p className="mt-0.5 truncate text-[11px] font-medium text-[var(--color-accent)]">{slot.deal_title}</p>
        )}
        {slot.availability_count != null && (
          <p className="mt-0.5 text-[10.5px] text-[var(--color-text-faint)]">{slot.availability_count} tables free</p>
        )}
      </div>
      <button
        onClick={() =>
          onQuickMessage(
            `Book the ${slot.display_time ?? ""} slot${restaurantName ? ` at ${restaurantName}` : ""}.`
          )
        }
        className="shrink-0 rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-[11px] font-bold text-white shadow-[0_2px_8px_rgba(255,82,0,0.25)] transition-all hover:brightness-105"
      >
        Book table
      </button>
    </div>
  );
}

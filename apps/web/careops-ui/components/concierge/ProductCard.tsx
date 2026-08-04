"use client";

import { ConciergeSupplyItem } from "@/types/concierge";

export default function ProductCard({
  item,
  onQuickMessage,
}: {
  item: ConciergeSupplyItem;
  onQuickMessage: (text: string) => void;
}) {
  return (
    <div className="card flex w-full max-w-sm items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="truncate text-[13px] font-semibold text-[var(--color-text-primary)]">{item.name ?? item.query}</p>
        <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-faint)]">
          {item.price != null && <span className="font-semibold text-[var(--color-text-primary)]">Rs.{item.price}</span>}
          {item.unit && <span>· {item.unit}</span>}
          {item.in_stock === false && <span className="text-[var(--color-critical)]">· out of stock</span>}
        </div>
      </div>
      <button
        disabled={item.in_stock === false}
        onClick={() => onQuickMessage(`Add ${item.name ?? item.query} to my supplies cart.`)}
        className="shrink-0 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-[11px] font-semibold text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-40"
      >
        Add to cart
      </button>
    </div>
  );
}

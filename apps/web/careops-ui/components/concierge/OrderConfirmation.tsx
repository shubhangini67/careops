"use client";

import { ConciergeBooking, ConciergeOrder } from "@/types/concierge";
import { StagingInlineNote } from "@/components/concierge/StagingInlineNote";

const STATUS_LABEL: Record<string, string> = {
  pending_staging: "Pending confirmation",
  pending_confirmation: "Pending confirmation",
  confirmed: "Confirmed",
};

function statusTone(status?: string) {
  if (status === "confirmed") return "text-emerald-600 dark:text-emerald-400";
  if (status === "pending_staging" || status === "pending_confirmation") return "text-amber-600 dark:text-amber-400";
  return "text-[var(--color-text-soft)]";
}

export default function OrderConfirmation({ record }: { record: ConciergeBooking | ConciergeOrder }) {
  const isBooking = "restaurant_name" in record;
  const title = isBooking ? (record as ConciergeBooking).restaurant_name ?? "Table booking" : "Order";
  const status = record.status;
  const total = isBooking ? (record as ConciergeBooking).estimated_cost : (record as ConciergeOrder).total;
  const eta = !isBooking ? (record as ConciergeOrder).estimated_delivery ?? (record as ConciergeOrder).estimated_delivery_mins : undefined;
  const code = isBooking ? (record as ConciergeBooking).confirmation_code ?? (record as ConciergeBooking).order_id : (record as ConciergeOrder).order_id;

  return (
    <div className="card w-full max-w-sm px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">{title}</p>
        {total != null && <p className="text-[13px] font-bold text-[var(--color-text-primary)]">Rs.{Math.round(total)}</p>}
      </div>
      <p className={`mt-1 text-[11.5px] font-semibold ${statusTone(status)}`}>
        {STATUS_LABEL[status ?? ""] ?? status ?? "Submitted"}
      </p>
      {code && <p className="mt-0.5 text-[10.5px] text-[var(--color-text-faint)]">Ref: {code}</p>}
      {eta && <p className="mt-0.5 text-[10.5px] text-[var(--color-text-faint)]">ETA: {eta}</p>}
      {status === "pending_staging" && (
        <StagingInlineNote text="Your spot in the plan is saved. Final confirmation will follow shortly." />
      )}
    </div>
  );
}

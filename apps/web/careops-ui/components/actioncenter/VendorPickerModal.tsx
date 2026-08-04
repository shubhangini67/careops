"use client";

// "Message Your Vendors" -- a real restaurant works with a handful of real
// vendors by category (produce, dairy, general grocery, etc.), not one
// auto-picked one. This lists the org's actual vendors and what each one
// really supplies (from real VendorPriceQuote data, never fabricated), and
// lets the owner choose who to message -- same real WhatsApp draft/approve
// flow either way, just owner-chosen instead of silently auto-matched.

import { useEffect, useState } from "react";
import { createVendorMessage, getVendors, type ActionQueueItem, type VendorSummary } from "@/lib/api";
import { ChannelIcon, XIcon } from "./actionQueueMeta";

type Status = "loading" | "done" | "error";

const CATEGORY_LABELS: Record<string, string> = {
  produce: "Produce",
  dairy: "Dairy",
  general: "General Grocery",
};

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function VendorPickerModal({
  ingredient, context, onClose, onDrafted,
}: {
  ingredient: string;
  context?: {
    unit?: string | null;
    quantity_in_stock?: number | null;
    reorder_threshold?: number | null;
    recommended_restock_qty?: number | null;
    reason?: string | null;
  };
  onClose: () => void;
  onDrafted: (action: ActionQueueItem) => void;
}) {
  const [status, setStatus] = useState<Status>("loading");
  const [vendors, setVendors] = useState<VendorSummary[]>([]);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  useEffect(() => {
    getVendors()
      .then((data) => { setVendors(data); setStatus("done"); })
      .catch(() => setStatus("error"));
  }, []);

  const handlePick = async (vendor: VendorSummary) => {
    setSendingId(vendor.id);
    setSendError(null);
    try {
      const action = await createVendorMessage({
        vendor_id: vendor.id,
        ingredient,
        unit: context?.unit,
        quantity_in_stock: context?.quantity_in_stock,
        reorder_threshold: context?.reorder_threshold,
        recommended_restock_qty: context?.recommended_restock_qty,
        reason: context?.reason,
      });
      onDrafted(action);
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Couldn't draft that message.");
    } finally {
      setSendingId(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-[backdropIn_0.15s_ease_both]"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-2xl bg-[var(--color-surface-raised)] shadow-2xl animate-[modalIn_0.2s_ease-out_both]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border-soft)] bg-[var(--color-surface-raised)] px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white p-1.5 shadow-sm">
              <ChannelIcon channel="whatsapp" className="h-full w-full" />
            </div>
            <div>
              <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-accent)]">Message your vendors</p>
              <p className="mt-0.5 text-[15px] font-bold leading-tight text-[var(--color-text-primary)]">
                Who&apos;s this about?
              </p>
              <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">
                Choose who to message about {capitalize(ingredient)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-full p-1.5 text-[var(--color-text-faint)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-text-primary)]"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {status === "loading" && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--color-border-default)] border-t-[var(--color-accent)]" />
              <p className="text-[12px] text-[var(--color-text-faint)]">Loading your vendors…</p>
            </div>
          )}
          {status === "error" && (
            <p className="py-10 text-center text-[12px]" style={{ color: "var(--color-caution)" }}>
              Couldn&apos;t load your vendors right now.
            </p>
          )}
          {status === "done" && vendors.length === 0 && (
            <p className="py-10 text-center text-[12px] text-[var(--color-text-faint)]">
              No vendors on file yet. Add one under Restaurant Profiles to message them here.
            </p>
          )}
          {status === "done" && vendors.length > 0 && (
            <div className="space-y-2">
              {vendors.map((v) => (
                <button
                  key={v.id}
                  onClick={() => handlePick(v)}
                  disabled={sendingId !== null}
                  className="w-full rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] p-3.5 text-left shadow-sm transition-all hover:-translate-y-px hover:border-[var(--color-accent)] hover:shadow-md disabled:cursor-wait disabled:opacity-60 disabled:hover:translate-y-0"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">{v.name}</p>
                    {v.category && (
                      <span
                        className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                        style={{ background: "var(--color-accent-soft)", color: "var(--color-accent)" }}
                      >
                        {CATEGORY_LABELS[v.category] ?? capitalize(v.category)}
                      </span>
                    )}
                  </div>
                  {v.supplies.length > 0 && (
                    <p className="mt-1 text-[11px] text-[var(--color-text-faint)]">
                      Deals in: {v.supplies.slice(0, 4).join(", ")}
                      {v.supplies.length > 4 ? `, +${v.supplies.length - 4} more` : ""}
                    </p>
                  )}
                  <p className="mt-1.5 flex items-center gap-1 text-[11px] font-medium" style={{ color: "var(--color-good)" }}>
                    {sendingId === v.id ? (
                      <>
                        <span className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--color-good)] border-t-transparent" />
                        Drafting message…
                      </>
                    ) : (
                      "Draft a WhatsApp message →"
                    )}
                  </p>
                </button>
              ))}
            </div>
          )}
          {sendError && (
            <p className="mt-2 text-[11px]" style={{ color: "var(--color-caution)" }}>{sendError}</p>
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { rejectAction, type ActionQueueItem } from "@/lib/api";
import {
  BagIcon, ChannelIcon, ClockIcon, XIcon, shortagesOf,
} from "./actionQueueMeta";
import InstamartPriceModal from "./InstamartPriceModal";
import VendorPickerModal from "./VendorPickerModal";

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function ActionAttentionHero({
  action,
  onDismissed,
  onOpenAction,
  onSnoozed,
}: {
  action: ActionQueueItem;
  onDismissed: () => void;
  onOpenAction: (action: ActionQueueItem) => void;
  onSnoozed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [showInstamartModal, setShowInstamartModal] = useState(false);
  const [showVendorPicker, setShowVendorPicker] = useState(false);

  const shortages = shortagesOf(action);
  const top = shortages[0];

  const headline = top
    ? `${shortages.length} inventory item${shortages.length !== 1 ? "s" : ""} need${shortages.length !== 1 ? "" : "s"} your approval`
    : action.title;

  const detailText = top
    ? "Below threshold"
    : action.category === "pricing_promo_review"
      ? `${String(action.payload.area_deals_count ?? 0)} nearby deals live tonight`
      : null;


  const ingredientForSearch = top?.ingredient
    ?? (action.category === "whatsapp_vendor_order" ? String(action.payload.ingredient ?? "") : null);

  const handleDismiss = async () => {
    setBusy(true);
    try {
      await rejectAction(action.id);
      onDismissed();
    } catch {
      // leave the item in place on failure
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="relative overflow-hidden rounded-xl p-5 shadow-[0_1px_2px_rgba(60,40,15,0.05),0_2px_6px_rgba(60,40,15,0.09),0_18px_44px_-12px_rgba(60,40,15,0.24)] sm:p-6"
      style={{ background: "var(--color-surface-raised)" }}
    >
      {/* Top accent bar + corner glow -- same family treatment as the KPI
          strip below it, so the hero reads as part of one designed system
          instead of a differently-styled banner bolted on top. Kept to the
          site's one accent orange rather than introducing red -- the page
          was reading as too many competing colors at once. */}
      <span
        className="absolute inset-x-0 top-0"
        style={{ background: "linear-gradient(90deg, var(--color-accent), #ffab5e)" }}
      />
      <span
        className="pointer-events-none absolute -left-10 -top-10 h-48 w-48 rounded-full blur-3xl"
        style={{ background: "rgba(255,82,0,0.18)" }}
      />

      <div className="relative flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
       <div className="flex items-center gap-2">
  <p className="text-[13px] font-bold uppercase tracking-wide text-[var(--color-text-soft)]">
    Action Required !
  </p>


</div>

        <h2 className="mt-1.5 text-[20px] font-bold leading-snug text-[var(--color-text-primary)]">
          {headline}
        </h2>

        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-2">
          {top && (
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium text-[var(--color-text-primary)] shadow-sm"
              style={{ background: "var(--color-accent-soft)" }}
            >
              <BagIcon className="h-3.5 w-3.5" />
              {capitalize(top.ingredient)}
              {top.quantity_in_stock !== undefined ? ` (${top.quantity_in_stock}${top.unit ?? ""})` : ""}
            </span>
          )}
          {detailText && (
            <span className="text-[13px] font-semibold" style={{ color: "var(--color-accent)" }}>
              {detailText}
            </span>
          )}
          {top?.recommended_restock_qty !== undefined && (
            <span className="text-[13px] font-medium text-[var(--color-text-soft)]">
              Restock {top.recommended_restock_qty}{top.unit ?? ""}
            </span>
          )}
        </div>

        {top?.reason && (
          <p className="mt-2 max-w-[460px] text-[13px] leading-relaxed text-[var(--color-text-faint)]">
            {top.reason}
          </p>
        )}

        {/* Two independent, human-decided options -- the system never picks
            one for the owner. Instamart is a real live price check (no cart/
            checkout yet: blocked on Swiggy staging creds); WhatsApp opens the
            real draft message to whichever local vendor is on file. */}
        {ingredientForSearch && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => setShowInstamartModal(true)}
              className="hero-instamart-btn inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-[13px] font-semibold text-[var(--color-text-primary)] shadow-sm transition-transform hover:-translate-y-px"
            >
              <ChannelIcon channel="instamart" className="h-6 w-6" />
              Check Supply Price
            </button>
            {top && (
              <button
                onClick={() => setShowVendorPicker(true)}
                className="hero-whatsapp-btn inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-[13px] font-semibold text-[var(--color-text-primary)] shadow-sm transition-transform hover:-translate-y-px"
              >
                <ChannelIcon channel="whatsapp" className="h-6 w-6" />
                Message Your Vendors
              </button>
            )}
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--color-border-soft)] pt-3">
          <button
            onClick={() => onOpenAction(action)}
            className="btn-primary inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold shadow-sm transition-transform hover:-translate-y-px"
          >
            View Details
          
          </button>
          <button
            onClick={handleDismiss}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3.5 py-2 text-[13px] font-semibold text-[var(--color-text-soft)] shadow-sm transition-all hover:-translate-y-px hover:border-[var(--color-text-faint)] hover:text-[var(--color-text-primary)] disabled:opacity-50"
          >
            <XIcon className="h-3.5 w-3.5" />
            Dismiss
          </button>
          <button
            onClick={onSnoozed}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3.5 py-2 text-[13px] font-semibold text-[var(--color-text-soft)] shadow-sm transition-all hover:-translate-y-px hover:border-[var(--color-text-faint)] hover:text-[var(--color-text-primary)]"
          >
            <ClockIcon className="h-3.5 w-3.5" />
            Snooze 1hr
          </button>
        </div>
      </div>

      <div className="relative hidden h-[130px] w-[240px] shrink-0 self-center rounded-2xl sm:block md:h-[150px] md:w-[277px] lg:h-[170px] lg:w-[315px]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/banners/light-mode/inventory-graphics-light.png"
          alt=""
          aria-hidden="true"
          className="hero-illustration-light pointer-events-none absolute inset-0 h-full w-full object-contain transition-opacity duration-500 ease-in-out"
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/banners/dark-mode/inventory-graphics.png"
          alt=""
          aria-hidden="true"
          className="hero-illustration-dark pointer-events-none absolute inset-0 h-full w-full object-contain transition-opacity duration-500 ease-in-out"
        />
      </div>
      </div>

      {showInstamartModal && ingredientForSearch && (
        <InstamartPriceModal
          initialQuery={ingredientForSearch}
          onClose={() => setShowInstamartModal(false)}
        />
      )}

      {showVendorPicker && top && (
        <VendorPickerModal
          ingredient={top.ingredient}
          context={{
            unit: top.unit,
            quantity_in_stock: top.quantity_in_stock,
            reorder_threshold: top.reorder_threshold,
            recommended_restock_qty: top.recommended_restock_qty,
            reason: top.reason,
          }}
          onClose={() => setShowVendorPicker(false)}
          onDrafted={(drafted) => { setShowVendorPicker(false); onOpenAction(drafted); }}
        />
      )}
    </div>
  );
}

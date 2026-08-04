// Shared category/priority/icon language for Action Center's hero card,
// pending panel, and history timeline -- kept in one place so all three
// surfaces render the same category identical to each other.

import type { ReactNode } from "react";
import type { ActionQueueItem } from "@/lib/api";

/** Shared filter-chip look for Action Queue/History's status + channel
 * tabs -- solid fill when active, outlined ghost otherwise, instead of each
 * file hand-rolling its own slightly-different pill classes. */
export function FilterChip({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
        active
          ? "bg-[var(--color-accent)] text-white shadow-sm"
          : "border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] text-[var(--color-text-soft)] hover:border-[var(--color-text-faint)] hover:text-[var(--color-text-primary)]"
      }`}
    >
      {children}
    </button>
  );
}

export const CATEGORY_LABELS: Record<string, string> = {
  whatsapp_vendor_order: "WhatsApp vendor order",
  restock_alert: "Restock",
  pricing_promo_review: "Pricing Review",
  overstock_alert: "Overstock",
};

export const AGENT_LABELS: Record<string, string> = {
  whatsapp_vendor_order: "Procurement Agent",
  restock_alert: "Inventory Agent",
  pricing_promo_review: "Market Intel Agent",
  overstock_alert: "Inventory Agent",
};

// Text/icon tone per category -- WhatsApp reads green (brand-consistent),
// Restock reads amber (matches the existing caution/inventory language),
// Pricing Review gets a distinct cyan, Overstock gets a distinct violet so
// all four are never confusable at a glance.
export const CATEGORY_TONE: Record<string, string> = {
  whatsapp_vendor_order: "var(--color-good)",
  restock_alert: "var(--color-caution)",
  pricing_promo_review: "#38bdf8",
  overstock_alert: "#a855f7",
};

export const CATEGORY_TONE_SOFT: Record<string, string> = {
  whatsapp_vendor_order: "var(--color-good-soft)",
  restock_alert: "var(--color-caution-soft)",
  pricing_promo_review: "rgba(56,189,248,0.10)",
  overstock_alert: "rgba(168,85,247,0.10)",
};

export type Shortage = {
  ingredient: string;
  unit?: string;
  quantity_in_stock?: number;
  reorder_threshold?: number;
  shortfall?: number;
  recommended_restock_qty?: number;
  // The real, local (WhatsApp/phone) vendor for this ingredient, when one is
  // on file -- Instamart is deliberately NOT here: its price is checked live,
  // on demand, never pre-picked as "the" channel. The owner chooses per
  // shortage, the system just surfaces the real WhatsApp option when it exists.
  whatsapp_vendor?: string | null;
  reason?: string | null;
  severity?: string;
};

export function shortagesOf(action: ActionQueueItem): Shortage[] {
  const raw = action.payload?.shortages;
  return Array.isArray(raw) ? (raw as Shortage[]) : [];
}

export type OverstockItem = {
  ingredient: string;
  unit?: string;
  quantity_in_stock?: number;
  reorder_threshold?: number;
  excess?: number;
  reason?: string | null;
};

export function overstockOf(action: ActionQueueItem): OverstockItem[] {
  const raw = action.payload?.overstock_items;
  return Array.isArray(raw) ? (raw as OverstockItem[]) : [];
}

export type Channel = "instamart" | "whatsapp";

export const CHANNEL_LABELS: Record<Channel, string> = {
  instamart: "Supply catalog",
  whatsapp: "WhatsApp",
};

/** Which channel an action actually WAS/IS placed through -- only ever
 * "whatsapp" (a whatsapp_vendor_order is a WhatsApp order by definition).
 * A restock_alert is not itself placed through either channel: it just
 * surfaces both real options (an on-demand Instamart price check, and a
 * WhatsApp draft when a real local vendor is on file) for the owner to pick
 * from, so it has no single channel of its own -- there's no "instamart"
 * category yet since real checkout is still blocked on staging creds. */
export function channelOf(action: ActionQueueItem): Channel | null {
  if (action.category === "whatsapp_vendor_order") return "whatsapp";
  return null;
}

export function ChannelIcon({ channel, className = "h-4 w-4" }: { channel?: Channel | null; className?: string }) {
  if (channel === "instamart") {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src="/icons/instamart-icon.png" alt="" aria-hidden="true" className={`${className} object-contain`} />;
  }
  if (channel === "whatsapp") {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src="/icons/whatsapp-icon.png" alt="" aria-hidden="true" className={`${className} object-contain`} />;
  }
  return null;
}

/** "High Priority" for anything approve-gated or carrying a critical shortage,
 * "Medium Priority" otherwise -- derived from real fields, never fabricated. */
export function priorityLabel(action: ActionQueueItem): "High Priority" | "Medium Priority" {
  const hasCritical = shortagesOf(action).some((s) => s.severity === "critical");
  if (action.tier === "approve_required" || hasCritical) return "High Priority";
  return "Medium Priority";
}

export function CategoryIcon({ category, className = "h-5 w-5" }: { category: string; className?: string }) {
  if (category === "whatsapp_vendor_order") {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src="/icons/whatsapp-icon.png" alt="" aria-hidden="true" className={`${className} object-contain`} />;
  }
  if (category === "pricing_promo_review") {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5.586a1 1 0 01.707.293l7.414 7.414a1 1 0 010 1.414l-8.586 8.586a1 1 0 01-1.414 0L3.293 13.293A1 1 0 013 12.586V7a4 4 0 014-4z" />
      </svg>
    );
  }
  if (category === "overstock_alert") {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2m-9 0l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M10 11v6M14 11v6" />
      </svg>
    );
  }
  // restock_alert / default
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
  );
}

export function CheckIcon({ className = "h-3.5 w-3.5", strokeWidth = 2.4 }: { className?: string; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={strokeWidth}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

export function XIcon({ className = "h-3.5 w-3.5", strokeWidth = 2.4 }: { className?: string; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={strokeWidth}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

export function InfoIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25h.375c.207 0 .375.168.375.375v4.5m-.75-9h.008v.008h-.008V6.75zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

export function EyeIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

export function AlertTriangleIcon({ className = "h-4 w-4", strokeWidth = 1.8 }: { className?: string; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={strokeWidth}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  );
}

export function HourglassIcon({ className = "h-4 w-4", strokeWidth = 1.8 }: { className?: string; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={strokeWidth}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

export function ThumbUpIcon({ className = "h-4 w-4", strokeWidth = 1.8 }: { className?: string; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={strokeWidth}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75A2.25 2.25 0 0116.5 4.5c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904M6.633 10.5H5.904m0 0H3.375A1.125 1.125 0 002.25 11.625v6.75A1.125 1.125 0 003.375 19.5h1.638a.75.75 0 00.75-.75v-7.5a.75.75 0 00-.75-.75z" />
    </svg>
  );
}

export function BagIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 7h12l1 13H5L6 7z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 10V6a3 3 0 016 0v4" />
    </svg>
  );
}

export function ClockIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 7v5l3.5 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

export function ArrowRightIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2.2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
    </svg>
  );
}

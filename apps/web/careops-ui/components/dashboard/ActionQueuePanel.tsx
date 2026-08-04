"use client";

import { useEffect, useMemo, useState } from "react";
import { getActionQueue, approveAction, rejectAction, type ActionQueueItem } from "@/lib/api";
import {
  AGENT_LABELS, CATEGORY_LABELS, CATEGORY_TONE, ChannelIcon,
  CategoryIcon, FilterChip, InfoIcon, XIcon, channelOf, overstockOf, priorityLabel, shortagesOf,
} from "@/components/actioncenter/actionQueueMeta";
import InstamartPriceModal from "@/components/actioncenter/InstamartPriceModal";
import VendorPickerModal from "@/components/actioncenter/VendorPickerModal";
import { toSupplyLabel } from "@/lib/careopsDisplay";

/** One shortage's real, per-ingredient fulfillment options -- a live
 * Instamart cart-preview modal, plus a real vendor picker (a restaurant has
 * multiple real vendors by category, so the owner chooses who to message
 * rather than the system silently auto-picking one). Same pattern as the
 * hero card, now available for every restock_alert row reviewed from the
 * list, not just the single featured one. */
function ShortageRow({
  shortage, onDrafted,
}: {
  shortage: ReturnType<typeof shortagesOf>[number];
  /** Called with the newly-created WhatsApp draft once a vendor is picked --
   * the parent switches the details modal to show it for review/send. */
  onDrafted?: (action: ActionQueueItem) => void;
}) {
  const [showInstamartModal, setShowInstamartModal] = useState(false);
  const [showVendorPicker, setShowVendorPicker] = useState(false);

  return (
    <div className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] p-3">
      <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">{toSupplyLabel(shortage.ingredient)}</p>
      {shortage.quantity_in_stock !== undefined && (
        <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">
          {shortage.quantity_in_stock}{shortage.unit} in stock, vs {shortage.reorder_threshold}{shortage.unit} threshold
        </p>
      )}
      {shortage.recommended_restock_qty !== undefined && (
        <p className="mt-1 text-[12px] font-medium" style={{ color: "var(--color-accent)" }}>
          Restock {shortage.recommended_restock_qty}{shortage.unit}
        </p>
      )}
      {shortage.reason && <p className="mt-0.5 text-[11px] text-[var(--color-text-soft)]">{shortage.reason}</p>}

      <div className="mt-2 flex flex-wrap gap-1.5">
        <button
          onClick={() => setShowInstamartModal(true)}
          className="hero-instamart-btn inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11.5px] font-semibold text-[var(--color-text-primary)] shadow-sm transition-transform hover:-translate-y-px"
        >
          <ChannelIcon channel="instamart" className="h-4 w-4" />
          Check Supply Price
        </button>
        <button
          onClick={() => setShowVendorPicker(true)}
          className="hero-whatsapp-btn inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-semibold text-[var(--color-text-primary)] shadow-sm transition-transform hover:-translate-y-px"
        >
          <ChannelIcon channel="whatsapp" className="h-4 w-4" />
          Message Supplier
        </button>
      </div>

      {showInstamartModal && (
        <InstamartPriceModal
          initialQuery={shortage.ingredient}
          onClose={() => setShowInstamartModal(false)}
        />
      )}

      {showVendorPicker && (
        <VendorPickerModal
          ingredient={shortage.ingredient}
          context={{
            unit: shortage.unit,
            quantity_in_stock: shortage.quantity_in_stock,
            reorder_threshold: shortage.reorder_threshold,
            recommended_restock_qty: shortage.recommended_restock_qty,
            reason: shortage.reason,
          }}
          onClose={() => setShowVendorPicker(false)}
          onDrafted={(action) => { setShowVendorPicker(false); onDrafted?.(action); }}
        />
      )}
    </div>
  );
}

type ChannelTab = "all" | "instamart" | "whatsapp";
const CHANNEL_TABS: { key: ChannelTab; label: string }[] = [
  { key: "all", label: "All channels" },
  { key: "instamart", label: "Supply catalog" },
  { key: "whatsapp", label: "WhatsApp" },
];

export function ActionDetailsModal({
  action, busy, error, onClose, onApprove, onSwitchAction,
}: {
  action: ActionQueueItem;
  busy: boolean;
  error?: string;
  onClose: () => void;
  onApprove: (action: ActionQueueItem, messageOverride?: string) => void;
  /** Swaps the modal to show a different action in place -- e.g. a shortage
   * row's newly-drafted WhatsApp order, once a vendor is picked. Both
   * callers just do setDetailsAction(a). */
  onSwitchAction?: (action: ActionQueueItem) => void;
}) {
  const shortages = shortagesOf(action);
  const overstockItems = overstockOf(action);
  const isWhatsapp = action.category === "whatsapp_vendor_order";
  const [message, setMessage] = useState(String(action.payload.message_draft ?? ""));

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-[backdropIn_0.15s_ease_both]"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-2xl bg-[var(--color-surface-raised)] shadow-2xl animate-[modalIn_0.2s_ease-out_both]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border-soft)] bg-[var(--color-surface-raised)] px-6 py-4">
          <div className="flex items-center gap-3">
            <span
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm"
              style={{ background: "linear-gradient(135deg, var(--color-accent), #ffab5e)" }}
            >
              <InfoIcon className="h-4 w-4" />
            </span>
            <div>
              <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-accent)]">
                {CATEGORY_LABELS[action.category] ?? "Action"}
              </p>
              <p className="mt-0.5 text-[15px] font-bold leading-tight text-[var(--color-text-primary)]">{action.title}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-full p-1.5 text-[var(--color-text-faint)] transition-colors hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-text-primary)]"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
        {isWhatsapp && (
          <>
            <p className="mt-1 text-[11.5px] text-[var(--color-text-faint)]">
              To: {String(action.payload.vendor ?? "Vendor")}
            </p>
            <p className="mt-2 text-[10.5px] uppercase tracking-wide text-[var(--color-text-faint)]">
              Drafted message — edit before sending
            </p>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              className="mt-1.5 w-full resize-none rounded-xl bg-[#dcf8c6] p-3 text-[13px] leading-snug text-[#111] outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            />
          </>
        )}

        {action.category === "restock_alert" && shortages.length > 0 && (
          <div className="mt-3 max-h-80 space-y-3 overflow-y-auto">
            {shortages.map((s) => (
              <ShortageRow key={s.ingredient} shortage={s} onDrafted={onSwitchAction} />
            ))}
          </div>
        )}

        {action.category === "pricing_promo_review" && (
          <p className="mt-2 text-[12px] text-[var(--color-text-soft)]">
            {String(action.payload.area_deals_count ?? 0)} area deal(s) live tonight while occupancy is high.
          </p>
        )}

        {action.category === "overstock_alert" && overstockItems.length > 0 && (
          <div className="mt-3 max-h-80 space-y-3 overflow-y-auto">
            {overstockItems.map((o) => (
              <div key={o.ingredient} className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] p-3">
                <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">{toSupplyLabel(o.ingredient)}</p>
                {o.quantity_in_stock !== undefined && (
                  <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">
                    {o.quantity_in_stock}{o.unit} in stock — {o.excess}{o.unit} more than usual
                  </p>
                )}
                {o.reason && <p className="mt-1 text-[11.5px] text-[var(--color-text-soft)]">{o.reason}</p>}
              </div>
            ))}
          </div>
        )}

        {error && (
          <p className="mt-2 text-[11px]" style={{ color: "var(--color-caution)" }}>Couldn&apos;t send: {error}</p>
        )}
        </div>

        <div className="flex justify-end gap-2 border-t border-[var(--color-border-soft)] bg-[var(--color-surface-sunken)] px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-[12px] font-semibold text-[var(--color-text-faint)] transition-colors hover:text-[var(--color-text-primary)]"
          >
            Cancel
          </button>
          <button
            onClick={() => onApprove(action, isWhatsapp ? message : undefined)}
            disabled={busy || (isWhatsapp && !message.trim())}
            className="btn-primary rounded-lg px-4 py-2 text-[12px] font-semibold disabled:opacity-50"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ActionQueuePanel({
  actions: controlledActions,
  onActionTaken,
  emptyMessage,
}: {
  actions?: ActionQueueItem[];
  onActionTaken?: () => void;
  emptyMessage?: string;
} = {}) {
  const [actions, setActions] = useState<ActionQueueItem[]>(controlledActions ?? []);
  const [loaded, setLoaded] = useState(!!controlledActions);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [detailsAction, setDetailsAction] = useState<ActionQueueItem | null>(null);
  const [actionErrors, setActionErrors] = useState<Record<number, string>>({});
  const [channelTab, setChannelTab] = useState<ChannelTab>("all");

  // Uncontrolled mode (e.g. /planning): self-fetch pending actions once.
  useEffect(() => {
    if (controlledActions) return;
    getActionQueue("pending")
      .then((data) => { setActions(data); setLoadError(null); })
      .catch((err) => { console.error("Action Queue load failed:", err); setLoadError(err instanceof Error ? err.message : "Failed to load."); })
      .finally(() => setLoaded(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Controlled mode (Action Center): mirror whatever the parent already fetched.
  useEffect(() => {
    if (controlledActions) {
      setActions(controlledActions);
      setLoaded(true);
    }
  }, [controlledActions]);

  const handleApprove = async (action: ActionQueueItem, messageOverride?: string) => {
    setBusyId(action.id);
    try {
      // For whatsapp_vendor_order actions, approving is also what triggers the
      // real Twilio send (P6-A9) -- a 200 response doesn't guarantee the send
      // itself succeeded, so check the returned error field explicitly rather
      // than treating any non-throwing response as success.
      const result = await approveAction(action.id, messageOverride);
      if (result.error) {
        setActionErrors((prev) => ({ ...prev, [action.id]: result.error! }));
      } else {
        setActions((prev) => prev.filter((a) => a.id !== action.id));
        setActionErrors((prev) => {
          const next = { ...prev };
          delete next[action.id];
          return next;
        });
        onActionTaken?.();
      }
    } catch (err) {
      setActionErrors((prev) => ({ ...prev, [action.id]: err instanceof Error ? err.message : "Approve failed." }));
    } finally {
      setBusyId(null);
      setDetailsAction(null);
    }
  };

  const handleReject = async (action: ActionQueueItem) => {
    setBusyId(action.id);
    try {
      await rejectAction(action.id);
      setActions((prev) => prev.filter((a) => a.id !== action.id));
      onActionTaken?.();
    } catch {
      // leave the item in the list on failure
    } finally {
      setBusyId(null);
    }
  };

  const channelCounts = useMemo(() => {
    const c: Record<ChannelTab, number> = { all: actions.length, instamart: 0, whatsapp: 0 };
    for (const a of actions) {
      const ch = channelOf(a);
      if (ch) c[ch] += 1;
    }
    return c;
  }, [actions]);

  const visibleActions = channelTab === "all" ? actions : actions.filter((a) => channelOf(a) === channelTab);

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-[15px] font-bold text-[var(--color-text-primary)]">
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4 text-[var(--color-text-primary)]" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Action Queue
          </p>
          <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">Recommendations awaiting your approval</p>
        </div>
        {actions.length > 0 && (
          <span
            className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold"
            style={{ background: "var(--color-caution-soft)", color: "var(--color-caution)" }}
          >
            {actions.length} pending
          </span>
        )}
      </div>

      {loaded && !loadError && actions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {CHANNEL_TABS.map((tab) => (
            <FilterChip key={tab.key} active={channelTab === tab.key} onClick={() => setChannelTab(tab.key)}>
              {tab.key !== "all" && <ChannelIcon channel={tab.key} className="h-3.5 w-3.5" />}
              {tab.label}
              <span className={channelTab === tab.key ? "text-white/80" : "text-[var(--color-text-ghost)]"}>
                {channelCounts[tab.key]}
              </span>
            </FilterChip>
          ))}
        </div>
      )}

      {!loaded ? (
        <p className="mt-4 text-[11px] text-[var(--color-text-faint)]">Loading…</p>
      ) : loadError ? (
        <p className="mt-4 text-[11px]" style={{ color: "var(--color-caution)" }}>Couldn&apos;t load the Action Queue ({loadError}).</p>
      ) : actions.length === 0 ? (
        <p className="mt-4 text-[11px] text-[var(--color-text-faint)]">{emptyMessage ?? "Nothing waiting for approval right now."}</p>
      ) : visibleActions.length === 0 ? (
        <p className="mt-4 text-[11px] text-[var(--color-text-faint)]">
          Nothing via {channelTab === "instamart" ? "supply catalog" : "supplier messaging"} right now.
        </p>
      ) : (
        <div className="mt-4 space-y-2.5">
          {visibleActions.map((action) => {
            const shortages = shortagesOf(action);
            const overstockItems = overstockOf(action);
            const subtitle =
              shortages.length === 1
                ? `${shortages[0].quantity_in_stock ?? "?"}${shortages[0].unit ?? ""} vs ${shortages[0].reorder_threshold ?? "?"}${shortages[0].unit ?? ""} threshold`
                : shortages.length > 1
                ? `${shortages.length} supply items below threshold`
                : overstockItems.length === 1
                ? `${overstockItems[0].quantity_in_stock ?? "?"}${overstockItems[0].unit ?? ""} in stock, ${overstockItems[0].excess ?? "?"}${overstockItems[0].unit ?? ""} over usual`
                : overstockItems.length > 1
                ? `${overstockItems.length} supply items overstocked`
                : null;

            const tone = CATEGORY_TONE[action.category] ?? "var(--color-text-faint)";
            return (
              <div
                key={action.id}
                className="group relative overflow-hidden rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-3.5 pl-5 pr-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: tone }} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className="inline-flex h-3 items-center gap-1 text-[10px] font-bold uppercase leading-3 tracking-wide"
                      style={{ color: tone }}
                    >
                      {CATEGORY_LABELS[action.category] ?? action.category}
                      <CategoryIcon category={action.category} className="h-3 w-3 shrink-0" />
                    </span>
                    <ChannelIcon channel={channelOf(action)} className="h-3.5 w-3.5" />
                    {action.approval_streak > 0 && (
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                        style={{ background: "var(--color-good-soft)", color: "var(--color-good)" }}
                        title={`You've approved ${CATEGORY_LABELS[action.category] ?? action.category} ${action.approval_streak} time${action.approval_streak !== 1 ? "s" : ""} in a row`}
                      >
                        Approved {action.approval_streak}x in a row
                      </span>
                    )}
                  </div>

                  <div className="mt-1 flex items-center justify-between gap-3">
                    <p className="min-w-0 truncate text-[13px] font-semibold text-[var(--color-text-primary)]">{action.title}</p>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        onClick={() => setDetailsAction(action)}
                        className="btn-primary inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-[12px] font-semibold"
                      >
                        <InfoIcon className="h-3 w-3" />
                        Review
                      </button>
                      <button
                        onClick={() => handleReject(action)}
                        disabled={busyId === action.id}
                        className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-[12px] font-semibold text-[var(--color-text-soft)] transition-colors hover:border-[var(--color-text-faint)] hover:text-[var(--color-text-primary)] disabled:opacity-50"
                      >
                        <XIcon className="h-3 w-3" />
                        Dismiss
                      </button>
                    </div>
                  </div>

                  {subtitle && <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">{subtitle}</p>}
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span className="rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-soft)]">
                      {AGENT_LABELS[action.category] ?? "Agent"}
                    </span>
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                      style={{ background: "var(--color-caution-soft)", color: "var(--color-caution)" }}
                    >
                      {priorityLabel(action)}
                    </span>
                  </div>
                </div>
                {actionErrors[action.id] && (
                  <p className="mt-2 text-[11px]" style={{ color: "var(--color-caution)" }}>
                    Couldn&apos;t send: {actionErrors[action.id]}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {detailsAction && (
        <ActionDetailsModal
          key={detailsAction.id}
          action={detailsAction}
          busy={busyId === detailsAction.id}
          error={actionErrors[detailsAction.id]}
          onClose={() => setDetailsAction(null)}
          onApprove={handleApprove}
          onSwitchAction={setDetailsAction}
        />
      )}
    </div>
  );
}

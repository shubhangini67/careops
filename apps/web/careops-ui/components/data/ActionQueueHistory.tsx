"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getActionQueue, type ActionQueueItem } from "@/lib/api";
import Badge from "@/components/ui/Badge";
import { relativeTime } from "@/lib/formatters";
import {
  AlertTriangleIcon, CATEGORY_LABELS, CATEGORY_TONE, ChannelIcon, CheckIcon, FilterChip, HourglassIcon, XIcon, channelOf,
} from "@/components/actioncenter/actionQueueMeta";

export type StatusTab = "all" | "pending" | "approved" | "executed" | "failed" | "rejected" | "expired";
type ChannelTab = "all" | "instamart" | "whatsapp";

const PREVIEW_LIMIT = 5;

// "Approved" has no dedicated filter chip here either -- same reasoning as
// ActionQueueStats: it only ever means a recommendation-tier action
// (restock_alert/pricing_promo_review) with no real content or side effect
// to review, and a failed WhatsApp send is already reclassified as "failed"
// by displayStatus() below, never showing up as a plain "approved" row.
// Any recommendation that does get manually approved still shows up under
// "All" with an honest "Approved" badge on its row -- it just isn't worth
// its own tab.
const TABS: { key: StatusTab; label: string; dot: string }[] = [
  { key: "all", label: "All", dot: "bg-[var(--color-text-faint)]" },
  { key: "pending", label: "Pending", dot: "bg-amber-400" },
  { key: "executed", label: "Executed", dot: "bg-emerald-400" },
  { key: "failed", label: "Failed", dot: "bg-rose-400" },
  { key: "rejected", label: "Rejected", dot: "bg-rose-400" },
  { key: "expired", label: "Expired", dot: "bg-rose-400" },
];

// No "all channels" chip -- clicking the active one again resets to "all"
// instead of needing a separate reset button.
const CHANNEL_TABS: { key: Exclude<ChannelTab, "all">; label: string }[] = [
  { key: "instamart", label: "Supply catalog" },
  { key: "whatsapp", label: "WhatsApp" },
];

const STATUS_TONE: Record<string, string> = {
  pending: "var(--color-caution)",
  approved: "var(--color-good)",
  executed: "var(--color-good)",
  failed: "var(--color-critical)",
  rejected: "var(--color-critical)",
  expired: "var(--color-critical)",
};

// Icon badge fill is a faint tint, not the solid tone -- the icon itself
// (colored, not white-on-solid) is what should read first, the fill just
// gives it a bit of a resting plate.
const STATUS_TONE_SOFT: Record<string, string> = {
  pending: "var(--color-caution-soft)",
  approved: "var(--color-good-soft)",
  executed: "var(--color-good-soft)",
  failed: "var(--color-critical-soft)",
  rejected: "var(--color-critical-soft)",
  expired: "var(--color-critical-soft)",
};

type ResolvedStatus = Exclude<StatusTab, "all">;

/** An approved whatsapp_vendor_order whose real Twilio send failed stays at
 * status "approved" with an error attached -- indistinguishable from a
 * healthy restock/pricing recommendation you'd simply acknowledged, unless
 * this display-only "failed" bucket is split out. */
function displayStatus(action: ActionQueueItem): ResolvedStatus {
  if (action.status === "approved" && action.error) return "failed";
  return action.status as ResolvedStatus;
}

function StatusGlyph({ status }: { status: ResolvedStatus }) {
  const cls = "h-3 w-3";
  if (status === "approved" || status === "executed") return <CheckIcon className={cls} strokeWidth={2.8} />;
  if (status === "failed") return <AlertTriangleIcon className={cls} strokeWidth={2.2} />;
  if (status === "rejected" || status === "expired") return <XIcon className={cls} strokeWidth={2.8} />;
  return <HourglassIcon className={cls} strokeWidth={2.2} />;
}

function HistoryRow({ action, isLast }: { action: ActionQueueItem; isLast: boolean }) {
  const status = displayStatus(action);
  const tone = STATUS_TONE[status] ?? "var(--color-text-faint)";
  const soft = STATUS_TONE_SOFT[status] ?? "var(--color-surface-sunken)";
  const timestamp = action.executed_at ?? action.created_at;
  return (
    <div className="group relative flex items-start gap-3 rounded-xl px-2 py-2.5 transition-colors hover:bg-[var(--color-surface-sunken)]">
      {!isLast && (
        <span className="absolute left-[19px] top-8 bottom-0 w-px bg-[var(--color-border-soft)]" />
      )}
      <span
        className="z-10 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
        style={{ background: soft, color: tone }}
      >
        <StatusGlyph status={status} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold" style={{ color: CATEGORY_TONE[action.category] ?? "var(--color-text-faint)" }}>
              {CATEGORY_LABELS[action.category] ?? action.category}
            </span>
            <ChannelIcon channel={channelOf(action)} className="h-3.5 w-3.5" />
            <Badge variant={status} />
          </div>
          {timestamp && (
            <span className="shrink-0 text-[11px] text-[var(--color-text-faint)]" title={new Date(timestamp).toLocaleString()}>
              {relativeTime(timestamp)}
            </span>
          )}
        </div>
        <p className="mt-1 truncate text-[13px] font-semibold text-[var(--color-text-primary)]">{action.title}</p>
        {action.error && (
          <p className="mt-0.5 text-[11px]" style={{ color: "var(--color-caution)" }}>{action.error}</p>
        )}
      </div>
    </div>
  );
}

export default function ActionQueueHistory({
  actions: controlledActions,
  activeTab: controlledTab,
  onTabChange,
  open: controlledOpen,
  onOpenChange,
}: {
  actions?: ActionQueueItem[];
  activeTab?: StatusTab;
  onTabChange?: (tab: StatusTab) => void;
  /** Collapsed by default -- History is a record most people only check
   * occasionally, so it shouldn't cost half the page's width/height by
   * default. Controllable from outside (e.g. a stat card jumping straight
   * to a pre-filtered, expanded view) or left to manage its own state. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
} = {}) {
  const [actions, setActions] = useState<ActionQueueItem[]>(controlledActions ?? []);
  const [loaded, setLoaded] = useState(!!controlledActions);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [internalTab, setInternalTab] = useState<StatusTab>("all");
  const [channelTab, setChannelTab] = useState<ChannelTab>("all");
  const [showAll, setShowAll] = useState(false);
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
  const [internalOpen, setInternalOpen] = useState(false);
  const statusMenuRef = useRef<HTMLDivElement>(null);

  const activeTab = controlledTab ?? internalTab;
  const setActiveTab = onTabChange ?? setInternalTab;
  const isOpen = controlledOpen ?? internalOpen;
  const setIsOpen = onOpenChange ?? setInternalOpen;

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (statusMenuRef.current && !statusMenuRef.current.contains(e.target as Node)) setStatusMenuOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Uncontrolled fallback -- self-fetch every status, newest first.
  useEffect(() => {
    if (controlledActions) return;
    getActionQueue()
      .then((data) => { setActions(data); setLoadError(null); })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load."))
      .finally(() => setLoaded(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (controlledActions) {
      setActions(controlledActions);
      setLoaded(true);
    }
  }, [controlledActions]);

  const counts = useMemo(() => {
    const c: Record<StatusTab, number> = { all: actions.length, pending: 0, approved: 0, executed: 0, failed: 0, rejected: 0, expired: 0 };
    for (const a of actions) c[displayStatus(a)] += 1;
    return c;
  }, [actions]);

  const channelCounts = useMemo(() => {
    const c: Record<ChannelTab, number> = { all: actions.length, instamart: 0, whatsapp: 0 };
    for (const a of actions) {
      const ch = channelOf(a);
      if (ch) c[ch] += 1;
    }
    return c;
  }, [actions]);

  const visible = actions
    .filter((a) => activeTab === "all" || displayStatus(a) === activeTab)
    .filter((a) => channelTab === "all" || channelOf(a) === channelTab);
  const displayed = visible.slice(0, PREVIEW_LIMIT);
  const hasMore = visible.length > PREVIEW_LIMIT;

  return (
    <div className="card p-6">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <div>
          <p className="flex items-center gap-2 text-[15px] font-bold text-[var(--color-text-primary)]">
            <HourglassIcon className="h-4 w-4 text-[var(--color-text-primary)]" />
            History
          </p>
          <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">
            {isOpen ? "See everything you've approved, rejected, or completed. Filter it by status below." : "See everything you've approved, rejected, or completed."}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {actions.length > 0 && (
            <span className="rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-2.5 py-1 text-[11px] text-[var(--color-text-faint)]">
              {actions.length} total
            </span>
          )}
          <svg
            viewBox="0 0 24 24" fill="none"
            className={`h-4 w-4 text-[var(--color-text-faint)] transition-transform ${isOpen ? "rotate-90" : ""}`}
            stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </button>

      {isOpen && loaded && !loadError && actions.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <div ref={statusMenuRef} className="relative inline-block">
            <button
              type="button"
              onClick={() => setStatusMenuOpen((v) => !v)}
              className="flex items-center gap-2 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-[11.5px] font-semibold text-[var(--color-text-primary)] shadow-sm"
            >
              <span className={`h-1.5 w-1.5 rounded-full ${TABS.find((t) => t.key === activeTab)?.dot ?? ""}`} />
              {TABS.find((t) => t.key === activeTab)?.label ?? "All"}
              <span className="text-[var(--color-text-faint)]">{counts[activeTab]}</span>
              <svg
                viewBox="0 0 24 24" fill="none"
                className={`h-3.5 w-3.5 text-[var(--color-text-ghost)] transition-transform ${statusMenuOpen ? "rotate-180" : ""}`}
                stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {statusMenuOpen && (
              <div className="absolute z-20 mt-1.5 w-48 overflow-hidden rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-1.5 shadow-lg">
                {TABS.map((tab) => {
                  const active = activeTab === tab.key;
                  return (
                    <button
                      key={tab.key}
                      type="button"
                      onClick={() => { setActiveTab(tab.key); setStatusMenuOpen(false); }}
                      className={`flex w-full items-center justify-between gap-3 px-3.5 py-2 text-left text-[13px] transition-colors ${
                        active
                          ? "bg-[var(--color-accent-soft)] font-semibold text-[var(--color-text-primary)]"
                          : "text-[var(--color-text-soft)] hover:bg-[var(--color-surface-sunken)]"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <span className={`h-1.5 w-1.5 rounded-full ${tab.dot}`} />
                        {tab.label}
                      </span>
                      <span className="text-[var(--color-text-faint)]">{counts[tab.key]}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {CHANNEL_TABS.map((tab) => (
            <FilterChip
              key={tab.key}
              active={channelTab === tab.key}
              onClick={() => setChannelTab(channelTab === tab.key ? "all" : tab.key)}
            >
              <ChannelIcon channel={tab.key} className="h-3.5 w-3.5" />
              {tab.label}
              <span className={channelTab === tab.key ? "text-white/80" : "text-[var(--color-text-ghost)]"}>
                {channelCounts[tab.key]}
              </span>
            </FilterChip>
          ))}
        </div>
      )}

      {!isOpen ? null : !loaded ? (
        <p className="mt-4 text-[11px] text-[var(--color-text-faint)]">Loading…</p>
      ) : loadError ? (
        <p className="mt-4 text-[11px]" style={{ color: "var(--color-caution)" }}>Couldn&apos;t load Action Queue history ({loadError}).</p>
      ) : actions.length === 0 ? (
        <p className="mt-4 text-[11px] text-[var(--color-text-faint)]">No actions recorded yet.</p>
      ) : visible.length === 0 ? (
        <p className="mt-4 text-[11px] text-[var(--color-text-faint)]">
          No {activeTab === "all" ? "" : `${activeTab} `}actions{channelTab === "all" ? "" : ` via ${channelTab === "instamart" ? "supply catalog" : "supplier messaging"}`}.
        </p>
      ) : (
        <>
          <div className="mt-4">
            {displayed.map((action, idx) => (
              <HistoryRow key={action.id} action={action} isLast={idx === displayed.length - 1} />
            ))}
          </div>
          {hasMore && (
            <button
              onClick={() => setShowAll(true)}
              className="mt-1 w-full rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-2 text-[12px] font-semibold text-[var(--color-text-soft)] shadow-sm transition-colors hover:border-[var(--color-text-faint)] hover:text-[var(--color-text-primary)]"
            >
              View All ({visible.length})
            </button>
          )}
        </>
      )}

      {showAll && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowAll(false)}>
          <div
            className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[var(--color-surface-raised)] p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <p className="text-[14px] font-bold text-[var(--color-text-primary)]">
                History — {visible.length} action{visible.length !== 1 ? "s" : ""}
              </p>
              <button
                onClick={() => setShowAll(false)}
                className="rounded-lg px-3 py-1.5 text-[12px] font-semibold text-[var(--color-text-faint)] hover:text-[var(--color-text-primary)]"
              >
                Close
              </button>
            </div>
            {visible.map((action, idx) => (
              <HistoryRow key={action.id} action={action} isLast={idx === visible.length - 1} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

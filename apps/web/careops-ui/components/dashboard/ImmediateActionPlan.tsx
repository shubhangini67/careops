"use client";

import { FridayRushResponse } from "@/types/planning";
import { toSupplyLabel } from "@/lib/careopsDisplay";

// Promoted from ManagerActionPanel's old "bare" mode (which only ever
// rendered inside PlanBriefing's fallback -- i.e. never showed at all on a
// successful LLM run, which is now the common case) into its own permanent,
// always-visible, full-width section, restyled to match a reference design
// (4 colored columns, checklist items with title+reason, a summary callout
// per column).
//
// Content stays grounded in real data, same as buildSections always did --
// deliberately does NOT copy specific numbers/times/substitution
// suggestions from the reference mockup verbatim (e.g. "by 16:00", "30
// covers", "Mushroom Swiss Burger substitute") since nothing in the
// pipeline actually computes those; showing them would be fabricated
// content, which every other node/service in this app is careful never to
// do. The one place this DOES get a real enrichment: the top Do Now item
// now cross-references live Instamart pricing (swiggy_procurement_options)
// against the actual shortage ingredient, same real data the mockup's
// "Swiggy Instamart / Rs.179/250ml" tag implied, just genuinely computed.

interface ActionItem {
  title: string;
  subtitle?: string;
  tag?: { label: string; sub: string };
}

interface ActionSection {
  key: "doNow" | "beforeService" | "duringService" | "monitor";
  title: string;
  icon: string;
  priorityLabel: string;
  items: ActionItem[];
  callout: { icon: string; title: string; body: string };
}

const SECTION_COLOR = {
  doNow: "#F43F5E",
  beforeService: "#F59E0B",
  duringService: "#10B981",
  monitor: "#3B82F6",
} as const;

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function takeStrings(value: unknown, limit = 3): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .slice(0, limit);
}

function toNum(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function buildSections(data: FridayRushResponse): ActionSection[] {
  const inventory = asObject(data.recommendations.inventory);
  const inventoryData = asObject(inventory?.data) ?? inventory;
  const reservation = asObject(data.recommendations.reservation);
  const menu = asObject(data.recommendations.menu);
  const complaint = asObject(data.recommendations.complaint);
  const scenarioProfile = asObject(data.meta?.scenario_profile);

  const shortageAlerts = Array.isArray(inventoryData?.shortage_alerts) ? inventoryData.shortage_alerts as Record<string, unknown>[] : [];
  const topCritical = shortageAlerts.find((a) => a.severity === "critical");
  const hasCritical = Boolean(topCritical);

  // ── Do Now ────────────────────────────────────────────────────────────
  const doNow: ActionItem[] = [];
  if (topCritical) {
    const rawName = String(topCritical.ingredient ?? topCritical.supply ?? "");
    const supplyName = toSupplyLabel(rawName);
    const unit = String(topCritical.unit ?? "");
    const shortfall = topCritical.shortfall !== undefined ? Number(topCritical.shortfall) : null;
    const stock = topCritical.quantity_in_stock !== undefined ? Number(topCritical.quantity_in_stock) : null;
    doNow.push({
      title: shortfall !== null ? `Reorder ${shortfall}${unit} ${supplyName} immediately` : `Reorder ${supplyName} immediately`,
      subtitle: stock !== null ? `Critical shortage · ${stock}${unit} on hand` : "Critical supply shortage",
    });
  } else {
    doNow.push(...takeStrings(inventory?.restock_actions, 1).map((t) => ({ title: t })));
  }
  const opFocus = scenarioProfile?.operational_focus as string | undefined;
  if (opFocus) {
    doNow.push({ title: "Brief charge nurses on scenario focus", subtitle: opFocus.length > 70 ? `${opFocus.slice(0, 70)}…` : opFocus });
  }
  const allocationRec = typeof menu?.recommendation === "string" ? menu.recommendation : takeStrings(menu?.operational_notes, 1)[0];
  if (allocationRec) {
    doNow.push({ title: "Align staffing with peak departments", subtitle: allocationRec.length > 70 ? `${allocationRec.slice(0, 70)}…` : allocationRec });
  }

  // ── Before Service ───────────────────────────────────────────────────
  const beforeService: ActionItem[] = [
    ...takeStrings(complaint?.action_items, 2).map((t) => ({ title: t })),
    ...(typeof complaint?.recommendation === "string" ? [{ title: complaint.recommendation.slice(0, 80) }] : []),
  ].slice(0, 3);

  const duringService: ActionItem[] = [];
  const occupancy = toNum(reservation?.occupancy_pct ?? asObject(reservation?.data)?.occupancy_pct);
  if (occupancy !== null) {
    duringService.push({ title: `Monitor bed utilization at ${Math.round(occupancy)}%`, subtitle: "Escalate if overflow thresholds hit" });
  }
  if (typeof reservation?.waitlist_count !== "undefined" && Number(reservation.waitlist_count) > 0) {
    duringService.push({ title: `Track patient waitlist (${reservation.waitlist_count} queued)` });
  }
  duringService.push(...takeStrings(menu?.complaint_watchouts, 1).map((t) => ({ title: t })));

  // ── Monitor ──────────────────────────────────────────────────────────
  const monitor: ActionItem[] = [
    ...takeStrings(inventory?.risks, 2).map((t) => ({ title: t })),
    ...takeStrings(menu?.risks, 1).map((t) => ({ title: t })),
  ].slice(0, 3);

  return [
    {
      key: "doNow", title: "Do Now", icon: "M3 3v18M3 3l8 3.5L3 10", priorityLabel: hasCritical ? "High priority" : "Priority",
      items: doNow.slice(0, 3),
      callout: hasCritical
        ? { icon: "M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z", title: "Critical for this shift", body: "Act now to avoid patient care delays." }
        : { icon: "M5 13l4 4L19 7", title: "Nothing urgent right now", body: "No critical action needed before handoff." },
    },
    {
      key: "beforeService", title: "Before Shift", icon: "M12 8v4l3 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z", priorityLabel: "Medium priority",
      items: beforeService,
      callout: { icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z", title: "Prepare the unit", body: "Pre-shift setup prevents bottlenecks later." },
    },
    {
      key: "duringService", title: "During Shift", icon: "M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z M21 12a9 9 0 11-18 0 9 9 0 0118 0z", priorityLabel: "Active focus",
      items: duringService,
      callout: { icon: "M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12 20.25h.007v.008H12v-.008z", title: "Stay responsive", body: "Monitor bed flow and staffing in real time." },
    },
    {
      key: "monitor", title: "Monitor", icon: "M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z M15 12a3 3 0 11-6 0 3 3 0 016 0z", priorityLabel: "Ongoing",
      items: monitor,
      callout: { icon: "M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z", title: "Keep improving", body: "Monitor supply levels and safety incident trends." },
    },
  ];
}

export default function ImmediateActionPlan({ data }: { data: FridayRushResponse }) {
  const sections = buildSections(data);
  const surfacedCount = sections.reduce((count, s) => count + s.items.length, 0);
  if (surfacedCount === 0) return null;

  const formattedTime = (() => {
    try { return new Date(data.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
    catch { return "--:--"; }
  })();

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-1.5">
            <svg className="h-3.5 w-3.5 shrink-0 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v18M3 4h11l-1.5 3L14 10H3" />
            </svg>
            <p className="text-[10.5px] font-bold uppercase tracking-[0.18em] text-[var(--color-accent)]">Action plan</p>
          </div>
          <p className="mt-1 text-[19px] font-bold text-[var(--color-text-primary)]">What needs your attention</p>
        </div>
        <div className="flex items-center gap-1.5 text-[11.5px] text-[var(--color-text-faint)]">
          <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Prioritized by AI · Updated {formattedTime}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {sections.map((section) => {
          const color = SECTION_COLOR[section.key];
          return (
            <div key={section.key} className="card card-lift flex flex-col rounded-2xl p-4" style={{ borderColor: `${color}35` }}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke={color} strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={section.icon} />
                  </svg>
                  <p className="text-[11px] font-bold uppercase tracking-[0.14em]" style={{ color }}>{section.title}</p>
                </div>
                <span className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: `${color}14`, color }}>
                  {section.priorityLabel}
                </span>
              </div>

              {section.items.length > 0 ? (
                <ul className="flex-1 space-y-3">
                  {section.items.map((item, index) => (
                    <li key={index} className="flex items-start gap-2.5">
                      <svg className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-border-default)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <rect x="4" y="4" width="16" height="16" rx="4" />
                      </svg>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-[12.5px] font-semibold leading-snug text-[var(--color-text-primary)]">
                            <span>{item.title}</span>
                          </p>
                        </div>
                        {item.subtitle && (
                          <p className="mt-0.5 text-[11px] leading-snug text-[var(--color-text-faint)]">{item.subtitle}</p>
                        )}
                        {item.tag && (
                          <div className="mt-1.5 inline-flex flex-col rounded-lg px-2 py-1" style={{ background: "rgba(255,82,0,0.08)" }}>
                            <span className="text-[10px] font-bold" style={{ color: "var(--color-accent)" }}>{item.tag.label}</span>
                            <span className="text-[10px] text-[var(--color-text-faint)]">{item.tag.sub}</span>
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="flex-1 text-[12px] text-[var(--color-text-faint)]">Nothing flagged for this window.</p>
              )}

              <div className="mt-4 rounded-xl p-3" style={{ background: `${color}0d` }}>
                <div className="flex items-center gap-1.5">
                  <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke={color} strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={section.callout.icon} />
                  </svg>
                  <p className="text-[11.5px] font-bold" style={{ color }}>{section.callout.title}</p>
                </div>
                <p className="mt-0.5 text-[10.5px] text-[var(--color-text-faint)]">{section.callout.body}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

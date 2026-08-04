"use client";

import type { ReactNode, SVGProps } from "react";
import HighlightSwiggy from "./HighlightSwiggy";
import SwiggySignalBadge from "./SwiggySignalBadge";

// Shared visual system for every specialist agent's detail card (Forecast/
// Reservation/Inventory/Menu/Complaint): a header with an icon badge +
// serif title + context chips, a Recommendation panel (headline + priority
// pill + reasoning/risks side by side), an icon-circle stat grid, a
// priority gauge, and category columns with a colored takeaway callout.
// One literal implementation shared by all five cards, not five similar-
// but-different ones.

function Svg(props: SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...props} />;
}

export const ICONS = {
  lightbulb: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></Svg>,
  warning: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9.303 3.376c.866 1.5-.217 3.374-1.948 3.374H4.645c-1.73 0-2.813-1.874-1.948-3.374L10.652 4.5c.866-1.5 3.03-1.5 3.896 0l7.755 12.626zM12 15.75h.007v.008H12v-.008z" /></Svg>,
  star: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.562.562 0 00-.586 0L6.982 21.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" /></Svg>,
  tag: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z" /><path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6z" /></Svg>,
  noEntry: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" /></Svg>,
  shieldCheck: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></Svg>,
  cube: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" /></Svg>,
  trendUp: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.306a11.95 11.95 0 015.814-5.518l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941" /></Svg>,
  mapPin: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" /></Svg>,
  clock: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" /></Svg>,
  gauge: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9 9 0 100-18 9 9 0 000 18z" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 12l3.5-3.5M8 12a4 4 0 118 0" /></Svg>,
  chartBar: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" /></Svg>,
  chat: (p: SVGProps<SVGSVGElement>) => <Svg {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></Svg>,
};

// ---- Card header: icon badge + serif title + subtitle + context chips ----

export interface HeaderChip { icon: ReactNode; label: string; value: string }

export function CardHeader({
  icon, color, title, subtitle, chips,
}: {
  icon: ReactNode; color: string; title: string; subtitle: string; chips?: HeaderChip[];
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border-soft)] pb-4">
      <div className="flex items-start gap-3 min-w-0">
        <span
          className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-white shadow-sm"
          style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[20px] font-bold leading-tight text-[var(--color-text-primary)]" style={{ fontFamily: "var(--font-display)" }}>{title}</p>
          <p className="mt-0.5 text-[12.5px] text-[var(--color-text-faint)]">{subtitle}</p>
        </div>
      </div>
      {chips && chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-4">
          {chips.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-[var(--color-text-faint)]">{c.icon}</span>
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-wider text-[var(--color-text-faint)]">{c.label}</p>
                <p className="text-[12.5px] font-semibold text-[var(--color-text-primary)]">{c.value}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Icon-circle stat grid ----

export interface AgentStat {
  icon: ReactNode;
  iconColor: string;
  value: string;
  valueClass?: string;
  label: string;
  caption?: string;
}

export function StatCard({ icon, iconColor, value, valueClass, label, caption }: AgentStat) {
  return (
    <div className="rounded-2xl ring-1 ring-[var(--color-border-soft)] bg-[var(--color-surface-raised)] p-4">
      <span className="grid h-8 w-8 place-items-center rounded-full" style={{ background: `${iconColor}18`, color: iconColor }}>
        {icon}
      </span>
      <p className={`num-display mt-2.5 text-[26px] leading-none ${valueClass ?? "text-[var(--color-text-primary)]"}`}>{value}</p>
      <p className="mt-1.5 text-[12px] font-semibold text-[var(--color-text-primary)]">{label}</p>
      {caption && <p className="mt-0.5 text-[10.5px] leading-snug text-[var(--color-text-faint)]">{caption}</p>}
    </div>
  );
}

export function StatGrid({ stats }: { stats: AgentStat[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 @lg:grid-cols-4">
      {stats.map((s, i) => <StatCard key={i} {...s} />)}
    </div>
  );
}

// ---- Priority gauge ----

const GAUGE_COPY: Record<string, { word: string; color: string; desc: string }> = {
  critical: { word: "Critical", color: "#E11D48", desc: "Needs action now to avoid disrupting tonight's service." },
  high:     { word: "High",     color: "#F43F5E", desc: "Meaningful upside, worth acting on with some operational risk." },
  medium:   { word: "Medium",   color: "#F59E0B", desc: "Balanced opportunity with manageable operational risk." },
  low:      { word: "Low",      color: "#10B981", desc: "Low-stakes -- safe to action or leave for later." },
};

export function PriorityGauge({ priority }: { priority?: string }) {
  const copy = GAUGE_COPY[(priority ?? "medium").toLowerCase()] ?? GAUGE_COPY.medium;
  return (
    <div className="flex items-center justify-between gap-3 rounded-2xl px-4 py-3.5" style={{ background: `${copy.color}12`, border: `1px solid ${copy.color}30` }}>
      <div className="min-w-0">
        <p className="text-[9px] font-bold uppercase tracking-wider" style={{ color: copy.color }}>Overall priority</p>
        <p className="mt-0.5 text-[16px] font-bold" style={{ color: copy.color }}>{copy.word}</p>
        <p className="mt-0.5 text-[11px] leading-snug text-[var(--color-text-faint)]">{copy.desc}</p>
      </div>
      <ICONS.gauge className="h-7 w-7 shrink-0" style={{ color: copy.color }} strokeWidth={1.6} />
    </div>
  );
}

// ---- Recommendation panel: headline + priority pill, reasoning/risks side by side ----

const PRIORITY_PILL: Record<string, string> = {
  critical: "bg-rose-500/15 text-rose-600 dark:text-rose-300",
  high:   "bg-rose-500/15 text-rose-600 dark:text-rose-300",
  medium: "bg-amber-500/15 text-amber-600 dark:text-amber-300",
  low:    "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
};

export function PriorityPill({ priority }: { priority: string }) {
  const key = priority.toLowerCase();
  return (
    <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${PRIORITY_PILL[key] ?? PRIORITY_PILL.medium}`}>
      {priority} priority
    </span>
  );
}

export function RecommendationBlock({
  recommendation,
  reasoning,
  priority,
  risks,
}: {
  recommendation: string | null;
  reasoning?: string | null;
  priority?: string;
  risks?: string[];
}) {
  if (!recommendation && !reasoning) return null;

  return (
    <div className="rounded-2xl ring-1 ring-[var(--color-border-soft)] bg-[var(--color-surface-raised)] p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--color-accent)]">Recommendation</p>
        {priority && <PriorityPill priority={priority} />}
      </div>
      {recommendation && (
        <p className="mt-2 text-[17px] font-bold leading-snug text-[var(--color-text-primary)]">
          <HighlightSwiggy text={recommendation} />
        </p>
      )}

      {(reasoning || (risks && risks.length > 0)) && (
        <div className="mt-4 grid grid-cols-1 gap-4 border-t border-[var(--color-border-soft)] pt-4 @lg:grid-cols-2">
          {reasoning && (
            <div>
              <div className="flex items-center gap-1.5">
                <ICONS.lightbulb className="h-3.5 w-3.5 text-amber-500" strokeWidth={1.8} />
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-faint)]">Reasoning</p>
              </div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-text-soft)]">
                <HighlightSwiggy text={reasoning} />
              </p>
            </div>
          )}
          {risks && risks.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5">
                <ICONS.warning className="h-3.5 w-3.5 text-rose-500" strokeWidth={1.8} />
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-faint)]">Risks</p>
              </div>
              <ul className="mt-1.5 space-y-1.5">
                {risks.map((risk, i) => (
                  <li key={i} className="rounded-lg bg-rose-500/10 px-2.5 py-1.5 text-[11.5px] text-rose-600 dark:text-rose-300">
                    <HighlightSwiggy text={risk} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---- Section title (used for list-style breakdowns like Shortage Alerts,
// Best Sellers, Recurring Issues -- not the icon-header category columns) ----

export function SectionTitle({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <div className="mb-2.5 flex items-center justify-between">
      <p className="text-[11.5px] font-bold text-[var(--color-text-primary)]">{title}</p>
      {right}
    </div>
  );
}

// ---- Category column: icon header, item list, colored takeaway callout ----

const CATEGORY_TONE: Record<"good" | "warn" | "risk" | "info", { icon: string; item: string; callout: string }> = {
  good: { icon: "#10B981", item: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-200", callout: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-200" },
  warn: { icon: "#F59E0B", item: "bg-amber-500/10 text-amber-700 dark:text-amber-200",       callout: "bg-amber-500/10 text-amber-700 dark:text-amber-200" },
  risk: { icon: "#F43F5E", item: "bg-rose-500/10 text-rose-700 dark:text-rose-200",           callout: "bg-rose-500/10 text-rose-700 dark:text-rose-200" },
  info: { icon: "#8B5CF6", item: "bg-[var(--color-surface-sunken)] text-[var(--color-text-primary)]", callout: "bg-violet-500/10 text-violet-700 dark:text-violet-200" },
};

export function CategoryColumn({
  icon, label, items, tone, callout,
}: {
  icon: ReactNode; label: string; items: string[]; tone: "good" | "warn" | "risk" | "info"; callout?: string;
}) {
  if (items.length === 0) return null;
  const t = CATEGORY_TONE[tone];

  return (
    <div className="rounded-2xl ring-1 ring-[var(--color-border-soft)] bg-[var(--color-surface-raised)] p-4">
      <div className="flex items-center gap-1.5">
        <span style={{ color: t.icon }}>{icon}</span>
        <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: t.icon }}>{label}</p>
      </div>
      <div className="mt-3 space-y-1.5">
        {items.map((item, i) => (
          <div key={i} className={`rounded-lg px-2.5 py-2 text-[12px] font-medium leading-snug ${t.item}`}>
            <HighlightSwiggy text={item} />
          </div>
        ))}
      </div>
      {callout && (
        <p className={`mt-3 rounded-lg px-2.5 py-2 text-[11px] leading-snug ${t.callout}`}>{callout}</p>
      )}
    </div>
  );
}

// ---- Footer / sources line (kept for cards that still want a trailing
// fact below everything -- most now put Service window / Swiggy in the
// header chips instead) ----

export function CardFooter({ label, value, swiggySignal }: { label: string; value: string; swiggySignal?: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border-soft)] pt-3 text-[11px] text-[var(--color-text-faint)]">
      <span>{label} <span className="font-semibold text-[var(--color-text-soft)]">{value}</span></span>
      {swiggySignal && <SwiggySignalBadge signal={swiggySignal} />}
    </div>
  );
}

"use client";

// Analytics -- "how did WE do": internal business performance only. Market
// intelligence ("what's happening around us" -- weather/trends/compliance +
// Swiggy competitive intel) lives on its own top-level /market page now, so
// this page no longer duplicates any of that content, just links to it.
//
// P6-A32 real IA + visual pass: a dense 2-column dashboard (Business/Menu on
// the right, Customers/Operations stacked on the left, Inventory full-width
// below both) with a tab-style scroll-spy nav up top, instead of 5 separate
// full-width sections stacked one after another. A single day-toggle (7/14/30)
// genuinely governs every card -- channel split and complaint themes used to
// silently ignore it and always show a fixed window.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Area, AreaChart, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, ResponsiveContainer,
} from "recharts";
import RevenueTrendChart from "@/components/dashboard/RevenueTrendChart";
import MenuEngineeringMatrix from "@/components/dashboard/MenuEngineeringMatrix";
import {
  getBusinessPerformance, getInventorySnapshot,
  type BusinessPerformanceResponse, type InventorySnapshotResponse,
} from "@/lib/api";
import { mapVolumeLabel, toSafetyCategory, toSupplyLabel } from "@/lib/careopsDisplay";

// ── Icons (small, stroke-based, matching Sidebar.tsx's icon convention) ─────

function IconBusiness({ className = "h-4 w-4" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M3 21h18M6 21V10M12 21V3M18 21v14" /></svg>;
}
function IconCustomers({ className = "h-4 w-4" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m9-5.13a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm-16 0a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z" /></svg>;
}
function IconMenu({ className = "h-4 w-4" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.2" /></svg>;
}
function IconOperations({ className = "h-4 w-4" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>;
}
function IconInventory({ className = "h-4 w-4" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>;
}
function IconTrendUp({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>;
}
function IconWallet({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M21 12V7H5a2 2 0 010-4h14v4M3 5v14a2 2 0 002 2h16v-5M18 12a2 2 0 000 4h4v-4h-4z" /></svg>;
}
function IconHeart({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 21s-7.5-5.36-9.86-9.86C.7 8.06 2.1 5 5.2 4.3c2-.45 3.65.5 4.8 2.02C11.15 4.8 12.8 3.85 14.8 4.3c3.1.7 4.5 3.76 3.06 6.84C19.5 15.64 12 21 12 21z" /></svg>;
}
function IconClock({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 7v5l3.5 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
function IconTag({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5.586a1 1 0 01.707.293l7.414 7.414a1 1 0 010 1.414l-8.586 8.586a1 1 0 01-1.414 0L3.293 13.293A1 1 0 013 12.586V7a4 4 0 014-4z" /></svg>;
}
function IconSpeaker({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 010 14.14M16.24 7.76a5.5 5.5 0 010 8.48" /></svg>;
}
function IconCheck({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>;
}
function IconAlertTriangle({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" /></svg>;
}
function IconInfo({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25h.375c.207 0 .375.168.375.375v4.5m-.75-9h.008v.008h-.008V6.75zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
function IconBox({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>;
}
function IconStorefront({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M13 21v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4M3 9h18M4 9l1.5-5h13L20 9M4 9v9a2 2 0 002 2h12a2 2 0 002-2V9" /></svg>;
}
function IconDeliveryBag({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M6 7h12l1 13H5L6 7z" /><path strokeLinecap="round" strokeLinejoin="round" d="M9 10V6a3 3 0 016 0v4" /></svg>;
}

const SECTIONS = [
  { id: "business", label: "Operations", icon: <IconBusiness /> },
  { id: "customers", label: "Patients", icon: <IconCustomers /> },
  { id: "menu", label: "Departments", icon: <IconMenu /> },
  { id: "operations", label: "Throughput", icon: <IconOperations /> },
  { id: "inventory", label: "Supplies", icon: <IconInventory /> },
];

const COMPLAINT_ICONS: Record<string, React.ReactNode> = {
  "ED Wait Time": <IconClock />,
  "Wait Time": <IconClock />,
  "Care Quality": <IconMenu className="h-3.5 w-3.5" />,
  "Food Quality": <IconMenu className="h-3.5 w-3.5" />,
  "Supply Availability": <IconBox />,
  "Stock & Availability": <IconBox />,
  "Documentation Accuracy": <IconCheck />,
  Documentation: <IconCheck />,
  "Order Accuracy": <IconCheck />,
  "Billing & Value": <IconTag />,
  "Access & Value": <IconTag />,
  "Portion & Value": <IconTag />,
  "Facility Environment": <IconSpeaker />,
  Environment: <IconSpeaker />,
  Ambience: <IconSpeaker />,
};

// One square in a 2x2 "At a glance" stat grid -- icon badge, label, value
// stacked vertically, each tile a subtly tinted mini-card of its own.
function StatSquare({
  label, value, icon, iconColor, squareBg, borderColor,
}: {
  label: string; value: string; icon: React.ReactNode;
  iconColor?: string; squareBg?: string; borderColor?: string;
}) {
  return (
    <div
      className="rounded-xl border p-3"
      style={{ background: squareBg ?? "rgba(255,82,0,0.08)", borderColor: borderColor ?? "rgba(255,82,0,0.25)" }}
    >
      <span
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white shadow-sm"
        style={{ background: iconColor ?? "var(--color-accent)" }}
      >
        {icon}
      </span>
      <p className="mt-2 text-[10px] font-semibold leading-snug text-[var(--color-text-faint)]">{label}</p>
      <p className="mt-0.5 text-[17px] font-bold tracking-tight text-[var(--color-text-primary)]">{value}</p>
    </div>
  );
}

// Section color identity, matching the tab nav above -- reused on each
// card's header icon so the page reads as one connected colorful system,
// not a wall of identical white boxes.
const SECTION_COLOR = {
  // One warm family only (Swiggy orange / gold / brown) -- literal hex, not
  // var(--color-accent), since CardHeader appends an alpha suffix directly
  // to this string for its gradient (`${color}cc`), which only produces
  // valid CSS for a literal hex value.
  business: "#FF5200",
  customers: "#D97706",
  menu: "#92400E",
  operations: "#C2410C",
  inventory: "#A16207",
} as const;

function CardHeader({
  title, sub, icon, color,
}: { title: string; sub: string; icon?: React.ReactNode; color?: string }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      {icon && (
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm"
          style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
        >
          {icon}
        </span>
      )}
      <div className="min-w-0">
        <p className="text-[13.5px] font-bold text-[var(--color-text-primary)]">{title}</p>
        <p className="mt-0.5 text-[11px] text-[var(--color-text-faint)]">{sub}</p>
      </div>
    </div>
  );
}

function EmptyState({ text, height = 160 }: { text: string; height?: number }) {
  return (
    <div style={{ height }} className="flex items-center justify-center rounded-xl border border-dashed border-[var(--color-border-default)] text-center">
      <p className="max-w-xs text-xs text-[var(--color-text-faint)]">{text}</p>
    </div>
  );
}

export default function AnalyticsDetail() {
  const [businessPerf, setBusinessPerf] = useState<BusinessPerformanceResponse | null>(null);
  const [perfDays, setPerfDays] = useState(14);
  const [loaded, setLoaded] = useState(false);
  const [inventorySnapshot, setInventorySnapshot] = useState<InventorySnapshotResponse | null>(null);
  const [inventoryLoaded, setInventoryLoaded] = useState(false);
  const [activeId, setActiveId] = useState("business");

  useEffect(() => {
    let cancelled = false;
    getBusinessPerformance(perfDays)
      .then((perf) => { if (!cancelled) setBusinessPerf(perf); })
      .catch(() => { if (!cancelled) setBusinessPerf(null); })
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [perfDays]);

  useEffect(() => {
    let cancelled = false;
    getInventorySnapshot()
      .then((snap) => { if (!cancelled) setInventorySnapshot(snap); })
      .catch(() => { if (!cancelled) setInventorySnapshot(null); })
      .finally(() => { if (!cancelled) setInventoryLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  // Scroll-spy: highlight whichever section's marker is nearest the top of
  // the viewport, so the tab bar reflects where you've actually scrolled to.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: 0 }
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [loaded]);

  const revenueTrend = businessPerf?.trend ?? [];
  const topDishes = businessPerf?.top_dishes ?? [];
  const bottomDishes = businessPerf?.bottom_dishes ?? [];
  const allDishes = businessPerf?.all_dishes ?? [];
  const complaintCategories = businessPerf?.complaints_by_category ?? [];
  const complaintMax = Math.max(1, ...complaintCategories.map((c) => c.count));

  const channelSplit = businessPerf?.channel_split ?? null;
  const channelData = channelSplit && (channelSplit.dine_in_revenue + channelSplit.delivery_revenue) > 0 ? [
    { name: "Inpatient", value: channelSplit.dine_in_revenue, color: "#818cf8" },
    { name: "Outpatient", value: channelSplit.delivery_revenue, color: "#efa345" },
  ] : [];

  const peakHours = businessPerf?.peak_hours ?? [];
  const peakHoursDisplay = useMemo(() =>
    peakHours
      .filter((h) => h.hour >= 11 && h.hour <= 23)
      .map((h) => ({
        hour: h.hour,
        avg_orders: h.avg_orders,
        label: h.hour === 12 ? "12p" : h.hour > 12 ? `${h.hour - 12}p` : `${h.hour}a`,
      })),
    [peakHours]);

  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="space-y-4">
      {/* Tab-style nav, scroll-spy highlighted, plus the day-toggle and a
          plain link out to Market (no more duplicated teaser card). */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border-default)] pb-0">
        <div className="flex flex-wrap items-center gap-5">
          {SECTIONS.map((s) => {
            const active = activeId === s.id;
            return (
              <button
                key={s.id}
                onClick={() => scrollTo(s.id)}
                className="flex items-center gap-1.5 border-b-2 py-3 text-[13px] font-semibold transition-colors"
                style={{ borderColor: active ? "var(--color-accent)" : "transparent", color: active ? "var(--color-accent)" : "var(--color-text-soft)" }}
              >
                {s.icon}
                {s.label}
              </button>
            );
          })}
        </div>
        <div className="mb-2 flex shrink-0 items-center gap-3">
          <Link href="/planning" className="flex items-center gap-1 text-[12px] font-bold text-[var(--color-accent)]">
            Open capacity planner
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
          </Link>
          <div className="flex items-center gap-1 rounded-lg bg-[var(--color-surface-sunken)] p-1">
            {[7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => setPerfDays(d)}
                className="rounded-md px-2.5 py-1 text-[10.5px] font-semibold transition-colors"
                style={perfDays === d ? { background: "var(--color-surface-raised)", color: "var(--color-accent)" } : { color: "var(--color-text-faint)" }}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Bento grid: varied card sizes (hero charts wide, stat/list cards
          narrower), not a uniform stack of equal-width rows. 6-column base;
          same-row cards share height (default stretch) since same-row pairs
          are now sized close enough in natural content that stretching
          doesn't leave awkward gaps. */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-6">
        <div id="business" className="card card-lift scroll-mt-20 p-6 md:col-span-3">
          <CardHeader
            title="Admissions &amp; cost trend" sub={`Last ${perfDays} days`}
            icon={<IconBusiness className="h-4.5 w-4.5" />} color={SECTION_COLOR.business}
          />
          {revenueTrend.length > 0 ? <RevenueTrendChart data={revenueTrend} /> : <EmptyState text={loaded ? "Not enough encounter history yet." : "Loading…"} />}
        </div>

        <div className="card card-lift p-6 md:col-span-3">
          <CardHeader
            title="At a glance" sub={`Last ${perfDays} days`}
          />
          <div className="grid grid-cols-2 gap-3">
            <StatSquare
              icon={<IconTrendUp />}
              iconColor="#FF5200" squareBg="rgba(255,82,0,0.08)" borderColor="rgba(255,82,0,0.25)"
              label="Net Margin"
              value={businessPerf?.net_profit != null ? `₹${businessPerf.net_profit.toLocaleString("en-IN")}` : "--"}
            />
            <StatSquare
              icon={<span className="text-[12px] font-black">%</span>}
              iconColor="#FF5200" squareBg="rgba(255,82,0,0.08)" borderColor="rgba(255,82,0,0.25)"
              label="Net Margin"
              value={businessPerf?.net_margin_pct != null ? `${businessPerf.net_margin_pct}%` : "--"}
            />
            <StatSquare
              icon={<IconWallet />}
              iconColor="#FF5200" squareBg="rgba(255,82,0,0.08)" borderColor="rgba(255,82,0,0.25)"
              label="Total Expenses"
              value={businessPerf ? `₹${businessPerf.total_expenses.toLocaleString("en-IN")}` : "--"}
            />
            <StatSquare
              icon={<IconHeart />}
              iconColor="#FF5200" squareBg="rgba(255,82,0,0.08)" borderColor="rgba(255,82,0,0.25)"
              label="Operating Efficiency"
              value={businessPerf ? `${businessPerf.health_score}/100` : "--"}
            />
          </div>
        </div>

        <div className="card card-lift p-6 md:col-span-4">
          <CardHeader
            title="Department capacity matrix" sub={`Volume vs. utilization, last ${perfDays} days`}
          />
          {allDishes.length > 0 ? <MenuEngineeringMatrix dishes={allDishes} /> : <EmptyState text={loaded ? "Not enough encounter history yet." : "Loading…"} />}
        </div>

        <div id="menu" className="card card-lift scroll-mt-20 p-6 md:col-span-2">
          <CardHeader
            title="Department performance" sub={`By volume, last ${perfDays} days`}
            icon={<IconMenu className="h-4.5 w-4.5" />} color={SECTION_COLOR.menu}
          />
          {(topDishes.length > 0 || bottomDishes.length > 0) ? (
            <div className="space-y-5">
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: "#FF5200" }}>
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}><path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
                  Top volume
                </p>
                <div className="space-y-1.5">
                  {topDishes.slice(0, 5).map((d, i) => (
                    <div key={d.name} className="flex items-center gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white" style={{ background: "#FF5200" }}>{i + 1}</span>
                      <span className="truncate text-[12px] text-[var(--color-text-primary)]">{mapVolumeLabel(d.name, i)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--color-caution)]">
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}><path strokeLinecap="round" strokeLinejoin="round" d="M13 17h8m0 0v-8m0 8l-8-8-4 4-6-6" /></svg>
                  Needs attention
                </p>
                <div className="space-y-1.5">
                  {bottomDishes.slice(0, 5).map((d, i) => (
                    <div key={d.name} className="flex items-center gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white" style={{ background: "var(--color-text-ghost)" }}>{i + 1}</span>
                      <span className="truncate text-[12px] text-[var(--color-text-primary)]">{mapVolumeLabel(d.name, i + 5)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <EmptyState text={loaded ? "Not enough order history yet." : "Loading…"} />
          )}
        </div>

        <div id="customers" className="card card-lift scroll-mt-20 p-6 md:col-span-3">
          <CardHeader
            title="Encounter mix" sub={`Last ${perfDays} days`}
            icon={<IconCustomers className="h-4.5 w-4.5" />} color={SECTION_COLOR.customers}
          />
          {channelData.length > 0 ? (
            <div className="flex items-center gap-5">
              <div className="relative shrink-0" style={{ width: 116, height: 116 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={channelData} dataKey="value" nameKey="name" innerRadius={38} outerRadius={56} paddingAngle={3} stroke="none">
                      {channelData.map((d) => <Cell key={d.name} fill={d.color} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <p className="text-[9px] font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">Total</p>
                  <p className="text-[13px] font-bold text-[var(--color-text-primary)]">
                    ₹{Math.round(channelData[0].value + channelData[1].value).toLocaleString("en-IN")}
                  </p>
                </div>
              </div>
              <div className="min-w-0 flex-1 space-y-3">
                {channelData.map((d) => (
                  <div key={d.name} className="flex items-center gap-2.5">
                    <span
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white shadow-sm"
                      style={{ background: d.color }}
                    >
                      {d.name === "Inpatient" ? <IconStorefront className="h-4 w-4" /> : <IconDeliveryBag className="h-4 w-4" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] font-medium text-[var(--color-text-soft)]">{d.name}</p>
                      <p className="mono text-[9.5px] text-[var(--color-text-faint)]">₹{Math.round(d.value).toLocaleString("en-IN")}</p>
                    </div>
                    <span className="mono shrink-0 text-[17px] font-bold text-[var(--color-text-primary)]">
                      {Math.round((d.value / (channelData[0].value + channelData[1].value)) * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-[var(--color-text-faint)]">{loaded ? "No data yet" : "Loading…"}</p>
          )}
        </div>

        <div className="card card-lift p-6 md:col-span-3">
          <CardHeader
            title="Safety incident themes" sub={`Last ${perfDays} days`}
            icon={<IconCustomers className="h-4.5 w-4.5" />} color={SECTION_COLOR.customers}
          />
          {complaintCategories.length > 0 ? (
            <div className="space-y-2.5">
              {complaintCategories.slice(0, 6).map((c) => (
                <div key={c.category}>
                  <div className="flex items-center gap-2">
                    <span
                      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full"
                      style={{ background: "var(--color-surface-sunken)", color: "var(--color-text-soft)" }}
                    >
                      {COMPLAINT_ICONS[c.category] ?? <IconInfo />}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-[var(--color-text-soft)]">{toSafetyCategory(c.category)}</span>
                    <span className="mono shrink-0 text-right text-[12px] font-bold text-[var(--color-text-primary)]">{c.count}</span>
                  </div>
                  <div className="ml-7 mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
                    <div className="h-full rounded-full bg-[var(--color-caution)]" style={{ width: `${(c.count / complaintMax) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-[var(--color-text-faint)]">{loaded ? `No safety incidents in the last ${perfDays} days.` : "Loading…"}</p>
          )}
        </div>

        <div id="operations" className="card card-lift scroll-mt-20 p-6 md:col-span-3">
          <CardHeader
            title="Peak throughput" sub={`Avg encounters/hour, last ${perfDays} days`}
            icon={<IconOperations className="h-4.5 w-4.5" />} color={SECTION_COLOR.operations}
          />
          {peakHours.some((h) => h.avg_orders > 0) ? (
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={peakHoursDisplay} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="peakFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#efa345" stopOpacity={0.45} />
                      <stop offset="100%" stopColor="#efa345" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-soft)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#6b7280" }} axisLine={false} tickLine={false} interval={1} />
                  <YAxis width={26} tick={{ fontSize: 9, fill: "#6b7280" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(v) => [`${v} encounters/day avg`, ""]}
                    contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border-default)", borderRadius: 8, fontSize: 12 }}
                  />
                  <Area type="monotone" dataKey="avg_orders" stroke="#efa345" strokeWidth={2} fill="url(#peakFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState text={loaded ? "Not enough order history yet." : "Loading…"} />
          )}
        </div>

        <div id="inventory" className="card card-lift scroll-mt-20 p-6 md:col-span-3">
          <CardHeader
            title="Supply snapshot" sub="Live inventory levels — no historical supply trend yet."
            icon={<IconInventory className="h-4.5 w-4.5" />} color={SECTION_COLOR.inventory}
          />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <div>
              <p className="mb-2 text-[12px] font-semibold text-[var(--color-text-primary)]">Shortages right now</p>
              <p className="mb-3 text-[10.5px] text-[var(--color-text-faint)]">Below reorder threshold</p>
              {inventorySnapshot && inventorySnapshot.shortage_alerts.length > 0 ? (
                <div className="space-y-2">
                  {inventorySnapshot.shortage_alerts.map((a) => (
                    <div key={a.ingredient} className="flex items-center gap-3 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] p-2.5">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full" style={{ background: "rgba(194,65,12,0.12)", color: "#C2410C" }}>
                        <IconAlertTriangle />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-[12.5px] font-semibold text-[var(--color-text-primary)]">{toSupplyLabel(a.ingredient)}</p>
                          <span className="shrink-0 rounded-full px-2 py-0.5 text-[9.5px] font-semibold" style={{ background: "rgba(194,65,12,0.12)", color: "#C2410C" }}>{a.severity}</span>
                        </div>
                        <p className="mt-0.5 text-[10.5px] text-[var(--color-text-faint)]">{a.quantity_in_stock}{a.unit} in stock, vs {a.reorder_threshold}{a.unit} threshold</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-[var(--color-text-faint)]">{inventoryLoaded ? "Nothing below threshold right now." : "Loading…"}</p>
              )}
            </div>

            <div>
              <p className="mb-2 text-[12px] font-semibold text-[var(--color-text-primary)]">Overstock &amp; spoilage risk</p>
              <p className="mb-3 text-[10.5px] text-[var(--color-text-faint)]">Well above usual stock levels</p>
              {inventorySnapshot && inventorySnapshot.overstock_alerts.length > 0 ? (
                <div className="space-y-2">
                  {inventorySnapshot.overstock_alerts.map((a) => (
                    <div key={a.ingredient} className="flex items-center gap-3 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] p-2.5">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full" style={{ background: "var(--color-caution-soft)", color: "var(--color-caution)" }}>
                        <IconBox />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-[12.5px] font-semibold text-[var(--color-text-primary)]">{toSupplyLabel(a.ingredient)}</p>
                          {a.spoilage_risk && (
                            <span className="shrink-0 rounded-full px-2 py-0.5 text-[9.5px] font-semibold" style={{ background: "var(--color-caution-soft)", color: "var(--color-caution)" }}>spoilage risk</span>
                          )}
                        </div>
                        <p className="mt-0.5 text-[10.5px] text-[var(--color-text-faint)]">{a.quantity_in_stock}{a.unit} in stock — {a.excess}{a.unit} over usual</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-[var(--color-text-faint)]">{inventoryLoaded ? "Nothing overstocked right now." : "Loading…"}</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

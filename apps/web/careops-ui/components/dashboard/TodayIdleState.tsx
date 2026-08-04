"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ComposedChart, Area, Line, Bar, BarChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { useAuth } from "@/context/AuthContext";
import PlanShiftModal from "@/components/dashboard/PlanShiftModal";
import PageHeading from "@/components/ui/PageHeading";
import {
  getDataHealth, getConnectorsStatus, getMarketPulse, getBusinessPerformance, getBusinessSummary,
  listRestaurantProfiles,
  BusinessPerformanceResponse, BusinessSummaryResponse, ConnectorStatus, MarketPulseResponse,
  RestaurantProfile,
} from "@/lib/api";
import { shortDate } from "@/lib/formatters";
import { hourCacheKey, readHourCache, writeHourCache } from "@/lib/hourCache";
import { DataHealth, PlanningScenarioOption, PlanTriggerHandler } from "@/types/planning";

// Same prefix usePlanTriggerData uses -- Dashboard and /planning share one
// cache entry, so switching between them doesn't re-fetch market pulse at
// all within the same hour, not just independently cache their own copies.
const MARKET_PULSE_CACHE_PREFIX = "ck:market-pulse:";

const TONE_CLASS: Record<string, { bg: string; text: string }> = {
  good:    { bg: "var(--color-good-soft)",    text: "var(--color-good)" },
  info:    { bg: "rgba(56,189,248,0.10)",     text: "#38bdf8" },
  rose:    { bg: "rgba(251,113,133,0.10)",    text: "#fb7185" },
  caution: { bg: "var(--color-caution-soft)", text: "var(--color-caution)" },
  swiggy:  { bg: "rgba(252,128,25,0.12)",      text: "#fc8019" },
};

const CONDITION_LABELS: Record<string, string> = {
  heavy_rain: "Heavy Rain",
  light_rain: "Light Rain",
  very_hot:   "Very Hot",
  clear:      "Clear",
};

// TrendsService's digest is a multi-point paragraph/bullet list -- take just
// the first point as a compact row headline instead of dumping the whole
// thing (which overflowed the Live Intelligence row entirely).
function firstDigestSnippet(digest: string): string {
  const first = digest.split(/\n|(?<=[.;])\s*(?=[A-Z*•-])/)[0].replace(/^[*•\-\s]+/, "").trim();
  if (first.length <= 72) return first;
  const cut = first.slice(0, 69);
  const lastSpace = cut.lastIndexOf(" ");
  return `${lastSpace > 40 ? cut.slice(0, lastSpace) : cut}...`;
}

/** Maps legacy demo inventory names to hospital supply labels for display. */
const SUPPLY_DISPLAY: Record<string, string> = {
  "Burger Buns": "Surgical Gloves",
  "Paneer": "IV Saline Bags",
  "Mozzarella": "N95 Respirators",
  "Chicken Breast": "Sterile Syringes",
  "Tomatoes": "Wound Dressings",
  "Olive Oil": "Hand Sanitizer",
  "Pizza Dough": "Oxygen Cannulas",
};

const HOSPITAL_DEPARTMENTS = [
  "Emergency Medicine",
  "General Surgery",
  "Internal Medicine",
  "Radiology",
  "Pediatrics",
  "ICU",
];

function toSupplyLabel(name: string): string {
  return SUPPLY_DISPLAY[name] ?? name;
}

function healthcareTrendHeadline(digest: string): string {
  const snippet = firstDigestSnippet(digest).toLowerCase();
  if (/restaurant|menu|dish|dining|food delivery|kitchen/.test(snippet)) {
    return "National hospital capacity and staffing trends worth monitoring";
  }
  return firstDigestSnippet(digest)
    .replace(/\brestaurants?\b/gi, "hospitals")
    .replace(/\bmenu\b/gi, "service lines")
    .replace(/\bdining\b/gi, "healthcare");
}

function weatherOpsHeadline(condition: string, signal: string): string {
  if (condition === "clear") return "No weather impact on patient volume expected";
  if (condition === "heavy_rain") return "Heavy rain may increase ED visits 10–15%";
  if (condition === "light_rain") return "Light rain — minor walk-in volume uptick possible";
  if (condition === "very_hot") return "Heat advisory — watch dehydration-related admissions";
  return signal;
}

function sanitizeOpsSummary(text: string): string {
  let out = text;
  for (const [legacy, label] of Object.entries(SUPPLY_DISPLAY)) {
    out = out.replace(new RegExp(legacy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), label);
  }
  return out
    .replace(/\brestaurants?\b/gi, "hospital")
    .replace(/\bhealth score\b/gi, "operational health score")
    .replace(/\bnext service\b/gi, "next shift handoff")
    .replace(/\bcomplaint trends?\b/gi, "safety incident trends")
    .replace(/\bcustomer satisfaction\b/gi, "patient satisfaction")
    .replace(/\bWait Time\b/g, "ED wait time")
    .replace(/\bFood Quality\b/g, "Care quality")
    .replace(/\bingredients?\b/gi, "supply items")
    .replace(/\bfood cost\b/gi, "supply cost");
}

function healthLabel(score: number): string {
  if (score >= 70) return "Excellent";
  if (score >= 40) return "Fair";
  return "Needs attention";
}

function greetingWord(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good Morning";
  if (h < 17) return "Good Afternoon";
  return "Good Evening";
}

function todayLabel(): string {
  return new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
}

interface Props {
  onRun: PlanTriggerHandler;
  selectedScenario: PlanningScenarioOption["id"];
  historyCount: number;
  onShowHistory: () => void;
}

export default function TodayIdleState({
  onRun, selectedScenario, historyCount, onShowHistory,
}: Props) {
  const { user } = useAuth();

  const [profiles, setProfiles] = useState<RestaurantProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);

  const [dataHealth, setDataHealth]     = useState<DataHealth | null>(null);
  const [connector, setConnector]       = useState<ConnectorStatus | null>(null);
  // Must start identical on server and client -- a lazy initializer reading
  // localStorage here disagrees with the server's render (no localStorage,
  // always empty/not-loaded), which is a real hydration mismatch, not just a
  // missed optimization. The cache read moves into the effect below instead,
  // which only ever runs client-side, after hydration.
  const [marketPulse, setMarketPulse]   = useState<MarketPulseResponse | null>(null);
  const [businessPerf, setBusinessPerf] = useState<BusinessPerformanceResponse | null>(null);
  const [perfDays, setPerfDays]         = useState(14);
  const [loaded, setLoaded]             = useState(false);
  const [marketLoaded, setMarketLoaded] = useState(false);
  const [marketRefreshing, setMarketRefreshing] = useState(false);
  const [showPlanModal, setShowPlanModal] = useState(false);

  const [summary, setSummary]           = useState<BusinessSummaryResponse | null>(null);

  useEffect(() => {
    listRestaurantProfiles()
      .then((list) => { setProfiles(list); if (list.length > 0) setSelectedProfileId(list[0].id); })
      .catch(() => { /* optional context */ });
  }, []);

  // Fast, DB-only calls -- resolve in well under a second.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getDataHealth().catch(() => null),
      getConnectorsStatus().catch(() => null),
    ]).then(([health, connectors]) => {
      if (cancelled) return;
      setDataHealth(health);
      setConnector(connectors?.connectors.find((c) => c.type === "swiggy") ?? null);
    });
    return () => { cancelled = true; };
  }, []);

  // Business performance drives most of the page -- re-fetched whenever the
  // trend window toggle changes (Overall Performance's 7d/14d/30d control).
  useEffect(() => {
    let cancelled = false;
    getBusinessPerformance(perfDays)
      .then((perf) => { if (!cancelled) setBusinessPerf(perf); })
      .catch(() => { if (!cancelled) setBusinessPerf(null); })
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [perfDays]);

  // AI executive summary -- its own LLM call, cached server-side, never
  // blocks the KPIs/charts above from rendering.
  useEffect(() => {
    let cancelled = false;
    getBusinessSummary()
      .then((s) => { if (!cancelled) setSummary(s); })
      .catch(() => { if (!cancelled) setSummary(null); });
    return () => { cancelled = true; };
  }, []);

  // Market pulse hits live Swiggy MCP tools directly -- on a cold cache this can take
  // several seconds (real external calls). Kept in its own effect/loading flag so a
  // slow Swiggy response never blocks the rest of the page from rendering as soon as
  // it's ready. Hour-cached (shared with /planning's usePlanTriggerData) so toggling
  // between Dashboard and /planning doesn't re-fetch it at all within the same hour.
  useEffect(() => {
    const cached = readHourCache<MarketPulseResponse>(hourCacheKey(MARKET_PULSE_CACHE_PREFIX));
    if (cached !== null) {
      setMarketPulse(cached);
      setMarketLoaded(true);
      return;
    }
    let cancelled = false;
    getMarketPulse()
      .then((pulse) => {
        if (cancelled) return;
        setMarketPulse(pulse);
        writeHourCache(MARKET_PULSE_CACHE_PREFIX, hourCacheKey(MARKET_PULSE_CACHE_PREFIX), pulse);
      })
      .catch((err) => {
        console.error("TodayIdleState: failed to load /market/pulse", err);
        if (!cancelled) setMarketPulse(null);
      })
      .finally(() => { if (!cancelled) setMarketLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  // Manual refresh -- bypasses both the hour-bucketed localStorage cache and
  // the backend's own 1-hour Redis cache (trends/compliance), writing back
  // into the same shared "ck:market-pulse:" key /planning's idle state reads.
  async function handleMarketRefresh() {
    setMarketRefreshing(true);
    try {
      const pulse = await getMarketPulse(true);
      setMarketPulse(pulse);
      writeHourCache(MARKET_PULSE_CACHE_PREFIX, hourCacheKey(MARKET_PULSE_CACHE_PREFIX), pulse);
    } catch {
      /* keep whatever was already shown -- a failed refresh shouldn't blank the card */
    } finally {
      setMarketRefreshing(false);
    }
  }

  const activeProfile = profiles.find((p) => p.id === selectedProfileId) ?? profiles[0] ?? null;

  const coverage = dataHealth?.scenario_coverage.find((s) => s.scenario === selectedScenario) ?? null;
  const criticalShortages = dataHealth?.inventory.critical_shortages ?? 0;
  const shortageAlerts    = dataHealth?.inventory.shortage_alerts ?? 0;
  const feedback = dataHealth?.feedback ?? null;
  const positivePct = feedback && feedback.count > 0 ? Math.round((feedback.positive / feedback.count) * 100) : null;

  const occupancy = marketPulse?.area_occupancy ?? null;
  const pricingAlerts = (marketPulse?.competitor_pricing?.comparisons ?? []).filter(
    (a): a is typeof a & { diff_pct: number; direction: "above" | "below" } => a.your_price != null
  );
  const abovePricingCount = pricingAlerts.filter((a) => a.direction === "above").length;
  const procurement = marketPulse?.procurement ?? [];
  const cheapestProcurement = procurement.length > 0
    ? [...procurement].filter((p) => p.in_stock).sort((a, b) => a.price - b.price)[0] ?? procurement[0]
    : null;

  const yesterday = businessPerf?.yesterday ?? null;
  const revenueTrend = businessPerf?.trend ?? [];
  // Gross margin % by day -- a distinct profitability lens on the same
  // already-fetched trend data, so "Business Performance" isn't just a bar
  // version of "Overall Performance" repeating revenue/orders.
  const marginTrend = useMemo(
    () => revenueTrend.map((d) => ({
      date: d.date,
      margin_pct: d.revenue > 0 ? Math.round((d.profit / d.revenue) * 1000) / 10 : 0,
    })),
    [revenueTrend]
  );
  const healthScore = businessPerf?.health_score ?? 0;
  // Dark, saturated tones -- the hero card is now a light orange, so the
  // ring needs colors dark enough to read against a LIGHT background (a pale
  // cream barely showed up at all here, unlike on the previous dark-brown card).
  const healthRingColor = healthScore >= 70 ? "#34d399" : healthScore >= 40 ? "#FBBF24" : "#FB7185";
  const topDishes = businessPerf?.top_dishes ?? [];
  const departmentVolume = useMemo(
    () => topDishes.slice(0, 6).map((d, i) => ({
      name: HOSPITAL_DEPARTMENTS[i] ?? `Department ${i + 1}`,
      encounters: d.revenue,
    })),
    [topDishes],
  );
  const foodCostPct = yesterday && yesterday.revenue > 0
    ? Math.round(((yesterday.revenue - yesterday.profit) / yesterday.revenue) * 100)
    : null;
  const complaintCategories = businessPerf?.complaints_by_category ?? [];
  const revenueDelta = useMemo(() => {
    if (revenueTrend.length < 2) return null;
    const last = revenueTrend[revenueTrend.length - 2]; // yesterday (last complete day)
    const prior = revenueTrend[revenueTrend.length - 9]; // same weekday, one week earlier
    if (!last || !prior || !prior.revenue) return null;
    return Math.round(((last.revenue - prior.revenue) / prior.revenue) * 100);
  }, [revenueTrend]);
  const ordersDelta = useMemo(() => {
    if (revenueTrend.length < 9) return null;
    const last = revenueTrend[revenueTrend.length - 2];
    const prior = revenueTrend[revenueTrend.length - 9];
    if (!last || !prior || !prior.orders) return null;
    return Math.round(((last.orders - prior.orders) / prior.orders) * 100);
  }, [revenueTrend]);
  const aovDelta = useMemo(() => {
    if (revenueTrend.length < 9) return null;
    const last = revenueTrend[revenueTrend.length - 2];
    const prior = revenueTrend[revenueTrend.length - 9];
    if (!last || !prior || !last.orders || !prior.orders) return null;
    const lastAov = last.revenue / last.orders;
    const priorAov = prior.revenue / prior.orders;
    if (!priorAov) return null;
    return Math.round(((lastAov - priorAov) / priorAov) * 100);
  }, [revenueTrend]);

  const inventoryTotal = dataHealth?.inventory.items ?? 0;
  const overstockAlerts = dataHealth?.inventory.overstock_alerts ?? 0;
  const healthyItems = Math.max(0, inventoryTotal - shortageAlerts - overstockAlerts);
  const reservationGaugePct = coverage ? Math.min(100, Math.round(coverage.occupancy_pct)) : null;

  const risks = businessPerf?.risks ?? [];

  const insights: Array<{ tone: string; text: React.ReactNode }> = [];
  if (yesterday && revenueDelta !== null && revenueDelta !== 0) {
    insights.push({
      tone: revenueDelta > 0 ? "good" : "caution",
      text: <><b>Admissions were {revenueDelta > 0 ? "up" : "down"} {Math.abs(revenueDelta)}%</b> yesterday vs. the same day last week.</>,
    });
  }
  if (complaintCategories.length > 0) {
    const top = complaintCategories[0];
    insights.push({
      tone: "caution",
      text: <><b>{top.category} is your top safety concern</b> — {top.count} incidents in the last 28 days.</>,
    });
  }
  if (criticalShortages > 0) {
    insights.push({ tone: "caution", text: <><b>{criticalShortages} supply item{criticalShortages !== 1 ? "s are" : " is"} critically low</b> — review before the next shift handoff.</> });
  } else if (shortageAlerts > 0) {
    insights.push({ tone: "caution", text: <><b>{shortageAlerts} supply item{shortageAlerts !== 1 ? "s" : ""} running low</b> — worth reviewing before planning.</> });
  }
  if (coverage && coverage.waitlist > 0) {
    insights.push({ tone: "info", text: <><b>{coverage.waitlist} patient{coverage.waitlist !== 1 ? "s" : ""} on the waitlist</b> for {coverage.label.toLowerCase()} — plan for extra capacity.</> });
  }
  if (positivePct !== null) {
    insights.push({
      tone: positivePct >= 75 ? "good" : "caution",
      text: <><b>Patient feedback is {positivePct}% positive</b> across {feedback?.count} responses on record.</>,
    });
  }
  // "Today's Top Priorities" -- built entirely from real risk/demand data
  // (BusinessAnalyticsService.get_upcoming_risks + the Swiggy area-occupancy
  // signal), not a separate fabricated list.
  type Priority = { title: string; detail: string; pill: string; pillTone: "critical" | "caution" | "good"; icon: string };
  const priorities: Priority[] = [];
  const inventoryNames: string[] = [];
  for (const r of risks) {
    if (r.kind === "inventory") {
      const m = r.text.match(/^(.+?) below threshold/);
      const rawName = m ? m[1] : null;
      const name = rawName ? toSupplyLabel(rawName) : null;
      if (rawName) inventoryNames.push(name ?? rawName);
      priorities.push({
        title: name
          ? `${name} is ${r.severity === "critical" ? "critically low" : "running low"}`
          : r.text.replace(/^(.+?) below threshold/, (_, n: string) => `${toSupplyLabel(n)} below reorder threshold`),
        detail: rawName
          ? r.text.replace(rawName, toSupplyLabel(rawName)).replace("below threshold", "below reorder threshold")
          : r.text,
        pill: r.severity === "critical" ? "Critical" : "High",
        pillTone: r.severity === "critical" ? "critical" : "caution",
        icon: "M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z",
      });
    } else if (r.kind === "occupancy") {
      // Only surface here if the forecasted date is today/tomorrow -- these
      // risks are computed for the next occurrence of each scenario (up to
      // 7 days out), and labeling a 5-day-out forecast as a "Today" priority
      // is misleading. Further-out dates still show in the Upcoming Risks
      // card elsewhere, which is honestly framed as upcoming, not today's.
      const dateMatch = r.text.match(/\((\d{4}-\d{2}-\d{2})\)/);
      const daysUntil = dateMatch
        ? Math.round((new Date(dateMatch[1]).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000)
        : null;
      if (daysUntil !== null && daysUntil <= 1) {
        const m = r.text.match(/^(.+?) forecasted/);
        priorities.push({
          title: m ? `${m[1]} — capacity pressure expected` : r.text,
          detail: r.text,
          pill: "High",
          pillTone: "caution",
          icon: "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6",
        });
      }
    }
  }
  function highlightNames(text: string, names: string[]): React.ReactNode {
    if (names.length === 0) return text;
    const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
    const parts = text.split(pattern);
    return parts.map((part, i) =>
      names.some((n) => n.toLowerCase() === part.toLowerCase())
        ? <b key={i} style={{ color: "var(--color-accent)" }}>{part}</b>
        : <span key={i}>{part}</span>
    );
  }

  return (
    <div className="py-6 space-y-5">

      {/* Greeting row -- matches the shared PageHeading style rolled out from
          the Action Center redesign (P6-A31): bold sans title, short accent
          underline, no eyebrow. Today's date now sits on the right as the
          header's action slot instead of as an eyebrow above the title. */}
      <PageHeading
        title={<>{greetingWord()}, <span style={{ color: "var(--color-accent)" }}>{user?.full_name?.split(" ")[0] ?? "Director"}</span></>}
        description="Here's how your hospital is performing today."
        action={
          <span className="shrink-0 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-text-faint)]">
            {todayLabel()}
          </span>
        }
      />

      {/* ═══ The numbers, at a glance: 7-tile KPI strip ═══ */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        <MiniKpi
          label="Admissions" hue="#efa345" icon="M12 8c-1.66 0-3 .9-3 2s1.34 2 3 2 3 .9 3 2-1.34 2-3 2m0-8V6m0 10v2m0-14a8 8 0 100 16 8 8 0 000-16z"
          value={yesterday ? `₹${yesterday.revenue.toLocaleString("en-IN")}` : "--"}
          delta={revenueDelta !== null ? `${revenueDelta >= 0 ? "↑" : "↓"} ${Math.abs(revenueDelta)}% vs yesterday` : undefined}
          tone={revenueDelta !== null && revenueDelta < 0 ? "caution" : "good"}
          hero
        />
        <MiniKpi
          label="Encounters" hue="#38bdf8" icon="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
          value={yesterday ? yesterday.orders.toLocaleString("en-IN") : "--"}
          delta={ordersDelta !== null ? `${ordersDelta >= 0 ? "↑" : "↓"} ${Math.abs(ordersDelta)}% vs yesterday` : undefined}
          tone={ordersDelta !== null && ordersDelta < 0 ? "caution" : "good"}
        />
        <MiniKpi
          label="Avg Stay" hue="#818cf8" icon="M3 10h18M7 15h1m4 0h1m-7 4h12a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          value={yesterday ? `₹${Math.round(yesterday.avg_order_value)}` : "--"}
          delta={aovDelta !== null ? `${aovDelta >= 0 ? "↑" : "↓"} ${Math.abs(aovDelta)}% vs yesterday` : undefined}
          tone={aovDelta !== null && aovDelta < 0 ? "caution" : "good"}
        />
        <MiniKpi
          label="Bed Utilization" hue="#fb7185" icon="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"
          value={reservationGaugePct !== null ? `${reservationGaugePct}%` : "--"}
          delta={coverage ? `${coverage.waitlist} on waitlist` : undefined}
          tone={reservationGaugePct !== null && reservationGaugePct >= 90 ? "caution" : undefined}
        />
        <MiniKpi
          label="Supply Cost" hue="#fbbf24" icon="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
          value={foodCostPct !== null ? `${foodCostPct}%` : "--"} delta="of admissions revenue, yesterday"
        />
        <MiniKpi
          label="Supply Stock" hue="#B0621A" icon="M20 12V8H6a2 2 0 01-2-2c0-1.1.9-2 2-2h12v4M4 6v12a2 2 0 002 2h14v-4M18 12a2 2 0 00-2 2c0 1.1.9 2 2 2h4v-4h-4z"
          value={inventoryTotal > 0 ? `${healthyItems}/${inventoryTotal}` : "--"}
          delta={criticalShortages > 0 ? `${criticalShortages} critical` : "healthy"}
          tone={criticalShortages > 0 ? "caution" : undefined}
        />
        <MiniKpi
          label="Safety Rate" hue="#f472b6" icon="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          value={feedback && feedback.count > 0 ? `${feedback.negative_pct}%` : "--"}
          delta="negative feedback, 28d"
          tone={feedback && feedback.negative_pct > 25 ? "caution" : undefined}
        />
      </div>

      {/* ═══ HERO — health score + AI executive summary, paired with Live Intelligence ═══ */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.4fr_1fr] items-stretch">
        <div className="card min-w-0 p-5 sm:p-6">
          <p className="flex items-center gap-1.5 text-[15px] font-bold" style={{ color: "var(--color-accent)" }}>
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2l1.5 5.5L19 9l-5.5 1.5L12 16l-1.5-5.5L5 9l5.5-1.5z" /></svg>
            Operations Brief
          </p>

          <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-[auto_1fr]">
            <div className="flex shrink-0 flex-col items-center gap-1 text-center">
              <div className="relative shrink-0" style={{ width: 108, height: 108 }}>
                <svg width={108} height={108} viewBox="0 0 92 92">
                  <defs>
                    <linearGradient id="healthGauge" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#34d399" />
                      <stop offset="50%" stopColor="#fbbf24" />
                      <stop offset="100%" stopColor="#fb7185" />
                    </linearGradient>
                  </defs>
                  <circle cx={46} cy={46} r={40} fill="none" stroke="var(--color-surface-sunken)" strokeWidth={7} />
                  <circle
                    cx={46} cy={46} r={40} fill="none" stroke="url(#healthGauge)" strokeWidth={7} strokeLinecap="round"
                    strokeDasharray={2 * Math.PI * 40}
                    strokeDashoffset={loaded ? 2 * Math.PI * 40 * (1 - Math.min(100, Math.max(0, healthScore)) / 100) : 2 * Math.PI * 40}
                    transform="rotate(-90 46 46)" style={{ transition: "stroke-dashoffset 0.6s ease" }}
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="font-bold leading-none text-[var(--color-text-primary)]" style={{ fontSize: 38 }}>{loaded ? healthScore : "--"}</span>
                  <span className="mt-1 text-[10px] leading-none uppercase tracking-wide text-[var(--color-text-faint)]">/100</span>
                </div>
              </div>
              <p className="mt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-faint)]">Operational Health</p>
              <p className="text-[16px] font-bold leading-tight" style={{ color: healthRingColor }}>{loaded ? healthLabel(healthScore) : "Loading…"}</p>
            </div>

            <div className="min-w-0">
              <p className="text-[13.5px] leading-relaxed text-[var(--color-text-soft)]">
                {summary?.summary
                  ? highlightNames(sanitizeOpsSummary(summary.summary), inventoryNames)
                  : (loaded
                    ? "Operations brief isn't available right now — the KPIs below are still live and accurate."
                    : "Reading today's operational signals…")}
              </p>
            </div>
          </div>

          {priorities.length > 0 && (
            <div className="mt-5 border-t border-[var(--color-border-soft)] pt-4">
              <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-faint)]">Today&apos;s Top Priorities</p>
              <div className="mt-2.5 space-y-2">
                {priorities.slice(0, 3).map((p, i) => {
                  const toneColor = p.pillTone === "critical" ? "var(--color-critical)" : p.pillTone === "caution" ? "var(--color-caution)" : "var(--color-good)";
                  const toneSoft = p.pillTone === "critical" ? "var(--color-critical-soft)" : p.pillTone === "caution" ? "var(--color-caution-soft)" : "var(--color-good-soft)";
                  return (
                    <div key={i} className="flex items-center gap-3 rounded-xl border px-3.5 py-2.5" style={{ background: toneSoft, borderColor: toneSoft }}>
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-white shadow-sm" style={{ background: toneColor }}>
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d={p.icon} /></svg>
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-semibold text-[var(--color-text-primary)]">{p.title}</p>
                        <p className="truncate text-[11px] text-[var(--color-text-faint)]">{p.detail}</p>
                      </div>
                      <span
                        className="shrink-0 rounded-full px-2.5 py-1 text-[10.5px] font-bold"
                        style={{ background: "var(--color-surface-raised)", color: toneColor }}
                      >
                        {p.pill}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="mt-4 flex items-center justify-between border-t border-[var(--color-border-soft)] pt-4">
            <Link
              href="/analytics"
              className="inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-1.5 text-[12px] font-bold transition-colors"
              style={{ borderColor: "var(--color-accent)", color: "var(--color-accent)" }}
            >
              View Full Brief
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.6}><path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
            </Link>
            <p className="flex items-center gap-1 text-[11px] text-[var(--color-text-faint)]">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><circle cx="12" cy="12" r="9" /><path strokeLinecap="round" d="M12 7v5l3 3" /></svg>
              Refreshes hourly
            </p>
          </div>
        </div>

        <div className="card min-w-0 p-5">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-[15px] font-bold text-[var(--color-text-primary)]">
              <span className="h-2 w-2 rounded-full" style={{ background: "var(--color-good)" }} />
              Live Intelligence
            </p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleMarketRefresh}
                disabled={marketRefreshing}
                className="flex items-center gap-1 text-[11px] font-semibold text-[var(--color-text-faint)] transition hover:text-[var(--color-text-primary)] disabled:opacity-60"
              >
                <svg className={`h-3 w-3 ${marketRefreshing ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                {marketRefreshing ? "Refreshing…" : "Refresh"}
              </button>
              <Link href="/planning" className="text-[11px] font-semibold text-[var(--color-accent)]">Open capacity planner →</Link>
            </div>
          </div>
          <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">Signals affecting capacity, staffing, and compliance</p>

          <div className="mt-3 space-y-2.5">
            {marketPulse?.weather && (
              <LiveIntelRow
                hue="#38bdf8" icon="M17.5 19H6a4 4 0 01-1-7.87A5.5 5.5 0 0116 8.5a4.5 4.5 0 011.5 10.5z"
                title="Weather Impact"
                headline={weatherOpsHeadline(marketPulse.weather.condition, marketPulse.weather.signal)}
                detail={`${marketPulse.weather.avg_temp_celsius != null ? Math.round(marketPulse.weather.avg_temp_celsius) + "°C" : "--"} · ${CONDITION_LABELS[marketPulse.weather.condition] ?? marketPulse.weather.condition}${marketPulse.weather.avg_precipitation_pct != null ? ` · ${Math.round(marketPulse.weather.avg_precipitation_pct)}% precip.` : ""}`}
                pill={marketPulse.weather.condition === "clear" ? "Good" : "Caution"}
                pillTone={marketPulse.weather.condition === "clear" ? "good" : "caution"}
                headlineTone={marketPulse.weather.condition === "clear" ? "good" : "caution"}
              />
            )}
            {marketPulse?.industry_trends && marketPulse.industry_trends.headline_count > 0 && (
              <LiveIntelRow
                hue="#818cf8" icon="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                title="Healthcare Trends"
                headline={healthcareTrendHeadline(marketPulse.industry_trends.digest)}
                detail={`${marketPulse.industry_trends.headline_count} headlines · ${marketPulse.industry_trends.sources_used} sources tracked`}
                pill="Watch"
                pillTone="swiggy"
                headlineTone="swiggy"
              />
            )}
            <LiveIntelRow
              hue="#34d399" icon="M12 3l7 4v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V7l7-4z"
              title="Regulatory Updates"
              headline={marketPulse?.compliance_alerts?.notice_count ? `${marketPulse.compliance_alerts.notice_count} new regulatory notice${marketPulse.compliance_alerts.notice_count !== 1 ? "s" : ""} published` : "No action required"}
              detail={marketPulse?.compliance_alerts?.notices[0]?.title ?? "No critical notices right now"}
              pill={marketPulse?.compliance_alerts?.notice_count ? "Review" : "Clear"}
              pillTone={marketPulse?.compliance_alerts?.notice_count ? "caution" : "good"}
              headlineTone={marketPulse?.compliance_alerts?.notice_count ? "caution" : "good"}
            />
            {marketPulse?.upcoming_holiday && (
              <LiveIntelRow
                hue="#efa345" icon="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                title="Staffing Calendar"
                headline={marketPulse.upcoming_holiday.days_away === 0 ? `${marketPulse.upcoming_holiday.name} — skeleton staffing today` : "No public holiday today"}
                detail={marketPulse.upcoming_holiday.days_away === 0 ? "Expect reduced outpatient volume" : `Next: ${marketPulse.upcoming_holiday.name} · ${shortDate(marketPulse.upcoming_holiday.date)}`}
                pill={marketPulse.upcoming_holiday.days_away === 0 ? "Today" : "Upcoming"}
                pillTone={marketPulse.upcoming_holiday.days_away === 0 ? "caution" : "good"}
                headlineTone={marketPulse.upcoming_holiday.days_away === 0 ? "caution" : "good"}
              />
            )}
          </div>
          {!marketLoaded && <p className="mt-3 text-[11px] text-[var(--color-text-faint)]">Checking live signals…</p>}
        </div>
      </div>

      {/* ═══ ZONE 4 — Trend + what fed it ═══ */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3 items-stretch">
        <div className="card p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[15px] font-bold text-[var(--color-text-primary)]">Overall Performance</p>
              <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">Admissions, encounters &amp; capacity</p>
            </div>
            <div className="flex shrink-0 items-center gap-1 rounded-lg bg-[var(--color-surface-sunken)] p-1">
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

          {revenueTrend.length >= 2 ? (
            <div style={{ height: 220 }} className="mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={revenueTrend} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#efa345" stopOpacity={0.32} />
                      <stop offset="100%" stopColor="#efa345" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="profitFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#34d399" stopOpacity={0.22} />
                      <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-soft)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(d: string) => shortDate(d)} tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "Space Mono" }} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="money" tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "Space Mono" }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `₹${Math.round(v / 1000)}k`} />
                  <YAxis yAxisId="orders" orientation="right" tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "Space Mono" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    labelFormatter={(d) => shortDate(d as string)}
                    formatter={(value, name) => {
                      const label = String(name);
                      if (label === "Encounters") return [`${value}`, label];
                      if (label === "Cost efficiency") return [`₹${Number(value).toLocaleString("en-IN")}`, label];
                      return [`₹${Number(value).toLocaleString("en-IN")}`, label];
                    }}
                    contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border-default)", borderRadius: 8, fontSize: 12 }}
                  />
                  <Area yAxisId="money" type="monotone" dataKey="revenue" name="Admissions revenue" stroke="#efa345" strokeWidth={2.5} fill="url(#revenueFill)" dot={false} activeDot={{ r: 4 }} />
                  <Area yAxisId="money" type="monotone" dataKey="profit" name="Cost efficiency" stroke="#34d399" strokeWidth={2} fill="url(#profitFill)" dot={false} activeDot={{ r: 4 }} />
                  <Line yAxisId="orders" type="monotone" dataKey="orders" name="Encounters" stroke="#38bdf8" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-4 flex h-[180px] items-center justify-center rounded-xl border border-dashed border-[var(--color-border-default)] text-center">
              <p className="max-w-xs text-xs text-[var(--color-text-faint)]">{loaded ? "Not enough encounter history yet to show a trend." : "Loading…"}</p>
            </div>
          )}

          <div className="mt-3 flex items-center gap-5 text-[11px] text-[var(--color-text-faint)]">
            <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-sm" style={{ background: "#efa345" }} />Admissions revenue</span>
            <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-sm" style={{ background: "#34d399" }} />Cost efficiency</span>
            <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-sm" style={{ background: "#38bdf8" }} />Encounters</span>
          </div>
        </div>

        <div className="card p-6">
          <p className="text-[15px] font-bold text-[var(--color-text-primary)]">Operating Efficiency</p>
          <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">Net margin % by day — cost-to-serve vs. reimbursement</p>
          {marginTrend.length >= 2 ? (
            <div style={{ height: 240 }} className="mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={marginTrend} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                  <defs>
                    <linearGradient id="marginFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#0E9F6E" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#0E9F6E" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-soft)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(d: string) => shortDate(d)} tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "Space Mono" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "Space Mono" }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v}%`} />
                  <Tooltip
                    labelFormatter={(d) => shortDate(d as string)}
                    formatter={(value) => [`${value}%`, "Operating efficiency"]}
                    contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border-default)", borderRadius: 8, fontSize: 12 }}
                  />
                  <Area type="monotone" dataKey="margin_pct" name="Operating efficiency" stroke="#0E9F6E" strokeWidth={2.5} fill="url(#marginFill)" dot={false} activeDot={{ r: 4 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-4 flex h-[200px] items-center justify-center rounded-xl border border-dashed border-[var(--color-border-default)] text-center">
              <p className="max-w-xs text-xs text-[var(--color-text-faint)]">{loaded ? "Not enough billing history yet to show a trend." : "Loading…"}</p>
            </div>
          )}
        </div>

        <div className="card p-6">
          <p className="text-[15px] font-bold text-[var(--color-text-primary)]">Top Departments by Volume</p>
          <p className="mt-0.5 text-[11.5px] text-[var(--color-text-faint)]">Last {revenueTrend.length || perfDays} days — highest patient volume by department</p>
          {departmentVolume.length > 0 ? (
            <div style={{ height: 240 }} className="mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={departmentVolume} layout="vertical" margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10.5, fill: "#6b7280" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(v) => [`${Number(v).toLocaleString("en-IN")} encounters`, "Volume"]}
                    contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border-default)", borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="encounters" name="Encounters" fill="var(--color-accent)" radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-4 flex h-[200px] items-center justify-center rounded-xl border border-dashed border-[var(--color-border-default)] text-center">
              <p className="max-w-xs text-xs text-[var(--color-text-faint)]">{loaded ? "Not enough encounter history yet." : "Loading…"}</p>
            </div>
          )}
        </div>
      </div>

      {/* ═══ What to do about it: Signals + Upcoming Risks, one tabbed card.
          Action Queue and Latest Planning Run were dropped from here -- both
          already have a full, dedicated home (Action Center, Data/Planning)
          and were just duplicating that content at a smaller size here. ═══ */}
      <SignalsAndRisksCard insights={insights} risks={risks} loaded={loaded} />

      {/* ═══ One tap to act: quick-action band ═══ */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <button
          onClick={() => setShowPlanModal(true)}
          className="card flex items-center gap-3 p-4 text-left transition-transform hover:scale-[1.01]"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg" style={{ background: "var(--color-accent-soft)", color: "var(--color-accent)" }}>
            <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </span>
          <div className="min-w-0">
            <p className="text-[13px] font-bold text-[var(--color-text-primary)]">Run Capacity Planning</p>
            <p className="text-[11px] text-[var(--color-text-faint)]">Generate today&apos;s AI operational plan</p>
          </div>
          <svg className="ml-auto h-4 w-4 shrink-0 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
        </button>
        <Link href="/action-center" className="card flex items-center gap-3 p-4 transition-transform hover:scale-[1.01]">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg" style={{ background: "rgba(56,189,248,0.12)", color: "#38bdf8" }}>
            <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>
          </span>
          <div className="min-w-0">
            <p className="text-[13px] font-bold text-[var(--color-text-primary)]">Approval Queue</p>
            <p className="text-[11px] text-[var(--color-text-faint)]">Review staffing and supply actions</p>
          </div>
          <svg className="ml-auto h-4 w-4 shrink-0 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
        </Link>
        <Link href="/chat" className="card flex items-center gap-3 p-4 transition-transform hover:scale-[1.01]">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg" style={{ background: "rgba(52,211,153,0.12)", color: "#34d399" }}>
            <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
          </span>
          <div className="min-w-0">
            <p className="text-[13px] font-bold text-[var(--color-text-primary)]">Policy Assistant</p>
            <p className="text-[11px] text-[var(--color-text-faint)]">Ask about protocols and operations</p>
          </div>
          <svg className="ml-auto h-4 w-4 shrink-0 text-[var(--color-text-ghost)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
        </Link>
      </div>

      {historyCount > 0 && (
        <button onClick={onShowHistory} className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-faint)] transition-colors hover:text-[var(--color-text-primary)]">
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {historyCount} previous run{historyCount !== 1 ? "s" : ""}
        </button>
      )}
      <PlanShiftModal
        open={showPlanModal}
        onClose={() => setShowPlanModal(false)}
        onRun={onRun}
        activeProfile={activeProfile}
      />
    </div>
  );
}

function MiniKpi({ label, value, delta, tone, icon, hue, hero }: {
  label: string; value: string; delta?: string; tone?: "caution" | "good"; icon: string; hue: string; hero?: boolean;
}) {
  const deltaColor = tone === "caution" ? "var(--color-caution)" : tone === "good" ? "var(--color-good)" : "var(--color-text-faint)";
  return (
    <div className={`card p-4 ${hero ? "ring-1 ring-[var(--color-accent)]/25" : ""}`}>
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg" style={{ background: hue, color: "#fff" }}>
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d={icon} />
          </svg>
        </span>
        <p className="min-w-0 text-[11.5px] font-medium leading-tight text-[var(--color-text-faint)]">{label}</p>
      </div>
      <p
        className={`mt-2 text-[22px] font-bold leading-none ${hero ? "" : "text-[var(--color-text-primary)]"}`}
        style={hero ? { color: "var(--color-accent)" } : undefined}
      >
        {value}
      </p>
      {delta && <p className="mt-1.5 text-[11px] font-semibold" style={{ color: deltaColor }}>{delta}</p>}
    </div>
  );
}

function LiveIntelRow({ hue, icon, title, headline, detail, pill, pillTone }: {
  hue: string; icon: string; title: string; headline: string; detail: string; pill: string;
  pillTone: "good" | "caution" | "swiggy"; headlineTone: "good" | "caution" | "swiggy";
}) {
  const pillColors = TONE_CLASS[pillTone] ?? TONE_CLASS.good;
  return (
    <div
      className="flex items-center gap-3 rounded-xl border p-3"
      style={{ background: `${hue}14`, borderColor: `${hue}40` }}
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-white shadow-sm" style={{ background: hue }}>
        <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
          <path strokeLinecap="round" strokeLinejoin="round" d={icon} />
        </svg>
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.1em]" style={{ color: hue }}>{title}</p>
        <p className="mt-0.5 truncate text-[13px] font-bold text-[var(--color-text-primary)]">{headline}</p>
        <p className="mt-0.5 truncate text-[11px] text-[var(--color-text-faint)]">{detail}</p>
      </div>
      <span className="shrink-0 rounded-full px-2.5 py-1 text-[10.5px] font-bold" style={{ background: pillColors.bg, color: pillColors.text }}>
        {pill}
      </span>
    </div>
  );
}

// Signals (rule-based) and Upcoming Risks used to be two separate cards --
// folded into one tabbed card so Dashboard isn't just a wall of same-sized
// boxes; Action Queue/Latest Run were dropped from Dashboard entirely for
// the same reason since they already have a full home elsewhere.
function SignalsAndRisksCard({
  insights, risks, loaded,
}: {
  insights: Array<{ tone: string; text: React.ReactNode }>;
  risks: Array<{ text: string }>;
  loaded: boolean;
}) {
  const [tab, setTab] = useState<"signals" | "risks">("signals");

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setTab("signals")}
            className="rounded-lg px-2.5 py-1.5 text-[12.5px] font-bold transition-colors"
            style={tab === "signals"
              ? { background: "var(--color-accent-soft)", color: "var(--color-accent)" }
              : { color: "var(--color-text-faint)" }}
          >
            Signals
          </button>
          <button
            onClick={() => setTab("risks")}
            className="rounded-lg px-2.5 py-1.5 text-[12.5px] font-bold transition-colors"
            style={tab === "risks"
              ? { background: "var(--color-caution-soft)", color: "var(--color-caution)" }
              : { color: "var(--color-text-faint)" }}
          >
            Upcoming Risks
          </button>
        </div>
        <Link href={tab === "signals" ? "/analytics" : "/data"} className="shrink-0 text-[10.5px] font-semibold text-[var(--color-accent)]">
          View All →
        </Link>
      </div>

      {tab === "signals" ? (
        <div className="mt-2.5">
          {insights.length > 0 ? insights.slice(0, 5).map((item, i) => (
            <div key={i} className="flex items-start gap-2.5 border-t border-[var(--color-border-soft)] py-2 first:border-t-0 first:pt-0">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full" style={{ background: TONE_CLASS[item.tone]?.bg ?? "var(--color-surface-sunken)", color: TONE_CLASS[item.tone]?.text ?? "var(--color-text-faint)" }}>
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
              </span>
              <p className="text-[11.5px] leading-relaxed text-[var(--color-text-soft)] [&_b]:font-bold [&_b]:text-[var(--color-text-primary)]">{item.text}</p>
            </div>
          )) : (
            <p className="py-3 text-[11px] text-[var(--color-text-faint)]">{loaded ? "Nothing to flag right now." : "Loading…"}</p>
          )}
        </div>
      ) : (
        <div className="mt-2.5">
          {risks.length > 0 ? risks.slice(0, 4).map((r, i) => (
            <div key={i} className="flex items-start gap-2.5 border-t border-[var(--color-border-soft)] py-2 first:border-t-0 first:pt-0">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full" style={{ background: "var(--color-caution-soft)", color: "var(--color-caution)" }}>
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
              </span>
              <p className="text-[11.5px] leading-relaxed text-[var(--color-text-soft)]">{r.text}</p>
            </div>
          )) : (
            <p className="py-3 text-[11px] text-[var(--color-text-faint)]">{loaded ? "Nothing on the horizon." : "Loading…"}</p>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { getMarketPulse, MarketPulseResponse, MarketWeather, MarketUpcomingHoliday, MarketIndustryTrends, MarketComplianceAlerts } from "@/lib/api";
import { hourCacheKey, readHourCache, writeHourCache } from "@/lib/hourCache";
import CategoryPricingChart from "./CategoryPricingChart";
import OccupancyBySlotChart from "./OccupancyBySlotChart";
import IngredientPriceLookup from "./IngredientPriceLookup";

// Same prefix TodayIdleState.tsx uses -- shares one hour-bucketed cache
// entry across Dashboard and this page, so visiting whichever one first
// is the only one that actually hits the network within a given hour.
const MARKET_PULSE_CACHE_PREFIX = "ck:market-pulse:";

// One warm family only (Swiggy orange / gold / brown), matching Analytics'
// SECTION_COLOR convention -- literal hex, not var(--color-accent), since
// CardHeader appends an alpha suffix directly to this string for its
// gradient (`${color}cc`), which only produces valid CSS for a literal hex.
const MARKET_COLOR = {
  weather:    "#C2410C",
  trends:     "#D97706",
  alerts:     "#92400E",
  pricing:    "#FF5200",
  landscape:  "#A16207",
  occupancy:  "#D97706",
  ingredient: "#C2410C",
} as const;

function IconCloud({ className = "h-4.5 w-4.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M6.5 19a4.5 4.5 0 01-.5-8.98A5.5 5.5 0 0116.9 8.02 4.5 4.5 0 0117.5 19h-11z" /></svg>;
}
function IconNewspaper({ className = "h-4.5 w-4.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v12a2 2 0 01-2 2zM7 8h10M7 12h10M7 16h6" /></svg>;
}
function IconShieldAlert({ className = "h-4.5 w-4.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3zM12 8v4m0 3h.007" /></svg>;
}
function IconTagPrice({ className = "h-4.5 w-4.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5.586a1 1 0 01.707.293l7.414 7.414a1 1 0 010 1.414l-8.586 8.586a1 1 0 01-1.414 0L3.293 13.293A1 1 0 013 12.586V7a4 4 0 014-4z" /></svg>;
}
function IconStorefront({ className = "h-4.5 w-4.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M13 21v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4M3 9h18M4 9l1.5-5h13L20 9M4 9v9a2 2 0 002 2h12a2 2 0 002-2V9" /></svg>;
}
function IconClock({ className = "h-4.5 w-4.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 7v5l3.5 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
function IconRefresh({ className = "h-4.5 w-4.5" }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>;
}

function SwiggyBadge() {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex h-4 w-4 items-center justify-center rounded bg-white p-0.5">
        <Image src="/swiggy-logo.png" alt="Swiggy" width={12} height={12} className="h-full w-full object-contain" />
      </div>
      <span className="text-[9px] uppercase tracking-widest text-[var(--color-text-faint)]">via Swiggy MCP</span>
    </div>
  );
}

function ConceptBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border-2 border-[var(--color-caution)] bg-[var(--color-caution-soft)] px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-[var(--color-caution)] shadow-sm">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-caution)]" />
      Concept · Pending Consent
    </span>
  );
}

// One StatSquare-style tinted mini-tile, matching AnalyticsDetail.tsx's
// "at a glance" stat convention -- an icon badge + label + big value, instead
// of a plain bordered box with tiny uppercase text.
function StatTile({ label, value, sub, color }: { label: string; value: React.ReactNode; sub?: string; color: string }) {
  return (
    <div className="rounded-xl border p-3" style={{ background: `${color}14`, borderColor: `${color}40` }}>
      <p className="text-[9px] font-semibold uppercase tracking-widest" style={{ color: `${color}` }}>{label}</p>
      <p className="mt-1 font-mono text-lg font-bold text-[var(--color-text-primary)]">{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-[var(--color-text-faint)]">{sub}</p>}
    </div>
  );
}

function CardHeader({ title, sub, icon, color, titleIcon, concept, swiggy }: {
  title: string; sub: string; icon?: React.ReactNode; color?: string; titleIcon?: React.ReactNode; concept?: boolean; swiggy?: boolean;
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3 flex-wrap">
      <div className="flex min-w-0 items-center gap-3">
        {icon && (
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm"
            style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
          >
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 truncate text-[15px] font-bold text-[var(--color-text-primary)]">
            {title}
            {titleIcon}
          </p>
          <p className="mt-0.5 truncate text-[11.5px] font-medium text-[var(--color-text-soft)]">{sub}</p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {concept && <ConceptBadge />}
        {swiggy && <SwiggyBadge />}
      </div>
    </div>
  );
}

function Card({ title, source, children, wide, swiggy = true, concept = false, icon, color, titleIcon }: {
  title: string; source: string; children: React.ReactNode; wide?: boolean; swiggy?: boolean; concept?: boolean;
  icon?: React.ReactNode; color?: string; titleIcon?: React.ReactNode;
}) {
  return (
    <div className={`card card-lift flex h-full flex-col p-5 ${wide ? "lg:col-span-2" : ""}`}>
      <CardHeader title={title} sub={`via ${source}`} icon={icon} color={color} titleIcon={titleIcon} concept={concept} swiggy={swiggy} />
      {/* flex column so a footer element inside children can use mt-auto to
          pin itself to the bottom of the stretched card height, instead of
          leaving a dead gap under shorter content. */}
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}

// A card whose underlying signal is missing/unavailable must still render,
// just with an honest "not available" message -- a card that silently
// vanishes reads as broken, not as "nothing to report" (P6-MI, live testing
// feedback: a missing FSSAI compliance card looked indistinguishable from a
// real bug until this existed).
function UnavailableNote({ text }: { text: string }) {
  return (
    <div className="flex flex-1 items-center gap-2.5 rounded-lg border border-[var(--color-border-soft)] bg-[var(--color-surface-sunken)] px-3 py-3">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-text-ghost)]" />
      <p className="text-xs text-[var(--color-text-faint)] italic">{text}</p>
    </div>
  );
}

type Status = "loading" | "success" | "error";

export default function SwiggyLiveMarketPanel() {
  // Must start identical on server and client -- a lazy initializer that
  // reads localStorage here would make the server's first render (no
  // localStorage, always "loading") disagree with the client's first render
  // (real cache hit, renders full content immediately), which is a genuine
  // hydration mismatch, not just a missed optimization. The cache read moves
  // into the effect below instead, which only ever runs client-side, after
  // hydration -- a real cache hit still means no network round trip, just a
  // brief "loading" frame before it, unlike the previous zero-flash version.
  const [data, setData] = useState<MarketPulseResponse | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const cached = readHourCache<MarketPulseResponse>(hourCacheKey(MARKET_PULSE_CACHE_PREFIX));
    if (cached !== null) {
      setData(cached);
      setStatus("success");
      return;
    }

    let cancelled = false;
    getMarketPulse()
      .then((res) => {
        if (cancelled) return;
        writeHourCache(MARKET_PULSE_CACHE_PREFIX, hourCacheKey(MARKET_PULSE_CACHE_PREFIX), res);
        setData(res);
        setStatus("success");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("SwiggyLiveMarketPanel: failed to load /market/pulse", err);
        setError(err instanceof Error ? err.message : "Failed to load live market data");
        setStatus("error");
      });
    return () => { cancelled = true; };
  }, []);

  // Manual refresh -- bypasses both this hour-bucketed localStorage cache AND
  // the backend's own 1-hour Redis cache (trends/compliance), since clearing
  // only the frontend cache still hits a cached backend response otherwise.
  // Writes back into the SAME shared "ck:market-pulse:" key the Dashboard and
  // Planning idle-state read, so a refresh here is immediately visible there too.
  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      const res = await getMarketPulse(true);
      writeHourCache(MARKET_PULSE_CACHE_PREFIX, hourCacheKey(MARKET_PULSE_CACHE_PREFIX), res);
      setData(res);
      setStatus("success");
    } catch (err) {
      console.error("SwiggyLiveMarketPanel: failed to refresh /market/pulse", err);
      setError(err instanceof Error ? err.message : "Failed to refresh live market data");
      setStatus("error");
    } finally {
      setRefreshing(false);
    }
  }

  const refreshBar = (
    <div className="flex items-center justify-end">
      <button
        type="button"
        onClick={handleRefresh}
        disabled={refreshing}
        className="flex items-center gap-1.5 rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-[11.5px] font-semibold text-[var(--color-text-soft)] transition hover:text-[var(--color-text-primary)] disabled:opacity-60"
      >
        <IconRefresh className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
        {refreshing ? "Refreshing…" : "Refresh live signals"}
      </button>
    </div>
  );

  if (status === "loading") {
    return (
      <div className="card p-6">
        <p className="text-sm text-[var(--color-text-faint)]">Loading live market intelligence…</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="card p-6">
        <p className="text-sm text-rose-400">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  // Weather + holiday + industry trends + regulatory alerts are independent
  // of Swiggy (Open-Meteo, internal calendar, curated RSS, FSSAI notices --
  // no MCP involved) -- must render even when Swiggy isn't connected.
  const weather = data.weather;
  const upcomingHoliday = data.upcoming_holiday;
  const industryTrends = data.industry_trends;
  const complianceAlerts = data.compliance_alerts;

  if (!data.swiggy_connected) {
    return (
      <div className="space-y-4">
        {refreshBar}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <WeatherHolidayCard weather={weather} upcomingHoliday={upcomingHoliday} />
          <IndustryTrendsCard trends={industryTrends} />
          <ComplianceAlertsCard alerts={complianceAlerts} />
        </div>
        <div className="card px-6 py-10 text-center">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">Swiggy not connected</p>
          <p className="mt-1 text-sm text-[var(--color-text-faint)]">
            Connect your Swiggy account from Connectors to see live competitor pricing, occupancy, and procurement data.
          </p>
        </div>
      </div>
    );
  }

  const pricing = data.competitor_pricing;
  const occupancy = data.area_occupancy;
  const comparisons = pricing?.comparisons ?? [];
  const dealsActiveCount = pricing?.deals_active_count ?? 0;
  const categoryPricing = pricing?.category_pricing ?? [];
  const landscapeSummary = pricing?.landscape_summary ?? null;
  const positioning = pricing?.positioning ?? null;
  const menuBreadth = pricing?.menu_breadth ?? null;
  const cuisineCrowding = pricing?.cuisine_crowding ?? null;
  const vegMix = pricing?.veg_mix ?? null;
  const slotAvailability = occupancy?.slot_availability_by_time ?? [];

  // Weather/trends/compliance always render their own card (with an honest
  // "unavailable" state if their data is missing) -- this gate is only about
  // whether there's any Swiggy-dependent content below them worth showing.
  const hasSwiggyContent =
    categoryPricing.length > 0 || comparisons.length > 0 || Boolean(occupancy?.signal) ||
    dealsActiveCount > 0 || landscapeSummary !== null;

  return (
    <div className="space-y-4">
      {refreshBar}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 [grid-auto-flow:dense]">
        <WeatherHolidayCard weather={weather} upcomingHoliday={upcomingHoliday} />
        <IndustryTrendsCard trends={industryTrends} />
        <ComplianceAlertsCard alerts={complianceAlerts} />

        {!hasSwiggyContent && (
          <div className="card px-6 py-10 text-center lg:col-span-3">
            <p className="text-sm text-[var(--color-text-faint)] italic">No live Swiggy market data available right now.</p>
          </div>
        )}

        {/* Area Deals -- aggregate count/summary, no restaurant names. Not
            always present (fetch_food_coupons data). */}
        {dealsActiveCount > 0 && (
          <Card title="Area Deals Tonight" source="Swiggy live coupons, area aggregate" concept icon={<IconTagPrice />} color={MARKET_COLOR.pricing}>
            <div className="flex items-start gap-3 rounded-lg border border-amber-500/25 bg-amber-500/[0.06] p-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white shadow-sm">
                <IconTagPrice className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-bold text-amber-700 dark:text-amber-200">{dealsActiveCount} deal{dealsActiveCount !== 1 ? "s" : ""} active nearby</p>
                <p className="mt-0.5 text-[11px] text-amber-600 dark:text-amber-300/90">{pricing?.deals_summary}</p>
              </div>
            </div>
          </Card>
        )}

        {(categoryPricing.length > 0 || menuBreadth || cuisineCrowding || vegMix) && (
          <div className="lg:col-span-2">
          <Card title="Menu & Pricing Positioning" source="derived aggregate analysis" swiggy concept icon={<IconTagPrice />} color={MARKET_COLOR.pricing}>
            {pricing && pricing.restaurants_checked_count > 0 && (
              <p className="mb-3 text-[10px] text-[var(--color-text-faint)]">
                {pricing.restaurants_checked_count} nearby restaurant{pricing.restaurants_checked_count !== 1 ? "s" : ""} checked
              </p>
            )}
            {categoryPricing.length > 0 && (
              <>
                <div className="space-y-1.5 mb-4">
                  {categoryPricing.map((c) => {
                    const color = c.verdict === "above" ? "#E11D48" : c.verdict === "below" ? "#059669" : "#60A5FA";
                    return (
                      <div
                        key={c.category}
                        className="flex items-center gap-3 rounded-lg border p-2.5"
                        style={{ background: `${color}0d`, borderColor: `${color}30` }}
                      >
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white shadow-sm" style={{ background: color }}>
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
                            {c.verdict === "above" ? (
                              <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                            ) : c.verdict === "below" ? (
                              <path strokeLinecap="round" strokeLinejoin="round" d="M13 17h8m0 0v-8m0 8l-8-8-4 4-6-6" />
                            ) : (
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14" />
                            )}
                          </svg>
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-semibold capitalize text-[var(--color-text-primary)]">{c.category}</p>
                          <p className="mt-0.5 truncate text-[10px] text-[var(--color-text-faint)]">
                            based on {c.competitor_dishes_sampled} nearby dish{c.competitor_dishes_sampled !== 1 ? "es" : ""}
                          </p>
                        </div>
                        <span className="shrink-0 rounded-full px-2.5 py-1 text-xs font-bold" style={{ background: `${color}1a`, color }}>
                          {c.verdict === "in line" ? "on par" : `${Math.abs(c.diff_pct).toFixed(0)}%`}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <CategoryPricingChart data={categoryPricing} />
              </>
            )}
            {(menuBreadth || cuisineCrowding || vegMix) && (
              <div className={`grid grid-cols-1 gap-2 sm:grid-cols-3 ${categoryPricing.length > 0 ? "mt-4 border-t border-[var(--color-border-soft)] pt-4" : ""}`}>
                {menuBreadth && (
                  <StatTile
                    label="Menu breadth" color={MARKET_COLOR.pricing}
                    value={<>{menuBreadth.your_item_count} <span className="text-xs font-normal text-[var(--color-text-faint)]">items</span></>}
                    sub={`vs ${menuBreadth.competitor_avg_item_count} avg across ${menuBreadth.competitors_sampled} nearby`}
                  />
                )}
                {cuisineCrowding && (
                  <StatTile
                    label="Cuisine crowding" color={MARKET_COLOR.trends}
                    value={<>{cuisineCrowding.matching_count}<span className="text-xs font-normal text-[var(--color-text-faint)]">/{cuisineCrowding.total_checked}</span></>}
                    sub={`also serve ${cuisineCrowding.cuisine}`}
                  />
                )}
                {vegMix && (
                  <StatTile
                    label="Veg / non-veg mix" color="#16A34A"
                    value={<>{vegMix.veg_count}<span className="text-xs font-normal text-[var(--color-text-faint)]">/{vegMix.total}</span></>}
                    sub="are pure-veg only"
                  />
                )}
              </div>
            )}
          </Card>
          </div>
        )}

        {(landscapeSummary || occupancy) && (
          <div className="flex flex-col gap-4">
          {landscapeSummary && (
          <Card title="Nearby Market Landscape" source="Swiggy nearby restaurants, area aggregate" concept icon={<IconStorefront />} color={MARKET_COLOR.landscape}>
            {positioning && (
              <div className="rounded-lg border border-blue-400/25 bg-blue-400/[0.07] p-4">
                <p className="text-base text-[var(--color-text-primary)]">
                  Estimated <span className="font-mono font-semibold">₹{positioning.your_cost_for_two_estimate}</span> for two
                  ranks <span className="font-semibold text-[var(--color-accent)]">#{positioning.rank} of {positioning.total}</span> nearby options
                </p>
                {/* Position bar -- fills space with a genuine visualisation
                    instead of leaving the card looking sparse next to the
                    chart-heavy Menu & Pricing tile it's stretched to match. */}
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-[var(--color-border-soft)]">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent)]"
                    style={{ width: `${Math.max(6, 100 - ((positioning.rank - 1) / Math.max(1, positioning.total - 1)) * 100)}%` }}
                  />
                </div>
                <p className="mt-1.5 text-[10px] text-[var(--color-text-faint)]">
                  cheaper than {positioning.cheaper_than_count} · pricier than {positioning.pricier_than_count}
                </p>
              </div>
            )}
            <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <StatTile label="Nearby options" color={MARKET_COLOR.landscape} value={landscapeSummary.count} />
              {landscapeSummary.avg_rating !== null && (
                <StatTile label="Avg rating" color={MARKET_COLOR.landscape} value={<>{landscapeSummary.avg_rating}★</>} />
              )}
              {landscapeSummary.cost_for_two_min !== null && (
                <StatTile label="Cost for two range" color={MARKET_COLOR.landscape} value={<>₹{landscapeSummary.cost_for_two_min}–₹{landscapeSummary.cost_for_two_max}</>} />
              )}
            </div>

            {/* mt-auto -- pins to the bottom of the stretched card height
                regardless of whether the content above filled it. */}
            <div className="mt-auto pt-4">
              {landscapeSummary.offers_count > 0 ? (
                <div className="flex items-center gap-3 rounded-lg border border-amber-500/25 bg-amber-500/[0.06] p-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white shadow-sm">
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5.586a1 1 0 01.707.293l6.414 6.414a1 1 0 010 1.414l-8.586 8.586a1 1 0 01-1.414 0l-6.414-6.414A1 1 0 013 12.586V7a4 4 0 014-4z" />
                    </svg>
                  </span>
                  <p className="text-xs font-semibold text-amber-700 dark:text-amber-200">
                    {landscapeSummary.offers_count} nearby option{landscapeSummary.offers_count !== 1 ? "s" : ""} running an active offer
                  </p>
                </div>
              ) : (
                <div className="flex items-center gap-2 rounded-lg border border-blue-400/25 bg-blue-400/[0.07] px-3 py-2.5">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                  <p className="text-xs text-[var(--color-text-faint)]">No active offers reported nearby right now.</p>
                </div>
              )}
            </div>
          </Card>
          )}

          {occupancy && (
          <Card title="Area Occupancy" source="Swiggy Dineout availability, area aggregate" concept icon={<IconClock />} color={MARKET_COLOR.occupancy}>
            <div className="space-y-4">
              {occupancy.signal ? (
                <div className="space-y-2 rounded-lg border border-blue-400/25 bg-blue-400/[0.07] p-4">
                  <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                    occupancy.signal === "HIGH" ? "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-300"
                    : occupancy.signal === "MEDIUM" ? "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-300"
                    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300"
                  }`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${
                      occupancy.signal === "HIGH" ? "bg-rose-400" : occupancy.signal === "MEDIUM" ? "bg-amber-400" : "bg-emerald-400"
                    }`} />
                    {occupancy.signal} occupancy area
                  </span>
                  <p className="text-xs text-[var(--color-text-soft)]">
                    {occupancy.signal === "HIGH"
                      ? "Nearby restaurants are nearly full, so expect walk-in overflow tonight."
                      : occupancy.signal === "MEDIUM"
                      ? "Nearby restaurants have moderate availability tonight."
                      : "Nearby restaurants have ample availability, so no unusual demand pressure is expected."}
                  </p>
                  <p className="text-[10px] text-[var(--color-text-ghost)]">{occupancy.competitors_checked} restaurant(s) checked</p>
                </div>
              ) : (
                <p className="text-xs text-[var(--color-text-ghost)] italic">Occupancy data unavailable, add a Dineout saved location to your Swiggy account.</p>
              )}
              {slotAvailability.length > 0 && (
                <div className="border-t border-[var(--color-border-soft)] pt-4">
                  <OccupancyBySlotChart data={slotAvailability} />
                </div>
              )}
            </div>
          </Card>
          )}
          </div>
        )}
      </div>

      {/* Ingredient Price Lookup -- on-demand, your own procurement, not competitor data */}
      <IngredientPriceLookup />
    </div>
  );
}

const CONDITION_STYLES: Record<MarketWeather["condition"], { label: string; tile: string }> = {
  heavy_rain: { label: "Heavy rain expected", tile: "from-blue-300/20 to-rose-400/20" },
  light_rain: { label: "Light rain possible",  tile: "from-blue-300/20 to-amber-400/20" },
  very_hot:   { label: "Hot evening",          tile: "from-amber-400/20 to-orange-400/20" },
  clear:      { label: "Clear",                tile: "from-sky-400/20 to-emerald-400/20" },
};

function WeatherIcon({ condition }: { condition: MarketWeather["condition"] }) {
  const showRain = condition === "heavy_rain" || condition === "light_rain";
  const showBolt = condition === "heavy_rain";
  const showSun  = condition === "very_hot" || condition === "clear";

  return (
    <div className={`grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-gradient-to-br ${CONDITION_STYLES[condition].tile}`}>
      <svg viewBox="0 0 64 64" className="h-10 w-10" aria-hidden="true">
        {showSun && (
          <circle cx="32" cy="26" r="11" fill="#f5be73" />
        )}
        <path
          d="M20 34c-5 0-9-4-9-9s4-9 9-9c1.5-4.5 5.7-8 10.8-8 6.1 0 11.1 4.6 11.8 10.5 4.6.7 8.1 4.6 8.1 9.3 0 5.2-4.2 9.4-9.4 9.4H20z"
          fill="#93B4E0"
          opacity={showSun ? 0.5 : 0.85}
        />
        {showRain && (
          <>
            <path d="M22 40l-3 7" stroke="#60a5fa" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M32 40l-3 7" stroke="#60a5fa" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M42 40l-3 7" stroke="#60a5fa" strokeWidth="2.5" strokeLinecap="round" />
          </>
        )}
        {showBolt && (
          <path d="M33 38l-6 10h5l-2 8 8-11h-5l3-7z" fill="#f5be73" stroke="#c98a1f" strokeWidth="0.5" />
        )}
      </svg>
    </div>
  );
}

function WeatherHolidayCard({
  weather,
  upcomingHoliday,
}: {
  weather: MarketWeather | null | undefined;
  upcomingHoliday: MarketUpcomingHoliday | null | undefined;
}) {
  const holidaySoon = upcomingHoliday && upcomingHoliday.days_away > 0 && upcomingHoliday.days_away <= 7;

  return (
    <Card title="Weather & Holidays" source="Open-Meteo + internal calendar" swiggy={false} titleIcon={<IconCloud className="h-4 w-4 shrink-0 text-[var(--color-text-faint)]" />}>
      {!weather && <UnavailableNote text="Weather signal unavailable right now." />}
      {weather && (
        <div className="flex items-start gap-4">
          <WeatherIcon condition={weather.condition} />
          <div className="min-w-0 flex-1">
            <p className="text-lg font-bold text-[var(--color-text-primary)]">{CONDITION_STYLES[weather.condition].label}</p>
            <p className="mt-2 text-[13px] leading-relaxed text-[var(--color-text-soft)]">{weather.signal}</p>
          </div>
        </div>
      )}

      {/* Real numbers, not just prose -- gives the card the same tinted
          stat-tile texture as every other card on the page instead of
          reading as two boxes with a wall of plain text between them. */}
      {weather && (weather.avg_precipitation_pct !== null || weather.avg_temp_celsius !== null) && (
        <div className="mt-4 grid grid-cols-2 gap-2">
          {weather.avg_precipitation_pct !== null && (
            <StatTile label="Rain chance" color={MARKET_COLOR.weather} value={`${weather.avg_precipitation_pct.toFixed(0)}%`} />
          )}
          {weather.avg_temp_celsius !== null && (
            <StatTile label="Avg temp" color={MARKET_COLOR.weather} value={`${weather.avg_temp_celsius.toFixed(0)}°C`} />
          )}
        </div>
      )}

      {/* Always show a holiday line -- previously this box vanished
          entirely on any day with no holiday due today or very soon, which
          read as if the signal just hadn't loaded. Styled by proximity:
          today is the loudest, within a week gets a warm highlight, further
          out is a quiet mention -- rather than one flat neutral box always. */}
      <div
        className={`mt-4 flex items-center gap-2.5 rounded-lg border px-3 py-2.5 ${
          upcomingHoliday && upcomingHoliday.days_away === 0
            ? "border-[var(--color-accent)]/40 bg-[var(--color-accent-soft)]"
            : holidaySoon
            ? "border-amber-500/30 bg-amber-500/[0.08]"
            : "border-blue-400/25 bg-blue-400/[0.07]"
        }`}
      >
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
          style={{
            background: upcomingHoliday && upcomingHoliday.days_away === 0 ? "var(--color-accent)" : holidaySoon ? "#D97706" : "rgba(96,165,250,0.16)",
            color: upcomingHoliday && (upcomingHoliday.days_away === 0 || holidaySoon) ? "#fff" : "#60A5FA",
          }}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </span>
        {upcomingHoliday && upcomingHoliday.days_away === 0 ? (
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-accent)]">Holiday today</p>
            <p className="text-[13px] font-medium text-[var(--color-text-primary)]">{upcomingHoliday.name}</p>
          </div>
        ) : holidaySoon ? (
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700 dark:text-amber-400">Coming up</p>
            <p className="text-[13px] font-medium text-[var(--color-text-primary)]">
              {upcomingHoliday!.name} · {upcomingHoliday!.days_away === 1 ? "tomorrow" : `in ${upcomingHoliday!.days_away} days`}
            </p>
          </div>
        ) : (
          <div className="min-w-0">
            <p className="text-[13px] text-[var(--color-text-faint)]">No holiday today</p>
            {upcomingHoliday && (
              <p className="text-[10px] text-[var(--color-text-ghost)]">
                Next: {upcomingHoliday.name} (in {upcomingHoliday.days_away} days)
              </p>
            )}
          </div>
        )}
      </div>

      {/* mt-auto -- pins this to the bottom of the card's stretched height
          (Card's children wrapper is a flex column) instead of leaving a
          dead gap under it whenever a row-sibling's content runs longer. */}
      {weather && (
        <div className="mt-auto grid grid-cols-2 gap-2 pt-4">
          <TrendStat label="Delivery" value={weather.delivery_impact} />
          <TrendStat label="Dine-in" value={weather.dinein_impact} />
        </div>
      )}
    </Card>
  );
}

// SaaS-style trend stat: icon direction + color derived from the sign of
// the value itself (e.g. "+35%" vs "-20%"), tinted tile instead of a flat
// divided box -- matches the StatTile language used on every other card.
function TrendStat({ label, value }: { label: string; value: string }) {
  const isUp = value.trim().startsWith("+");
  const isDown = value.trim().startsWith("-");
  const color = isUp ? "#059669" : isDown ? "#E11D48" : "#60A5FA";

  return (
    <div className="flex items-center gap-2.5 rounded-lg border p-3" style={{ background: `${color}0f`, borderColor: `${color}30` }}>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white shadow-sm" style={{ background: color }}>
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
          {isUp ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          ) : isDown ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 17h8m0 0v-8m0 8l-8-8-4 4-6-6" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14" />
          )}
        </svg>
      </span>
      <div className="min-w-0">
        <p className="text-[9px] font-semibold uppercase tracking-widest text-[var(--color-text-faint)]">{label}</p>
        <p className="mt-0.5 text-lg font-bold" style={{ color }}>{value}</p>
      </div>
    </div>
  );
}

function TrendBullets({ bullets }: { bullets: string[] }) {
  return (
    <ul className="space-y-4">
      {bullets.map((line, i) => (
        <li key={i} className="flex gap-3 text-[13px] leading-relaxed text-[var(--color-text-soft)]">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-accent)]" />
          <span>{line.replace(/^[-•*]\s*/, "")}</span>
        </li>
      ))}
    </ul>
  );
}

// Lightweight modal for the full trends list -- matches the app's existing
// modal language (backdrop + card, modalIn/backdropIn keyframes already in
// globals.css) without pulling in DashboardDetailModal's heavier agent-detail
// chrome (eyebrow label, meta chips, key-takeaways grid) that doesn't apply here.
function TrendsModal({ bullets, onClose }: { bullets: string[]; onClose: () => void }) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[70]">
      <button
        aria-label="Close industry trends modal"
        className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-[backdropIn_0.15s_ease_both]"
        onClick={onClose}
      />
      <div className="absolute inset-x-4 top-10 mx-auto max-w-xl md:inset-x-auto md:left-1/2 md:-translate-x-1/2">
        <div className="card max-h-[80vh] flex flex-col rounded-2xl overflow-hidden border-[var(--color-border-default)] shadow-2xl animate-[modalIn_0.2s_ease-out_both]">
          <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border-soft)] bg-[var(--color-surface-raised)] px-5 py-4">
            <div>
              <p className="text-[15px] font-bold text-[var(--color-text-primary)]">Industry Trends</p>
              <p className="text-[11.5px] font-medium text-[var(--color-text-soft)]">via curated RSS trade press</p>
            </div>
            <button
              onClick={onClose}
              className="rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-sunken)] px-3 py-1.5 text-xs text-[var(--color-text-soft)] hover:bg-[var(--color-surface-sunken)] transition-colors"
            >
              close
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-5">
            <TrendBullets bullets={bullets} />
          </div>
        </div>
      </div>
    </div>
  );
}

function IndustryTrendsCard({ trends }: { trends: MarketIndustryTrends | null | undefined }) {
  const [showAll, setShowAll] = useState(false);
  const bullets = trends ? trends.digest.split("\n").map((line) => line.trim()).filter(Boolean) : [];
  const visible = bullets.slice(0, 5);

  return (
    <Card title="Industry Trends" source="curated RSS trade press" swiggy={false} titleIcon={<IconNewspaper className="h-4 w-4 shrink-0 text-[var(--color-text-faint)]" />}>
      {!trends && <UnavailableNote text="Industry trends unavailable right now." />}
      {trends && <TrendBullets bullets={visible} />}
      {bullets.length > 5 && (
        <div className="mt-auto pt-3">
          <button
            onClick={() => setShowAll(true)}
            className="text-xs font-medium text-[var(--color-accent)] hover:underline"
          >
            View all →
          </button>
        </div>
      )}
      {showAll && <TrendsModal bullets={bullets} onClose={() => setShowAll(false)} />}
    </Card>
  );
}

function AlertDocIcon() {
  return (
    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg" style={{ background: `${MARKET_COLOR.alerts}14` }}>
      <svg className="h-4 w-4" style={{ color: MARKET_COLOR.alerts }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    </div>
  );
}

function ComplianceAlertsCard({ alerts }: { alerts: MarketComplianceAlerts | null | undefined }) {
  const [showAll, setShowAll] = useState(false);
  const notices = alerts?.notices ?? [];
  const visible = showAll ? notices : notices.slice(0, 5);

  return (
    <Card title="Regulatory Alerts" source="FSSAI public notices" swiggy={false} titleIcon={<IconShieldAlert className="h-4 w-4 shrink-0 text-[var(--color-text-faint)]" />}>
      {!alerts && <UnavailableNote text="Regulatory alerts unavailable right now." />}
      {alerts && notices.length === 0 && <UnavailableNote text="No regulatory notices tracked right now." />}
      {notices.length > 0 && (
        <>
          <ul className="space-y-3">
            {visible.map((n, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <AlertDocIcon />
                <div className="min-w-0 flex-1">
                  <a
                    href={n.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="line-clamp-2 text-[13px] font-medium text-[var(--color-text-primary)] hover:text-[var(--color-accent)] hover:underline"
                  >
                    {n.title}
                  </a>
                  <p className="mt-0.5 text-[10px] text-[var(--color-text-ghost)]">uploaded {n.uploaded_on}</p>
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-auto pt-3">
            {notices.length > 5 ? (
              <button
                onClick={() => setShowAll((v) => !v)}
                className="flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline"
              >
                {showAll ? "Show fewer alerts" : "View all alerts"} →
              </button>
            ) : (
              <p className="text-[10px] text-[var(--color-text-ghost)]">{alerts?.notice_count} notice{alerts?.notice_count !== 1 ? "s" : ""} tracked</p>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

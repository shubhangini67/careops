"use client";

import { useEffect, useState } from "react";
import { getDataHealth } from "@/lib/api";
import { DataHealth } from "@/types/planning";

// Same visual system as RunHistorySection.tsx / AnalyticsDetail.tsx: icon
// badge header, .card .card-lift containers (not flat border boxes), and a
// distinct warm-family color per tile/section instead of one grey repeated
// everywhere.

function IconDeliveryBag(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M6 7h12l1 13H5L6 7z" /><path strokeLinecap="round" strokeLinejoin="round" d="M9 10V6a3 3 0 016 0v4" /></svg>;
}
function IconCalendar(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" /></svg>;
}
function IconHeart(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M12 21s-7.5-5.36-9.86-9.86C.7 8.06 2.1 5 5.2 4.3c2-.45 3.65.5 4.8 2.02C11.15 4.8 12.8 3.85 14.8 4.3c3.1.7 4.5 3.76 3.06 6.84C19.5 15.64 12 21 12 21z" /></svg>;
}
function IconBox(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>;
}
function IconMenu(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.2" /></svg>;
}
function IconTable(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 6h18M3 14h18M3 18h18" /></svg>;
}
function IconPulse(p: React.SVGProps<SVGSVGElement>) {
  return <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...p}><path strokeLinecap="round" strokeLinejoin="round" d="M3 12h4l2-8 4 16 2-8h6" /></svg>;
}

const SECTION_COLOR = {
  dataHealth: "#0891B2",
  scenarios: "#D97706",
  signals: "#E11D48",
} as const;

function CardHeader({ title, sub, icon, color }: { title: string; sub?: string; icon: React.ReactNode; color: string }) {
  return (
    <div className="mb-4 flex items-center gap-3">
      <span
        className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white shadow-sm"
        style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</h2>
        {sub && <p className="mt-0.5 text-xs text-[var(--color-text-faint)]">{sub}</p>}
      </div>
    </div>
  );
}

export default function DataHealthSection() {
  const [data,  setData]  = useState<DataHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDataHealth()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load data health"));
  }, []);

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      {!data ? (
        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card rounded-2xl p-5 animate-pulse">
              <div className="h-9 w-9 rounded-xl bg-[var(--color-surface-sunken)] mb-4" />
              <div className="h-2.5 w-20 rounded bg-[var(--color-surface-sunken)] mb-4" />
              <div className="h-8 w-16 rounded bg-[var(--color-surface-sunken)] mb-3" />
              <div className="h-2.5 w-32 rounded bg-[var(--color-surface-sunken)]" />
            </div>
          ))}
        </section>
      ) : (
        <>
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
            <HealthCard title="Encounters"   value={data.orders.count}       detail={range(data.orders.date_range)}                                    icon={<IconDeliveryBag className="h-4.5 w-4.5" />} color="#FF5200" stagger={1} />
            <HealthCard title="Appointments" value={data.reservations.count} detail={range(data.reservations.date_range)}                              icon={<IconCalendar className="h-4.5 w-4.5" />}    color="#0891B2" stagger={2} />
            <HealthCard title="Feedback"     value={data.feedback.count}     detail={`${data.feedback.negative} negative (${data.feedback.negative_pct}%)`} icon={<IconHeart className="h-4.5 w-4.5" />}    color="#E11D48" stagger={3} />
            <HealthCard title="Supplies"     value={data.inventory.items}    detail={`${data.inventory.critical_shortages} critical shortages`}         icon={<IconBox className="h-4.5 w-4.5" />}         color="#059669" stagger={4} />
            <HealthCard title="Departments"  value={data.menu.items}         detail="active departments"                                               icon={<IconMenu className="h-4.5 w-4.5" />}        color="#D97706" stagger={5} />
          </section>

          <section className="grid grid-cols-1 gap-5 xl:grid-cols-12">
            <div className="card card-lift rounded-2xl p-5 xl:col-span-7">
              <CardHeader
                title="Scenario Coverage"
                sub="Best upcoming demo dates with appointment pressure in the database."
                icon={<IconTable className="h-4 w-4" />}
                color={SECTION_COLOR.scenarios}
              />
              <div className="overflow-hidden rounded-lg border border-[var(--color-border-default)]">
                <table className="w-full text-left text-sm">
                  <thead className="bg-[var(--color-surface-sunken)] text-xs uppercase tracking-[0.14em] text-[var(--color-text-faint)]">
                    <tr>
                      <th className="px-3 py-3">Scenario</th>
                      <th className="px-3 py-3">Date</th>
                      <th className="px-3 py-3">Bookings</th>
                      <th className="px-3 py-3">Patients</th>
                      <th className="px-3 py-3">Waitlist</th>
                      <th className="px-3 py-3">Load</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border-soft)]">
                    {data.scenario_coverage.map((row) => (
                      <tr key={`${row.scenario}-${row.date}`} className="hover:bg-[var(--color-surface-raised)] transition-colors duration-150">
                        <td className="px-3 py-3">{row.label}</td>
                        <td className="px-3 py-3 text-xs tabular-nums text-[var(--color-text-soft)]">{row.date}</td>
                        <td className="px-3 py-3">{row.reservations}</td>
                        <td className="px-3 py-3">{row.guests}</td>
                        <td className="px-3 py-3">{row.waitlist}</td>
                        <td className="px-3 py-3">{row.occupancy_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card card-lift rounded-2xl p-5 xl:col-span-5">
              <CardHeader title="Operational Signals" icon={<IconPulse className="h-4 w-4" />} color={SECTION_COLOR.signals} />
              <div className="space-y-3">
                <Signal label="Shortage alerts" value={data.inventory.shortage_alerts} />
                <Signal label="Critical shortages" value={data.inventory.critical_shortages} />
                <Signal label="Overstock alerts" value={data.inventory.overstock_alerts} />
                <Signal label="Positive feedback" value={data.feedback.positive} />
                <Signal label="Neutral feedback" value={data.feedback.neutral} />
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function HealthCard({
  title, value, detail, icon, color, stagger,
}: { title: string; value: number; detail: string; icon: React.ReactNode; color: string; stagger: number }) {
  return (
    <div className={`rounded-2xl bg-[var(--color-surface-raised)] p-5 shadow-sm ring-1 ring-[var(--color-border-soft)] stagger-${stagger}`}>
      <span
        className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white shadow-sm"
        style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
      >
        {icon}
      </span>
      <p className="mt-3 text-xs uppercase tracking-[0.16em] text-[var(--color-text-faint)]">{title}</p>
      <p className="mt-1.5 text-3xl font-bold text-[var(--color-text-primary)] tabular-nums">{value}</p>
      <p className="mt-2 text-xs text-[var(--color-text-soft)]">{detail}</p>
    </div>
  );
}

function Signal({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-[var(--color-surface-sunken)] px-3 py-3">
      <span className="text-sm text-[var(--color-text-soft)]">{label}</span>
      <span className="text-sm font-semibold tabular-nums text-[var(--color-text-primary)]">{value}</span>
    </div>
  );
}

function range(values: Array<string | null>) {
  const [start, end] = values;
  return `${start ?? "-"} to ${end ?? "-"}`;
}

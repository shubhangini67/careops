"use client";

import AnalyticsDetail from "@/components/analytics/AnalyticsDetail";
import PageHeading from "@/components/ui/PageHeading";

export default function AnalyticsPage() {
  return (
    <main className="min-h-screen page-canvas px-5 py-6 text-[var(--color-text-primary)] xl:px-8">
      <div className="mx-auto max-w-[1520px] space-y-6">
        <PageHeading
          title="Capacity Forecast"
          description={
            <>
              <span className="flex flex-wrap gap-1.5">
                {["Capacity trends", "Department load", "Safety incidents", "Supply levels"].map((t) => (
                  <span
                    key={t}
                    className="rounded-full px-2.5 py-1 text-[11.5px] font-semibold"
                    style={{ background: "rgba(255,82,0,0.08)", color: "var(--color-accent)" }}
                  >
                    {t}
                  </span>
                ))}
              </span>
              <span className="mt-2 block text-[13px] text-[var(--color-text-faint)]">
                Historical trends, not a daily trigger-time decision.
              </span>
            </>
          }
        />

        <AnalyticsDetail />
      </div>
    </main>
  );
}

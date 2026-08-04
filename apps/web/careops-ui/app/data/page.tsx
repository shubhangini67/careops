"use client";

// P6-A28 -- merges the old /runs (plan run history) and /data-health (sync
// status, freshness) pages into one Data page, and adds an Action Queue
// history section that had no home anywhere before. Also fixes the /runs/{id}
// deep-link 404: there was never a dynamic route for it, so this page reads
// the id from ?run=<id> instead (same convention /dashboard already uses).
//
// Restructured into tabs -- Run History / Observability / Data Health used
// to render stacked one below the other on one long page, which conflated
// three different jobs ("what did the plan say", "what is this costing us
// in LLM infra", "is the underlying data fresh") into a single scroll.
// Observability was pulled out of DataHealthSection into its own
// ObservabilitySection component so it could become its own tab rather than
// bundled under Data Health.

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import RunHistorySection from "@/components/data/RunHistorySection";
import DataHealthSection from "@/components/data/DataHealthSection";
import ObservabilitySection from "@/components/data/ObservabilitySection";
import PageHeading from "@/components/ui/PageHeading";

type TabId = "history" | "observability" | "health";

const TABS: { id: TabId; label: string; tone: string }[] = [
  { id: "history",       label: "Run History",   tone: "bg-ember-400/70" },
  { id: "observability", label: "Observability",  tone: "bg-emerald-300/70" },
  { id: "health",        label: "Data Health",    tone: "bg-cyan-300/70" },
];

function DataPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const runParam = searchParams.get("run");
  const tabParam = searchParams.get("tab");

  // A ?run=<id> deep link always means "show me this run" -- land on the
  // History tab regardless of whatever ?tab was also in the URL.
  const initialTab: TabId = runParam
    ? "history"
    : tabParam === "observability" || tabParam === "health"
      ? tabParam
      : "history";

  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [initialRunId] = useState<number | undefined>(runParam ? Number(runParam) : undefined);

  function selectTab(tab: TabId) {
    setActiveTab(tab);
    const qs = tab === "history" && runParam ? `?tab=${tab}&run=${runParam}` : `?tab=${tab}`;
    router.replace(`/data${qs}`, { scroll: false });
  }

  // Keeps ?run=<id> in the URL for whichever run is currently on screen
  // (rather than reading it once and stripping it) -- refreshing, sharing,
  // or hitting back/forward now lands back on the same run instead of
  // resetting to the newest one.
  function handleRunChange(id: number) {
    if (String(id) !== runParam) router.replace(`/data?tab=history&run=${id}`, { scroll: false });
  }

  return (
    <main className="min-h-screen page-canvas px-5 py-6 text-[var(--color-text-primary)] xl:px-8">
      <div className="mx-auto max-w-[1520px] space-y-6">

        <PageHeading
          title="Data"
          description="Every plan your hospital has run and the source data behind it."
        />

        <div className="flex gap-1 rounded-lg bg-[var(--color-surface-sunken)] p-1 w-fit">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => selectTab(tab.id)}
              className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors duration-150 ${
                activeTab === tab.id
                  ? "bg-[var(--color-surface-raised)] text-[var(--color-text-primary)] shadow-sm"
                  : "text-[var(--color-text-faint)] hover:text-[var(--color-text-soft)]"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${tab.tone}`} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Each section owns its own icon+title+subtitle header now (matching
            the reference-image redesign's visual system), so there's no
            page-level SectionHeader here -- that would just repeat the same
            title a second time above whichever tab is active. */}
        <div className="space-y-4">
          {activeTab === "history" && (
            <RunHistorySection initialRunId={initialRunId} onRunChange={handleRunChange} />
          )}
          {activeTab === "observability" && <ObservabilitySection />}
          {activeTab === "health" && <DataHealthSection />}
        </div>

      </div>
    </main>
  );
}

export default function DataPage() {
  return (
    <Suspense fallback={null}>
      <DataPageContent />
    </Suspense>
  );
}

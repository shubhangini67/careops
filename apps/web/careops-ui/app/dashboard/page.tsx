"use client";

// P6-A30 -- /dashboard now only shows the overview/idle state (health score,
// KPIs, live intelligence, scenario trigger); the "watch a plan run and
// inspect results" experience moved to /planning. Triggering a scenario here
// hands the request off via DashboardContext.pendingTrigger and navigates --
// useFridayRush's SSE stream isn't route-bound, so it has to be mounted on
// /planning itself, not kept alive across this navigation.

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import TodayIdleState from "@/components/dashboard/TodayIdleState";
import { useAuth } from "@/context/AuthContext";
import { useDashboardCtx } from "@/context/DashboardContext";
import { listPlanningRuns } from "@/lib/api";
import { PlanningScenarioOption, ScenarioProfile } from "@/types/planning";

function DashboardPageContent() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const dashCtx = useDashboardCtx();
  const [historyCount, setHistoryCount] = useState(0);

  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [user, authLoading, router]);

  useEffect(() => {
    listPlanningRuns(50).then(rows => setHistoryCount(rows.length)).catch(() => {});
  }, []);

  // Old /dashboard?run=<id> bookmarks (pre-P6-A30) -- run detail viewing now
  // lives on /planning, not here.
  useEffect(() => {
    const runId = searchParams.get("run");
    if (runId) router.replace(`/planning?run=${runId}`);
  }, [searchParams, router]);

  const selectedScenario = (dashCtx?.selectedScenario ?? "ed_surge") as PlanningScenarioOption["id"];

  const handleRun = (date?: string, restaurantName?: string, restaurantId?: number, customProfile?: ScenarioProfile, scenarioOverride?: string) => {
    dashCtx?.setPendingTrigger({
      targetDate: date,
      scenario: scenarioOverride ?? selectedScenario,
      restaurantId,
      restaurantName: restaurantName ?? user?.org_name ?? null,
      customProfile,
    });
    router.push("/planning");
  };

  if (authLoading || !user) return null;

  return (
    <div className="min-h-screen page-canvas text-[var(--color-text-primary)]">
      <main className="mx-auto w-full max-w-[1520px] px-6 py-8 xl:px-14">
        <TodayIdleState
          onRun={handleRun}
          selectedScenario={selectedScenario}
          historyCount={historyCount}
          onShowHistory={() => router.push("/data")}
        />
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={null}>
      <DashboardPageContent />
    </Suspense>
  );
}

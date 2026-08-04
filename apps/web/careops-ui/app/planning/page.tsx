"use client";

// P6-A30 -- the flagship "trigger a plan, watch it run, inspect the result"
// experience, split out of /dashboard (which now only shows the overview/
// idle state -- see components/dashboard/TodayIdleState.tsx). This page owns
// the SSE stream (useFridayRush) and the run lifecycle (reset/history/status
// registered into DashboardContext), since useFridayRush's trigger() isn't
// route-bound -- it lives entirely inside whichever component mounts the
// hook, so /dashboard can't keep a stream alive across a navigation to here.
// Instead /dashboard sets DashboardContext.pendingTrigger and navigates;
// this page consumes+clears it on mount.

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AgentIntelligencePanel from "@/components/dashboard/AgentIntelligencePanel";
import AskAiBar from "@/components/dashboard/AskAiBar";
import CriticBanner from "@/components/dashboard/CriticBanner";
import ImmediateActionPlan from "@/components/dashboard/ImmediateActionPlan";
import PlanBriefing from "@/components/dashboard/PlanBriefing";
import PlanHeader from "@/components/dashboard/PlanHeader";
import PlanShiftModal from "@/components/dashboard/PlanShiftModal";
import SituationDrivers from "@/components/dashboard/SituationDrivers";
import WhatIfPanel from "@/components/dashboard/WhatIfPanel";
import PlanningIdleState from "@/components/planning/PlanningIdleState";
import { useAuth } from "@/context/AuthContext";
import { DashStatus, useDashboardCtx } from "@/context/DashboardContext";
import { useFridayRush } from "@/hooks/useFridayRush";
import { usePlanTriggerData } from "@/hooks/usePlanTriggerData";
import { downloadRunPdf, downloadRunExcel } from "@/lib/exportRun";
import { RunHistoryEntry } from "@/types/planning";
import { SCENARIO_OPTIONS } from "@/lib/scenarios";
import { PlanningScenarioOption } from "@/types/planning";

type NodeState = "idle" | "running" | "done";

// The 6-stage grouping shown to the user, each made up of the real SSE node
// keys graph.py's stream_planning_scenario emits start/complete events for
// (see _NODE_SSE_MAP) -- every key here genuinely fires its own event, none
// of this is simulated pacing. Stage "Analyzing Your Business" is the one
// real parallel fan-out (all 5 fire together, not sequentially), which is
// why it gets its own grid treatment below instead of a plain checklist.
interface Stage {
  key: string;
  title: string;
  description: string;
  nodes: string[];
}

const STAGES: Stage[] = [
  { key: "understand", title: "Understanding Your Scenario", description: "Resolving the hospital scenario and target date.", nodes: ["supervisor_router"] },
  { key: "forecast", title: "Capacity Forecast", description: "Projecting admission volume and bed pressure.", nodes: ["capacity_forecast"] },
  { key: "analyze", title: "Parallel Specialist Analysis", description: "3 agents working in parallel on FHIR, policy, and resources.", nodes: ["fhir_operations", "policy_rag", "resource_allocation"] },
  { key: "strategy", title: "Building the Operations Plan", description: "Combining every specialist's findings into one plan.", nodes: ["aggregator"] },
  { key: "review", title: "Safety Review", description: "The safety critic checks the plan before you see it.", nodes: ["safety_critic"] },
  { key: "briefing", title: "Approval Queue", description: "Packaging actions for human review.", nodes: ["human_approval_queue"] },
];

const TOTAL_TRACKED_NODES = STAGES.reduce((sum, s) => sum + s.nodes.length, 0);

const NODE_LABEL: Record<string, string> = {
  supervisor_router: "Scenario routing",
  capacity_forecast: "Capacity forecast",
  fhir_operations: "FHIR operations data",
  policy_rag: "Policy & SOP retrieval",
  resource_allocation: "Staff & bed allocation",
  aggregator: "Plan synthesis",
  safety_critic: "Safety critic",
  human_approval_queue: "Human approval queue",
};

const PARALLEL_AGENTS: { key: string; label: string; sub: string; dot: string; swiggy: boolean }[] = [
  { key: "fhir_operations",      label: "FHIR Operations",       sub: "Encounters, appointments, observations", dot: "bg-cyan-400",    swiggy: false },
  { key: "policy_rag",           label: "Policy Intelligence",   sub: "Hospital SOPs & regulatory guidance",      dot: "bg-violet-400",  swiggy: false },
  { key: "resource_allocation",  label: "Resource Allocation",   sub: "Beds, staff shifts, supply levels",        dot: "bg-emerald-400", swiggy: false },
];

function nodeState(key: string, completedNodes: Set<string>, startedNodes: Set<string>): NodeState {
  if (completedNodes.has(key)) return "done";
  if (startedNodes.has(key)) return "running";
  return "idle";
}

function stageStatus(stage: Stage, completedNodes: Set<string>, startedNodes: Set<string>): "done" | "active" | "pending" {
  if (stage.nodes.every((n) => completedNodes.has(n))) return "done";
  if (stage.nodes.some((n) => startedNodes.has(n) || completedNodes.has(n))) return "active";
  return "pending";
}

function StageIcon({ status }: { status: "done" | "active" | "pending" }) {
  if (status === "done") {
    return (
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-emerald-500/15">
        <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="relative grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[var(--color-accent)]/15">
        <span className="absolute inset-1 animate-ping rounded-full bg-[var(--color-accent)]/40" />
        <span className="relative h-2.5 w-2.5 rounded-full bg-[var(--color-accent)]" />
      </span>
    );
  }
  return <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[var(--color-surface-sunken)]"><span className="h-2 w-2 rounded-full bg-[var(--color-border-default)]" /></span>;
}

// Small real-data checklist row, used for stages with more than one real
// backend node (Gathering Context, Building the Strategy, Preparing Your
// Briefing) -- each row ticks only when that specific node's own
// node_complete event has actually arrived, never simulated pacing.
function SubNodeRow({ label, hint, state }: { label: string; hint?: string; state: NodeState }) {
  return (
    <div className="flex items-start gap-2.5 py-1">
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
        {state === "done" ? (
          <svg className="h-3.5 w-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        ) : state === "running" ? (
          <span className="relative flex h-2 w-2">
            <span className="absolute inset-0 animate-ping rounded-full bg-[var(--color-accent)] opacity-60" />
            <span className="relative h-2 w-2 rounded-full bg-[var(--color-accent)]" />
          </span>
        ) : (
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-border-default)]" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-[12.5px] font-medium transition-colors duration-300 ${state === "idle" ? "text-[var(--color-text-ghost)]" : "text-[var(--color-text-primary)]"}`}>{label}</p>
        {hint && state !== "idle" && (
          <p className="mt-0.5 text-[11px] leading-snug text-[var(--color-text-faint)]">{hint}</p>
        )}
      </div>
    </div>
  );
}

function AgentTile({ agent, state, hint }: { agent: typeof PARALLEL_AGENTS[number]; state: NodeState; hint?: string }) {
  return (
    <div className={`rounded-xl ring-1 px-3.5 py-3 transition-colors ${state === "done" ? "ring-emerald-400/25 bg-emerald-500/[0.05]" : state === "running" ? "ring-[var(--color-accent)]/25 bg-[var(--color-accent)]/[0.05]" : "ring-[var(--color-border-soft)] bg-[var(--color-surface-raised)]"}`}>
      <div className="flex items-center gap-2">
        {state === "done" ? (
          <svg className="h-3.5 w-3.5 shrink-0 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        ) : state === "running" ? (
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inset-0 animate-ping rounded-full bg-[var(--color-accent)] opacity-60" />
            <span className={`relative h-2 w-2 rounded-full ${agent.dot}`} />
          </span>
        ) : (
          <span className={`h-2 w-2 shrink-0 rounded-full ${agent.dot} opacity-30`} />
        )}
        <p className={`text-[12.5px] font-semibold ${state === "idle" ? "text-[var(--color-text-ghost)]" : "text-[var(--color-text-primary)]"}`}>{agent.label}</p>
        {agent.swiggy && state !== "idle" && (
          <span className="h-2 w-2 shrink-0 rounded-full bg-indigo-400/80" title="Live data" />
        )}
      </div>
      <p className="mt-1 text-[10.5px] leading-snug text-[var(--color-text-faint)]">
        {hint && state === "done" ? hint : agent.sub}
      </p>
    </div>
  );
}

function LoadingState({ completedNodes, startedNodes, nodeHints, replanCount, scenarioLabel, restaurantName }: {
  completedNodes: Set<string>;
  startedNodes:   Set<string>;
  nodeHints:      Record<string, string>;
  replanCount: number;
  scenarioLabel?: string;
  restaurantName?: string | null;
}) {
  const criticDone = completedNodes.has("safety_critic");
  const allAgentsDone = ["fhir_operations", "policy_rag", "resource_allocation", "aggregator"].every((k) => completedNodes.has(k));
  const isReplanning = replanCount > 0 && !allAgentsDone;

  const doneCount = STAGES.reduce((sum, s) => sum + s.nodes.filter((n) => completedNodes.has(n)).length, 0);
  const progressPct = Math.min(100, Math.round((doneCount / TOTAL_TRACKED_NODES) * 100));

  const activeStage = STAGES.find((s) => stageStatus(s, completedNodes, startedNodes) === "active");
  // The stage the expanded detail panel below the stepper shows -- the
  // earliest not-yet-done stage (whether it's actively running or just
  // "up next"), falling back to the last stage once everything is done.
  const currentStage = STAGES.find((s) => stageStatus(s, completedNodes, startedNodes) !== "done") ?? STAGES[STAGES.length - 1];
  const currentStatus = stageStatus(currentStage, completedNodes, startedNodes);

  return (
    <div className="py-10">
      <div className="mx-auto max-w-[560px] text-center mb-8">
        <div className="inline-flex items-center gap-2 rounded-full border border-ember-500/20 bg-ember-500/[0.08] px-3 py-1.5 mb-4">
          <span className="relative flex h-2 w-2">
            {!criticDone && <span className="absolute inset-0 animate-ping rounded-full bg-ember-400 opacity-50" />}
            <span className={`relative rounded-full ${criticDone ? "bg-emerald-400" : "bg-ember-400"}`} />
          </span>
          <span className="text-[10px] uppercase tracking-[0.24em] text-[var(--color-accent)]">
            {criticDone ? "Complete" : "Working"}
          </span>
        </div>
        <h1 className="text-[30px] font-semibold tracking-[-0.015em] text-[var(--color-text-primary)] leading-[1.1]">
          {criticDone ? "Your brief is ready." : (
            <>
              Preparing your brief,{" "}
              <span className="display-it text-[var(--color-accent)]">
                {restaurantName ?? "Director"}!
              </span>
            </>
          )}
        </h1>
        {!criticDone && scenarioLabel && (
          <p className="mt-2 text-[10px] uppercase tracking-[0.24em] text-[var(--color-text-faint)]">
            for the {scenarioLabel} scenario
          </p>
        )}
        <p className="mt-3 text-[13px] leading-[1.7] text-[var(--color-text-faint)] max-w-sm mx-auto">
          Seven specialists analyse capacity, FHIR data, hospital policies, and supply levels in parallel. A safety critic reviews the plan before you see it.
        </p>

        {/* Real progress: completed nodes / total tracked nodes -- no time
            estimate shown since we don't have a grounded per-node duration
            average to base one on yet. */}
        <div className="mt-5 mx-auto max-w-[360px]">
          <div className="h-1.5 rounded-full bg-[var(--color-surface-sunken)] overflow-hidden">
            <div className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-500" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="mt-1.5 text-[10.5px] uppercase tracking-[0.18em] text-[var(--color-text-faint)]">{progressPct}% complete</p>
        </div>
      </div>

      {replanCount > 0 && (
        <div className="mx-auto max-w-[520px] mb-5 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3 flex items-start gap-3">
          <span className="relative flex h-2 w-2 shrink-0 mt-1">
            <span className="absolute inset-0 animate-ping rounded-full bg-amber-400 opacity-60" />
            <span className="relative rounded-full bg-amber-400" />
          </span>
          <div>
            <p className="text-xs font-semibold text-amber-300">
              Auto-replan triggered — attempt {replanCount} of 2
            </p>
            <p className="text-[11px] text-amber-300/60 mt-0.5">
              The critic found issues in the initial plan. Replanning with corrected constraints — this is automatic, no action needed.
            </p>
          </div>
        </div>
      )}

      {/* Horizontal stepper -- one row, constant height no matter how much
          content any single stage has. Replaces the old vertical stack of
          all 6 fully-expanded stages, which made the page extremely tall. */}
      <div className="mx-auto flex max-w-[600px] items-start">
        {STAGES.map((stage, index) => {
          const status = stageStatus(stage, completedNodes, startedNodes);
          const isLast = index === STAGES.length - 1;
          return (
            <div key={stage.key} className={`flex items-start ${isLast ? "shrink-0" : "flex-1"}`}>
              <div className="flex shrink-0 flex-col items-center gap-1.5" style={{ width: 72 }}>
                <StageIcon status={status} />
                <p className={`text-center text-[9px] leading-tight transition-colors duration-300 ${status === "pending" ? "text-[var(--color-text-ghost)]" : "text-[var(--color-text-primary)]"}`}>
                  {stage.title}
                </p>
              </div>
              {!isLast && (
                <div className={`mt-3.5 h-px flex-1 transition-colors duration-300 ${status === "done" ? "bg-emerald-400/50" : "bg-[var(--color-border-soft)]"}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Expanded detail for whichever stage is current -- only one stage's
          real content is ever on screen at once. */}
      <div className="mx-auto mt-6 max-w-[600px] rounded-2xl ring-1 ring-[var(--color-border-soft)] bg-[var(--color-surface-raised)] p-5">
        <div className="flex items-center gap-3">
          <StageIcon status={currentStatus} />
          <div className="min-w-0">
            <p className="text-[15px] font-bold text-[var(--color-text-primary)]">{currentStage.title}</p>
            <p className="text-[11.5px] text-[var(--color-text-faint)]">{currentStage.description}</p>
          </div>
        </div>

        <div className="mt-4">
          {currentStage.key === "analyze" ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {PARALLEL_AGENTS.map((agent) => (
                <AgentTile key={agent.key} agent={agent} state={nodeState(agent.key, completedNodes, startedNodes)} hint={nodeHints[agent.key]} />
              ))}
            </div>
          ) : currentStage.nodes.length > 1 ? (
            currentStage.nodes.map((n) => (
              <SubNodeRow
                key={n}
                label={n === "critic" && replanCount > 0 ? `Quality review (retry ${replanCount} of 2)` : NODE_LABEL[n] ?? n}
                hint={nodeHints[n]}
                state={nodeState(n, completedNodes, startedNodes)}
              />
            ))
          ) : (
            <p className="text-[12px] leading-relaxed text-[var(--color-text-soft)]">
              {currentStage.key === "review" && replanCount > 0
                ? `Retry ${replanCount} of 2 — ${nodeHints[currentStage.nodes[0]] ?? "reviewing…"}`
                : nodeHints[currentStage.nodes[0]] ?? "Starting…"}
            </p>
          )}
        </div>
      </div>

      <div className="mt-5 text-center">
        {criticDone && replanCount === 0 ? (
          <div className="mx-auto max-w-[480px] rounded-xl bg-emerald-500/[0.06] ring-1 ring-emerald-400/25 px-5 py-3.5">
            <p className="text-sm font-semibold text-emerald-300">Plan approved. Loading your brief...</p>
          </div>
        ) : criticDone && replanCount > 0 ? (
          <div className="mx-auto max-w-[480px] rounded-xl bg-emerald-500/[0.06] ring-1 ring-emerald-400/25 px-5 py-3.5">
            <p className="text-sm font-semibold text-emerald-300">Plan finalised after {replanCount} replan{replanCount > 1 ? "s" : ""}. Loading your brief...</p>
          </div>
        ) : isReplanning ? (
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-faint)]">Fixing a few things — attempt {replanCount} of 2…</p>
        ) : activeStage ? (
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-faint)]">{activeStage.title}…</p>
        ) : null}
      </div>
    </div>
  );
}

function PlanningPageContent() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const dashCtx = useDashboardCtx();

  const { data, status, error, history, completedNodes, startedNodes, nodeHints, replanCount, trigger, reset, loadFromHistory } = useFridayRush();
  const [showWhatIf,       setShowWhatIf]       = useState(false);
  const [showRerunModal,   setShowRerunModal]   = useState(false);
  const [exportingPdf,     setExportingPdf]     = useState(false);
  const [exportingExcel,   setExportingExcel]   = useState(false);
  const { activeProfile } = usePlanTriggerData();
  const [runMeta, setRunMeta] = useState<{ scenarioLabel: string; restaurantName: string | null }>({ scenarioLabel: "", restaurantName: null });

  async function handleExportPdf() {
    const runId   = data?.meta?.planning_run_id as number | undefined;
    const scenario = data?.scenario ?? "run";
    if (!runId) return;
    setExportingPdf(true);
    try { await downloadRunPdf(runId, scenario); } catch (e) { console.error(e); }
    finally { setExportingPdf(false); }
  }

  async function handleExportExcel() {
    const runId   = data?.meta?.planning_run_id as number | undefined;
    const scenario = data?.scenario ?? "run";
    if (!runId) return;
    setExportingExcel(true);
    try { await downloadRunExcel(runId, scenario); } catch (e) { console.error(e); }
    finally { setExportingExcel(false); }
  }

  // Auth guard
  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [user, authLoading, router]);

  // Sync run status and reset fn to NavBar context -- /planning now owns
  // the run lifecycle (moved from /dashboard, P6-A30).
  useEffect(() => {
    dashCtx?.setDashStatus(status as DashStatus);
  }, [status, dashCtx]);

  useEffect(() => {
    dashCtx?.registerReset(reset);
  }, [reset, dashCtx]);

  // Consume a trigger request handed off from /dashboard (which no longer
  // owns the SSE stream -- see DashboardContext.pendingTrigger).
  useEffect(() => {
    const pending = dashCtx?.pendingTrigger;
    if (pending) {
      setRunMeta({
        scenarioLabel: pending.customProfile?.label ?? SCENARIO_OPTIONS.find(s => s.id === pending.scenario)?.label ?? pending.scenario,
        restaurantName: pending.restaurantName ?? user?.org_name ?? null,
      });
      trigger(pending.targetDate, pending.scenario, pending.restaurantId, pending.customProfile);
      dashCtx?.setPendingTrigger(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashCtx?.pendingTrigger]);

  // Deep-link a specific past run via ?run=<id> -- relocated from /dashboard
  // (P6-A30), preserves old /dashboard?run=<id> and /operations?run=<id>
  // bookmarks via their redirect shims. Deliberately does NOT strip the
  // param after loading (it used to, via router.replace("/planning")) --
  // that was the same "loses your place on refresh" bug the /data history
  // page had: keeping ?run=<id> in the URL is what makes reloading this
  // page, or the /data "View full plan" link, land back on the same run.
  useEffect(() => {
    const runId = searchParams.get("run");
    if (runId) {
      loadFromHistory({ id: Number(runId) } as RunHistoryEntry);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const selectedScenario = (dashCtx?.selectedScenario ?? "ed_surge") as PlanningScenarioOption["id"];

  const handleHistorySelect = async (entry: RunHistoryEntry) => {
    await loadFromHistory(entry);
  };

  const handleRun = (date?: string, restaurantName?: string, restaurantId?: number, customProfile?: import("@/types/planning").ScenarioProfile, scenarioOverride?: string) => {
    const effectiveScenario = scenarioOverride ?? selectedScenario;
    setRunMeta({
      scenarioLabel: customProfile?.label ?? SCENARIO_OPTIONS.find(s => s.id === effectiveScenario)?.label ?? effectiveScenario,
      restaurantName: restaurantName ?? user?.org_name ?? null,
    });
    // Starting a fresh live run makes any ?run=<id> from a previously
    // viewed historical run stale -- clear it so a refresh mid-run doesn't
    // reload the old one instead of showing this new run's progress.
    if (searchParams.get("run")) router.replace("/planning");
    trigger(date, effectiveScenario, restaurantId, customProfile);
  };

  if (authLoading || !user) return null;

  return (
    <div className="min-h-screen bg-[var(--color-surface-page)] text-[var(--color-text-primary)]">
      <main className="mx-auto w-full max-w-[1520px] px-6 py-8 xl:px-14">
        <div className="space-y-6">
          {status === "idle" && (
            <PlanningIdleState
              onRun={handleRun}
              selectedScenario={selectedScenario}
              history={history}
              onSelectHistory={handleHistorySelect}
              onShowAllHistory={() => router.push("/data")}
            />
          )}

          {status === "loading" && <LoadingState completedNodes={completedNodes} startedNodes={startedNodes} nodeHints={nodeHints} replanCount={replanCount} scenarioLabel={runMeta.scenarioLabel} restaurantName={runMeta.restaurantName} />}

          {status === "error" && error && (
            <div
              className="rounded-3xl border border-rose-500/20 px-6 py-5"
              style={{ background: "rgba(244,63,94,0.06)" }}
            >
              <p className="text-sm font-semibold text-rose-400">Something went wrong</p>
              <p className="mt-1 text-xs text-rose-300/80">{error}</p>
              <button
                onClick={() => trigger()}
                className="mt-4 text-xs text-rose-300 underline underline-offset-4"
              >
                retry
              </button>
            </div>
          )}

          {status === "success" && data && (
            <>
              <PlanHeader
                data={data}
                onExportPdf={handleExportPdf}
                onExportExcel={handleExportExcel}
                exportingPdf={exportingPdf}
                exportingExcel={exportingExcel}
                onWhatIf={() => setShowWhatIf(true)}
                onRerun={() => setShowRerunModal(true)}
              />

              {/* Single column -- the app already has a persistent left nav
                  (components/layout/Sidebar.tsx), so a second sticky column
                  here just crowded the page. Reads like an executive AI
                  briefing, progressively revealing more detail: Situation
                  (what's happening) -> Immediate Action Plan (the plan
                  itself) -> Situation Drivers, one-line glance + why per
                  specialist -> Agent Intelligence, full detail one click
                  away per specialist (the evidence) -> Critic Review
                  (trust) -> Ask AI (conversation). No separate KPI/
                  "Operational Snapshot" row: 5 of its 6 tiles just restated
                  a number Situation Drivers already shows WITH context (a
                  number alone vs. a number + why it matters), and the 6th
                  (menu focus) is already covered by the Do Now action item
                  and Agent Intelligence's Menu panel -- same repeated-
                  middle-layer problem as the old Inventory+Menu section. */}
              <div className="mt-6 space-y-6">
                <PlanBriefing data={data} />

                <ImmediateActionPlan data={data} />

                <SituationDrivers data={data} />

                <AgentIntelligencePanel data={data} />

                <CriticBanner critic={data.critic} />

                <button
                  onClick={() => router.push("/action-center")}
                  className="flex w-full items-center justify-between gap-2 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] px-4 py-2.5 text-left text-xs text-[var(--color-text-soft)] transition-colors hover:border-ember-500/30 hover:text-[var(--color-text-primary)]"
                >
                  Review supply approvals in Approval Queue
                  <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </button>

                <AskAiBar />
              </div>

              <PlanShiftModal
                open={showRerunModal}
                onClose={() => setShowRerunModal(false)}
                onRun={handleRun}
                activeProfile={activeProfile}
              />

              {showWhatIf && (() => {
                const fc      = data.recommendations?.forecast as Record<string, unknown> | null;
                const fcData  = (fc?.data as Record<string, unknown> | null) ?? fc;
                const baseCovers = Number(fcData?.forecast_24h ?? fcData?.predicted_orders ?? 0);
                const avgCovers  = Number(fcData?.forecast_48h ?? fcData?.avg_same_day_orders ?? fcData?.avg_friday_orders ?? baseCovers);
                const svcWindow  = (fcData?.service_window as string) ?? "08:00-20:00";
                return baseCovers > 0 ? (
                  <>
                    <div
                      className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm"
                      onClick={() => setShowWhatIf(false)}
                    />
                    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
                      <div
                        className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl bg-[var(--color-surface)] ring-1 ring-[var(--color-border-default)] shadow-[0_40px_80px_rgba(0,0,0,0.6)] pointer-events-auto"
                        style={{ animation: "fadeUp 0.2s ease-out" }}
                      >
                        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border-default)]">
                          <div>
                            <p className="text-[10px] uppercase tracking-[0.22em] text-[var(--color-accent)]/80">Simulator</p>
                            <h2 className="mt-0.5 text-base font-semibold text-[var(--color-text-primary)]">What-if Simulator</h2>
                          </div>
                          <button
                            onClick={() => setShowWhatIf(false)}
                            className="text-[var(--color-text-faint)] hover:text-[var(--color-text-soft)] transition-colors"
                          >
                            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                        <div className="px-6 py-5">
                          <WhatIfPanel
                            baseCovers={baseCovers}
                            avgCovers={avgCovers}
                            scenario={data.scenario ?? "ed_surge"}
                            serviceWindow={svcWindow}
                            defaultOpen
                          />
                        </div>
                      </div>
                    </div>
                    <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }`}</style>
                  </>
                ) : null;
              })()}
            </>
          )}
        </div>
      </main>

    </div>
  );
}

export default function PlanningPage() {
  return (
    <Suspense fallback={null}>
      <PlanningPageContent />
    </Suspense>
  );
}

// hooks/useFridayRush.ts
"use client";

import { useState, useCallback, useEffect } from "react";
import { getPlanningRun, listPlanningRuns, streamPlanningScenario } from "@/lib/api";
import { FridayRushRequest, FridayRushResponse, PlanningRunSummary, RunHistoryEntry, ScenarioProfile } from "@/types/planning";

type Status = "idle" | "loading" | "success" | "error";

interface UseFridayRushReturn {
  data:           FridayRushResponse | null;
  status:         Status;
  error:          string | null;
  history:        RunHistoryEntry[];
  completedNodes: Set<string>;
  startedNodes:   Set<string>;
  nodeHints:      Record<string, string>;
  replanCount:    number;
  trigger:        (targetDate?: string, scenario?: FridayRushRequest["scenario"], restaurantId?: number, customProfile?: ScenarioProfile) => Promise<void>;
  reset:          () => void;
  loadFromHistory: (entry: RunHistoryEntry) => Promise<void>;
  refreshHistory:  () => Promise<void>;
}

function toHistoryEntry(run: PlanningRunSummary): RunHistoryEntry {
  return {
    id: run.id,
    targetDate: run.target_date ?? "Next Friday",
    runAt: run.created_at ?? run.generated_at ?? new Date().toISOString(),
    status: run.status,
    verdict: run.critic_verdict ?? "unknown",
    // critic_score is stored as a 0-1 fraction everywhere in the backend --
    // every other consumer (RunHistorySection, DataHealthSection,
    // TodayIdleState) does Math.round(score * 100) before display; this was
    // the one place that didn't, so RunHistoryEntry.score silently carried
    // the raw fraction (e.g. 0.92 instead of 92) into whatever rendered it.
    score: run.critic_score != null ? Math.round(run.critic_score * 100) : null,
    scenario: run.scenario,
    scenarioLabel: run.scenario_label,
  };
}

export function useFridayRush(): UseFridayRushReturn {
  const [data,           setData]           = useState<FridayRushResponse | null>(null);
  const [status,         setStatus]         = useState<Status>("idle");
  const [error,          setError]          = useState<string | null>(null);
  const [history,        setHistory]        = useState<RunHistoryEntry[]>([]);
  const [completedNodes, setCompletedNodes] = useState<Set<string>>(new Set());
  const [startedNodes,   setStartedNodes]   = useState<Set<string>>(new Set());
  const [nodeHints,      setNodeHints]      = useState<Record<string, string>>({});
  const [replanCount,    setReplanCount]    = useState<number>(0);

  const refreshHistory = useCallback(async () => {
    const runs = await listPlanningRuns(10);
    setHistory(runs.map(toHistoryEntry));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshHistory().catch(() => {
        // History should not block the main planning experience.
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshHistory]);

  const trigger = useCallback(async (targetDate?: string, scenario: FridayRushRequest["scenario"] = "ed_surge", restaurantId?: number, customProfile?: ScenarioProfile) => {
    setStatus("loading");
    setError(null);
    setData(null);
    setCompletedNodes(new Set());
    setStartedNodes(new Set());
    setNodeHints({});
    setReplanCount(0);

    try {
      const stream = streamPlanningScenario({
        target_date: targetDate ?? null,
        simulation_mode: false,
        scenario,
        ...(restaurantId ? { restaurant_id: restaurantId } : {}),
        ...(customProfile ? { custom_profile: customProfile } : {}),
      });

      for await (const evt of stream) {
        if (evt.event === "node_start") {
          const { node, hint } = evt as { event: string; node: string; hint?: string };
          setStartedNodes(prev => new Set([...prev, node]));
          if (hint) setNodeHints(prev => ({ ...prev, [node]: hint }));
        } else if (evt.event === "node_complete") {
          const { node, hint } = evt as { event: string; node: string; hint?: string };
          setCompletedNodes(prev => new Set([...prev, node]));
          if (node === "replan") setReplanCount(prev => prev + 1);
          // Completion hint overwrites the start hint with a richer summary
          if (hint) setNodeHints(prev => ({ ...prev, [node]: hint }));
        } else if (evt.event === "complete") {
          const { event: _e, ...response } = evt as { event: string } & FridayRushResponse;
          setData(response as FridayRushResponse);
          setStatus("success");
          await refreshHistory();
        } else if (evt.event === "error") {
          const { message } = evt as { event: string; message: string };
          setError(message ?? "Unknown stream error");
          setStatus("error");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stream connection error");
      setStatus("error");
    }
  }, [refreshHistory]);

  const reset = useCallback(() => {
    setData(null);
    setStatus("idle");
    setError(null);
  }, []);

  const loadFromHistory = useCallback(async (entry: RunHistoryEntry) => {
    try {
      setStatus("loading");
      setError(null);
      if (entry.data) {
        setData(entry.data);
      } else {
        const detail = await getPlanningRun(Number(entry.id));
        setData(detail.final_response);
      }
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown history load error");
      setStatus("error");
    }
  }, []);

  return {
    data, status, error, history,
    completedNodes, startedNodes, nodeHints, replanCount,
    trigger, reset, loadFromHistory, refreshHistory,
  };
}

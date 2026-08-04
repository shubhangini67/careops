// hooks/useSelectedRun.ts
"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getPlanningRun, listPlanningRuns } from "@/lib/api";
import { FridayRushResponse } from "@/types/planning";

type Status = "loading" | "success" | "empty" | "error";

interface UseSelectedRunReturn {
  data:    FridayRushResponse | null;
  runId:   number | null;
  status:  Status;
  error:   string | null;
}

/**
 * Used by /market: reads ?run=<id> from the URL, falling back to the most
 * recent completed run when absent. Independent of the live SSE hook
 * (useFridayRush) on purpose -- /market shows a completed run's market
 * intelligence, not the in-progress streaming experience, so it doesn't
 * need to share that hook's state. (/dashboard handles its own ?run=<id>
 * deep link directly via loadFromHistory -- P6-A26, since /operations
 * -- the other historical consumer of this hook -- now just redirects there.)
 */
export function useSelectedRun(): UseSelectedRunReturn {
  const searchParams = useSearchParams();
  const runParam = searchParams.get("run");

  const [data,   setData]   = useState<FridayRushResponse | null>(null);
  const [runId,  setRunId]  = useState<number | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error,  setError]  = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setStatus("loading");
      setError(null);
      try {
        let id = runParam ? Number(runParam) : null;
        if (!id) {
          const recent = await listPlanningRuns(1);
          id = recent[0]?.id ?? null;
        }
        if (!id) {
          if (!cancelled) { setStatus("empty"); setData(null); setRunId(null); }
          return;
        }
        const detail = await getPlanningRun(id);
        if (!cancelled) {
          setData(detail.final_response);
          setRunId(id);
          setStatus("success");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load run");
          setStatus("error");
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, [runParam]);

  return { data, runId, status, error };
}

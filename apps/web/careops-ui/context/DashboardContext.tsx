"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";
import { ScenarioProfile } from "@/types/planning";

// Widened from the 4-literal union (P6-A25) so a custom natural-language-
// derived scenario id can be selected the same way a preset is.
export type DashScenario = string;
export type DashStatus   = "idle" | "loading" | "success" | "error";

// P6-A30 -- carries a trigger request from /dashboard (which no longer owns
// the SSE stream) across to /planning (which does). useFridayRush()'s
// trigger() call lives entirely inside whichever component mounts the hook;
// it isn't route-bound, so it can't survive a client-side navigation itself
// -- /dashboard sets this, navigates to /planning, and /planning's own
// useFridayRush() instance consumes+clears it on mount.
export interface PendingTrigger {
  targetDate?: string;
  scenario: DashScenario;
  restaurantId?: number;
  restaurantName?: string | null;
  customProfile?: ScenarioProfile;
}

interface DashboardCtx {
  selectedScenario: DashScenario;
  setSelectedScenario: (s: DashScenario) => void;
  dashStatus: DashStatus;
  setDashStatus: (s: DashStatus) => void;
  doReset: () => void;
  registerReset: (fn: () => void) => void;
  pendingTrigger: PendingTrigger | null;
  setPendingTrigger: (t: PendingTrigger | null) => void;
}

const Context = createContext<DashboardCtx | null>(null);

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [selectedScenario, setSelectedScenario] = useState<DashScenario>("ed_surge");
  const [dashStatus, setDashStatus] = useState<DashStatus>("idle");
  const [pendingTrigger, setPendingTrigger] = useState<PendingTrigger | null>(null);
  const resetFnRef       = useRef<() => void>(() => {});

  const registerReset = useCallback((fn: () => void) => {
    resetFnRef.current = fn;
  }, []);

  const doReset = useCallback(() => {
    resetFnRef.current();
    setDashStatus("idle");
  }, []);

  return (
    <Context.Provider value={{
      selectedScenario, setSelectedScenario,
      dashStatus, setDashStatus,
      doReset, registerReset,
      pendingTrigger, setPendingTrigger,
    }}>
      {children}
    </Context.Provider>
  );
}

export function useDashboardCtx(): DashboardCtx | null {
  return useContext(Context);
}

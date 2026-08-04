"use client";

import { useEffect, useState } from "react";
import { composeLiveScenario, LiveScenarioComposition } from "@/lib/api";
import { hourCacheKey, readHourCache, writeHourCache } from "@/lib/hourCache";

function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const CACHE_PREFIX = "ck:live-scenario-composition:";

// Backs the "Run for today" fast path -- fetches a scenario profile composed
// fresh from live signals (real time-of-day, weather, holiday, occupancy,
// inventory shortage count, recent runs), instead of "Run for today" silently
// reusing whatever scenario was last manually selected.
// Uses LiveScenarioComposer (not the older, preset-forcing ScenarioRecommender)
// specifically so the label/reasoning shown can never mismatch reality --
// e.g. recommending "Weekday Lunch" during a rainy dinner service because
// that was the closest of only 4 fixed buckets.
// Hour-cached -- live signals genuinely change through the day, but not
// minute to minute, so an hour-old composition is still an honest
// recommendation. Without this, every single page refresh fired a real LLM
// call (LiveScenarioComposer) just to populate a hero caption nobody had
// asked to run yet.
// enabled=false skips the fetch entirely, for any consumer that doesn't
// render the quick-run banner this backs.
export function useScenarioRecommendation(enabled: boolean = true) {
  // Must start identical on server and client -- a lazy initializer reading
  // localStorage here disagrees with the server's render (no localStorage,
  // always empty/not-loaded), which is a real hydration mismatch, not just an
  // avoidable extra render. The cache read moves into the effect below
  // instead, which only ever runs client-side, after hydration.
  const [composition, setComposition] = useState<LiveScenarioComposition | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!enabled) return;

    const cached = readHourCache<LiveScenarioComposition>(hourCacheKey(CACHE_PREFIX));
    if (cached !== null) {
      // Reading an external store (localStorage) into state, not deriving
      // state from a prop -- the pattern this lint rule targets doesn't
      // apply, and this can't move to render since it must stay SSR-safe.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setComposition(cached);
      setLoaded(true);
      return;
    }

    let cancelled = false;
    composeLiveScenario(todayISO())
      .then((comp) => {
        if (cancelled) return;
        setComposition(comp);
        writeHourCache(CACHE_PREFIX, hourCacheKey(CACHE_PREFIX), comp);
      })
      .catch((err) => {
        console.error("useScenarioRecommendation: failed to compose live scenario", err);
        if (!cancelled) setComposition(null);
      })
      .finally(() => { if (!cancelled) setLoaded(true); });

    return () => { cancelled = true; };
  }, [enabled]);

  return { composition, loaded };
}

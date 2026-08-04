// Shared hour-bucketed localStorage cache -- used everywhere a fetch's
// result doesn't need to be fresher than "once per hour" (weather, industry
// trends, FSSAI notices, area occupancy, live-composed scenarios). Without
// this, toggling between Dashboard and /planning re-ran these fetches (and,
// for the scenario composer, a real LLM call) on every single page mount.

export function hourCacheKey(prefix: string): string {
  const d = new Date();
  return `${prefix}${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}-${String(d.getHours()).padStart(2, "0")}`;
}

export function readHourCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null; // storage unavailable/corrupt -- just refetch
  }
}

export function writeHourCache<T>(prefix: string, key: string, value: T): void {
  try {
    // Drop stale hour-buckets from earlier so this never grows unbounded.
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith(prefix) && k !== key) localStorage.removeItem(k);
    }
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full/unavailable -- non-fatal, just means no caching this time */
  }
}

// Lightweight, no-account "previous plans" list for Guest Concierge.
// Concierge sessions are anonymous Redis state (no DB transcript), so this
// only remembers session_id + a derived title + timestamp in this browser's
// localStorage. Resuming a plan rehydrates budget/bookings/orders from the
// server, not the old chat transcript -- there is no message history to
// restore, only the session's current state.

export interface ConciergePlanHistoryEntry {
  session_id: string;
  title: string;
  updated_at: string;
}

const STORAGE_KEY = "concierge_plan_history";
const MAX_ENTRIES = 20;

export function loadPlanHistory(): ConciergePlanHistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function savePlanHistory(entries: ConciergePlanHistoryEntry[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // non-fatal, history just doesn't persist this time
  }
}

export function upsertPlanHistory(sessionId: string, title: string): ConciergePlanHistoryEntry[] {
  const existing = loadPlanHistory().filter((e) => e.session_id !== sessionId);
  const next = [{ session_id: sessionId, title, updated_at: new Date().toISOString() }, ...existing];
  savePlanHistory(next);
  return next;
}

export function removePlanHistory(sessionId: string): ConciergePlanHistoryEntry[] {
  const next = loadPlanHistory().filter((e) => e.session_id !== sessionId);
  savePlanHistory(next);
  return next;
}

const OCCASION_LABEL: Record<string, string> = {
  birthday: "Birthday",
  anniversary: "Anniversary",
  corporate: "Corporate event",
  date: "Date night",
  general: "Get-together",
};

export function derivePlanTitle(occasion: string | null, headcount: number | null, fallback: string): string {
  if (occasion) {
    const label = OCCASION_LABEL[occasion] ?? occasion;
    return headcount ? `${label}, ${headcount} guests` : label;
  }
  return fallback.slice(0, 48) || "New plan";
}

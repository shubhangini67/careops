// lib/api.ts
// Thin client for the CareOps AI FastAPI backend.

import {
  DataHealth,
  FridayRushRequest,
  FridayRushResponse,
  PlanningScenarioOption,
  PlanningRunDetail,
  PlanningRunSummary,
  ScenarioProfile,
} from "@/types/planning";
import { ConciergeHealth, ConciergeSessionState } from "@/types/concierge";
import { getAuthToken } from "@/lib/auth-cookies";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = getAuthToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface LoginRequest { email: string; password: string }
export interface RegisterRequest { email: string; password: string; full_name?: string; org_name: string }
export interface TokenResponse { access_token: string; token_type: string }
export interface UserMe { id: number; email: string; full_name: string | null; org_id: number; org_name: string; org_slug: string; role: string }

export async function apiLogin(body: LoginRequest): Promise<TokenResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Login failed." }));
    throw new Error(detail.detail ?? "Login failed.");
  }
  return res.json() as Promise<TokenResponse>;
}

export async function apiRegister(body: RegisterRequest): Promise<TokenResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Registration failed." }));
    throw new Error(detail.detail ?? "Registration failed.");
  }
  return res.json() as Promise<TokenResponse>;
}

export async function apiGetMe(): Promise<UserMe> {
  const res = await fetch(`${BASE_URL}/api/v1/auth/me`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch user.");
  return res.json() as Promise<UserMe>;
}

// ── Planning ─────────────────────────────────────────────────────────────────

export async function runFridayRush(
  request: FridayRushRequest = {}
): Promise<FridayRushResponse> {
  if (request.scenario && request.scenario !== "ed_surge") {
    return runPlanningScenario(request);
  }

  const res = await fetch(`${BASE_URL}/api/v1/planning/friday-rush`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Planning API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<FridayRushResponse>;
}

export async function runPlanningScenario(
  request: FridayRushRequest = {}
): Promise<FridayRushResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/planning/run`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Planning API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<FridayRushResponse>;
}

// P6-A25 -- converts a free-form description of tonight's service into a
// structured ScenarioProfile, for use as FridayRushRequest.custom_profile
// alongside a non-preset scenario id (e.g. "custom").
export async function deriveScenarioProfile(text: string): Promise<ScenarioProfile> {
  const res = await fetch(`${BASE_URL}/api/v1/planning/scenario-from-text`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ text }),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Scenario profile derivation failed ${res.status}: ${detail}`);
  }

  const data = await res.json() as { profile: ScenarioProfile };
  return data.profile;
}

// Backs the planning modal's mic input -- posts a recorded clip (raw
// MediaRecorder output, e.g. audio/webm) for transcription. Can't reuse
// authHeaders() here: that hardcodes Content-Type: application/json, but a
// multipart body needs the browser to set its own boundary, so only
// Authorization is sent manually.
export async function transcribeAudio(blob: Blob): Promise<string> {
  const token = getAuthToken();
  const formData = new FormData();
  formData.append("file", blob, "recording.webm");

  const res = await fetch(`${BASE_URL}/api/v1/planning/transcribe`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Transcription failed ${res.status}: ${detail}`);
  }

  const data = await res.json() as { text: string };
  return data.text;
}

// P6-MI10 -- ScenarioRecommender already existed server-side (calendar
// context, live Swiggy occupancy, inventory shortage count, weather, recent
// run history -> one LLM call, deterministic fallback) but had no frontend
// caller anywhere -- "Run for today" always just reused whatever scenario
// was last manually selected instead of asking what today actually calls for.
export interface ScenarioRecommendation {
  recommended_scenario: string;
  reason: string;
  confidence: "high" | "medium" | "low";
  signals_used: string[];
}

export async function getScenarioRecommendation(targetDate: string): Promise<ScenarioRecommendation> {
  const res = await fetch(`${BASE_URL}/api/v1/planning/recommend?target_date=${encodeURIComponent(targetDate)}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Scenario recommendation failed ${res.status}: ${detail}`);
  }

  return res.json() as Promise<ScenarioRecommendation>;
}

// Backs the "Run for today" fast path specifically -- unlike getScenarioRecommendation
// above (which forces a fit onto one of 4 fixed presets), this composes a fresh
// profile from live signals (real time-of-day, weather, holiday, occupancy,
// inventory shortage count) so the label can never mismatch reality (e.g.
// "Weekday Lunch" during a rainy dinner service). Shaped like ScenarioProfile,
// safe to pass straight through as FridayRushRequest.custom_profile.
export interface LiveScenarioComposition {
  profile: ScenarioProfile;
  reason: string;
  confidence: "high" | "medium" | "low";
  signals_used: string[];
}

export async function composeLiveScenario(targetDate: string): Promise<LiveScenarioComposition> {
  const res = await fetch(`${BASE_URL}/api/v1/planning/compose-live-scenario?target_date=${encodeURIComponent(targetDate)}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Live scenario composition failed ${res.status}: ${detail}`);
  }

  return res.json() as Promise<LiveScenarioComposition>;
}

export interface ObservabilitySummary {
  period_days: number;
  total_runs: number;
  by_verdict: Record<string, number>;
  by_scenario: Record<string, number>;
  success_rate: number | null;
  avg_critic_score: number | null;
  avg_duration_ms: number | null;
  top_scenario: string | null;
  latest_run_at: string | null;
}

export async function getObservabilitySummary(days = 7): Promise<ObservabilitySummary> {
  const res = await fetch(`${BASE_URL}/api/v1/observability/summary?days=${days}`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Observability API error ${res.status}`);
  return res.json() as Promise<ObservabilitySummary>;
}

export interface WhatIfRequest  { predicted_covers: number; avg_covers: number; scenario: string; service_window: string }
export interface WhatIfResponse {
  scenario: string; service_window: string;
  predicted_covers: number; avg_covers: number; demand_ratio: number;
  cost_pressure_score: number; benefit_score: number; tradeoff_score: number;
  pressure_components: Record<string, number>;
  tradeoff_notes: string[]; recommended_focus: string[];
}

export async function runWhatIf(body: WhatIfRequest): Promise<WhatIfResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/planning/whatif`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`What-if error ${res.status}`);
  return res.json() as Promise<WhatIfResponse>;
}

export type SSENodeStartEvent = { event: "node_start";    node: string; hint?: string };
export type SSENodeEvent      = { event: "node_complete"; node: string; hint?: string; cached?: boolean };
export type SSECompleteEvent  = { event: "complete" } & FridayRushResponse;
export type SSEErrorEvent     = { event: "error"; message: string };
export type SSEEvent = SSENodeStartEvent | SSENodeEvent | SSECompleteEvent | SSEErrorEvent;

export async function* streamPlanningScenario(
  request: FridayRushRequest = {}
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${BASE_URL}/api/v1/planning/stream`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(request),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream failed: ${res.status}`);
  }

  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer    = "";
  let eventType = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        if (!raw) continue;
        try {
          const parsed = JSON.parse(raw);
          yield { event: eventType, ...parsed } as SSEEvent;
        } catch { /* skip malformed line */ }
        eventType = "";
      }
    }
  }
}

export async function getPlanningScenarios(): Promise<PlanningScenarioOption[]> {
  const res = await fetch(`${BASE_URL}/api/v1/planning/scenarios`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Scenario API error ${res.status}: ${detail}`);
  }

  const payload = await res.json() as { scenarios: PlanningScenarioOption[] };
  return payload.scenarios;
}

export interface RunsFilter {
  limit?: number;
  scenario?: string;
  verdict?: string;
  date_from?: string;
  date_to?: string;
}

export async function listPlanningRuns(limitOrFilter: number | RunsFilter = 50): Promise<PlanningRunSummary[]> {
  const params = new URLSearchParams();
  if (typeof limitOrFilter === "number") {
    params.set("limit", String(limitOrFilter));
  } else {
    if (limitOrFilter.limit)     params.set("limit",     String(limitOrFilter.limit));
    if (limitOrFilter.scenario)  params.set("scenario",  limitOrFilter.scenario);
    if (limitOrFilter.verdict)   params.set("verdict",   limitOrFilter.verdict);
    if (limitOrFilter.date_from) params.set("date_from", limitOrFilter.date_from);
    if (limitOrFilter.date_to)   params.set("date_to",   limitOrFilter.date_to);
  }

  const res = await fetch(`${BASE_URL}/api/v1/runs?${params.toString()}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Runs API error ${res.status}: ${detail}`);
  }

  const payload = await res.json() as { runs: PlanningRunSummary[] };
  return payload.runs;
}

export async function getPlanningRun(runId: number): Promise<PlanningRunDetail> {
  const res = await fetch(`${BASE_URL}/api/v1/runs/${runId}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Run detail API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<PlanningRunDetail>;
}

// ── Settings ──────────────────────────────────────────────────────────────────

export interface OrgSettings {
  capacity: number;
  timezone: string;
  cuisine_type: string;
  peak_hours: string;
  critic_threshold: number;
  low_stock_threshold_pct: number;
  overstock_threshold_pct: number;
}

export interface OrgSettingsResponse {
  org_id: number;
  org_name: string;
  settings: OrgSettings;
}

export async function getOrgSettings(): Promise<OrgSettingsResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/settings`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Settings API error ${res.status}`);
  return res.json() as Promise<OrgSettingsResponse>;
}

export async function updateOrgSettings(body: OrgSettings): Promise<OrgSettingsResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/settings`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Update failed." }));
    throw new Error(detail.detail ?? "Update failed.");
  }
  return res.json() as Promise<OrgSettingsResponse>;
}

// ── Restaurant Profiles ───────────────────────────────────────────────────────

export interface RestaurantProfile {
  id: number;
  org_id: number;
  name: string;
  cuisine: string;
  capacity: number;
  peak_hours: string;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface RestaurantProfileCreate {
  name: string;
  cuisine: string;
  capacity: number;
  peak_hours: string;
  timezone: string;
}

export async function listRestaurantProfiles(): Promise<RestaurantProfile[]> {
  const res = await fetch(`${BASE_URL}/api/v1/restaurant-profiles`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Restaurant profiles API error ${res.status}`);
  const payload = await res.json() as { profiles: RestaurantProfile[] };
  return payload.profiles;
}

export async function createRestaurantProfile(body: RestaurantProfileCreate): Promise<RestaurantProfile> {
  const res = await fetch(`${BASE_URL}/api/v1/restaurant-profiles`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Create failed." }));
    throw new Error(detail.detail ?? "Create failed.");
  }
  return res.json() as Promise<RestaurantProfile>;
}

export async function updateRestaurantProfile(id: number, body: Partial<RestaurantProfileCreate>): Promise<RestaurantProfile> {
  const res = await fetch(`${BASE_URL}/api/v1/restaurant-profiles/${id}`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Update failed." }));
    throw new Error(detail.detail ?? "Update failed.");
  }
  return res.json() as Promise<RestaurantProfile>;
}

export async function deleteRestaurantProfile(id: number): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/v1/restaurant-profiles/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}

// ── Connectors ────────────────────────────────────────────────────────────────

export interface ConnectorStatus {
  type: string;
  name: string;
  logo: string;
  connected: boolean;
  last_sync_at: string | null;
  sync_status: string;
  orders_synced: number;
  feedback_synced: number;
  address_configured: boolean;
}

export interface ConnectorsStatusResponse {
  connectors: ConnectorStatus[];
}

export async function getConnectorsStatus(): Promise<ConnectorsStatusResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/connectors/status`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Connectors status error ${res.status}`);
  return res.json() as Promise<ConnectorsStatusResponse>;
}

export interface SyncResult {
  status: string;
  message: string;
  results: Record<string, unknown>;
}

export async function triggerSwiggySync(): Promise<SyncResult> {
  const res = await fetch(`${BASE_URL}/api/v1/connectors/swiggy/sync`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Sync failed." }));
    throw new Error(detail.detail ?? `Sync failed: ${res.status}`);
  }
  return res.json() as Promise<SyncResult>;
}

// ── Action Queue (approval-gated agentic recommendations) ──────────────────

export interface ActionQueueItem {
  id: number;
  category: string;
  tier: "auto" | "approve_required" | "recommendation";
  status: "pending" | "approved" | "executed" | "rejected" | "expired";
  title: string;
  payload: Record<string, unknown>;
  approved_by: number | null;
  executed_at: string | null;
  error: string | null;
  created_at: string | null;
  approval_streak: number;
}

export async function getActionQueue(status?: string): Promise<ActionQueueItem[]> {
  const qs = status ? `?status=${status}` : "";
  const res = await fetch(`${BASE_URL}/api/v1/action-queue${qs}`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Action queue API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<ActionQueueItem[]>;
}

export async function approveAction(id: number, messageOverride?: string): Promise<ActionQueueItem> {
  const res = await fetch(`${BASE_URL}/api/v1/action-queue/${id}/approve`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ message_override: messageOverride ?? null }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Approve failed." }));
    throw new Error(detail.detail ?? `Approve failed: ${res.status}`);
  }
  return res.json() as Promise<ActionQueueItem>;
}

export async function rejectAction(id: number): Promise<ActionQueueItem> {
  const res = await fetch(`${BASE_URL}/api/v1/action-queue/${id}/reject`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Reject failed." }));
    throw new Error(detail.detail ?? `Reject failed: ${res.status}`);
  }
  return res.json() as Promise<ActionQueueItem>;
}

// ── Vendors — real, org-scoped WhatsApp/phone vendor directory ───────────────

export interface VendorSummary {
  id: number;
  name: string;
  category: string | null;
  supplies: string[];
}

export async function getVendors(): Promise<VendorSummary[]> {
  const res = await fetch(`${BASE_URL}/api/v1/vendors`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Vendors API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<VendorSummary[]>;
}

export interface VendorMessageRequest {
  vendor_id: number;
  ingredient: string;
  unit?: string | null;
  quantity_in_stock?: number | null;
  reorder_threshold?: number | null;
  recommended_restock_qty?: number | null;
  reason?: string | null;
}

export async function createVendorMessage(body: VendorMessageRequest): Promise<ActionQueueItem> {
  const res = await fetch(`${BASE_URL}/api/v1/action-queue/vendor-message`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Couldn't draft that message." }));
    throw new Error(detail.detail ?? `Vendor message failed: ${res.status}`);
  }
  return res.json() as Promise<ActionQueueItem>;
}

export async function getDataHealth(): Promise<DataHealth> {
  const res = await fetch(`${BASE_URL}/api/v1/data-health`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Data health API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<DataHealth>;
}

// ── Business performance (revenue, profit, complaints) ─────────────────────────

export interface BusinessDailyPoint {
  date: string;
  revenue: number;
  profit: number;
  orders: number;
}

export interface BusinessDaySnapshot {
  date: string;
  revenue: number;
  profit: number;
  margin_pct: number | null;
  orders: number;
  avg_order_value: number;
  expenses: number;
  net_profit: number | null;
  net_margin_pct: number | null;
}

export interface BusinessDishPerformance {
  name: string;
  category: string;
  revenue: number;
  quantity: number;
  margin_pct: number | null;
}

export interface BusinessChannelSplit {
  dine_in_revenue: number;
  delivery_revenue: number;
  dine_in_orders: number;
  delivery_orders: number;
}

export interface BusinessComplaintCategory {
  category: string;
  count: number;
}

export interface BusinessHourlyDemand {
  hour: number;
  avg_orders: number;
}

// P6-A30 v2 -- forecast reconciliation (predicted vs actual, past runs only)
// and forward-looking risks, both from BusinessAnalyticsService methods every
// other consumer already reads (no new query paths).
export interface BusinessForecastAccuracyPoint {
  date: string;
  scenario: string;
  predicted_orders: number;
  actual_orders: number;
  error_pct: number;
}

export interface BusinessForecastAccuracy {
  points: BusinessForecastAccuracyPoint[];
  accuracy_pct: number | null;
}

export interface BusinessUpcomingRisk {
  kind: "inventory" | "occupancy";
  severity: "critical" | "warning";
  text: string;
}

export interface BusinessPerformanceResponse {
  period_days: number;
  yesterday: BusinessDaySnapshot | null;
  today_so_far: BusinessDaySnapshot | null;
  trend: BusinessDailyPoint[];
  top_dishes: BusinessDishPerformance[];
  bottom_dishes: BusinessDishPerformance[];
  // Full margin-aware dish list (unsliced) -- the Menu Engineering Matrix
  // plots every dish, not just the top/bottom 5 above.
  all_dishes: BusinessDishPerformance[];
  channel_split: BusinessChannelSplit;
  complaints_by_category: BusinessComplaintCategory[];
  peak_hours: BusinessHourlyDemand[];
  total_expenses: number;
  net_profit: number | null;
  net_margin_pct: number | null;
  health_score: number;
  forecast_accuracy: BusinessForecastAccuracy;
  risks: BusinessUpcomingRisk[];
}

// AI-generated executive summary for the Dashboard hero, cached 1h/org/day
// server-side. Independently loading -- never blocks the rest of the page.
export interface BusinessSummaryResponse {
  summary: string | null;
  generated_at: string | null;
}

export async function getBusinessSummary(): Promise<BusinessSummaryResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/business/summary`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Business summary API error ${res.status}`);
  return res.json() as Promise<BusinessSummaryResponse>;
}

export async function getBusinessPerformance(days = 14): Promise<BusinessPerformanceResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/business/performance?days=${days}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Business performance API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<BusinessPerformanceResponse>;
}

// ── Inventory snapshot (live current-state, not a trend -- Analytics'
// Inventory section) ──────────────────────────────────────────────────────

export interface InventoryShortageAlert {
  ingredient: string;
  unit: string;
  quantity_in_stock: number;
  reorder_threshold: number;
  shortfall: number;
  spoilage_risk: boolean;
  severity: string;
  baseline_stock: number;
  projected_drawdown: number;
  scenario_adjustment_reason: string | null;
}

export interface InventoryOverstockAlert {
  ingredient: string;
  unit: string;
  quantity_in_stock: number;
  reorder_threshold: number;
  excess: number;
  spoilage_risk: boolean;
  severity: string;
  baseline_stock: number;
  projected_drawdown: number;
  scenario_adjustment_reason: string | null;
}

export interface InventorySnapshotResponse {
  total_items_checked: number;
  shortage_alerts: InventoryShortageAlert[];
  overstock_alerts: InventoryOverstockAlert[];
}

export async function getInventorySnapshot(): Promise<InventorySnapshotResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/business/inventory-snapshot`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Inventory snapshot API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<InventorySnapshotResponse>;
}

// ── Market pulse (live, independent of any planning run) ──────────────────────

export interface MarketPricingComparison {
  item: string;
  area_avg: number;
  your_price: number | null;
  diff_pct: number | null;
  direction: "above" | "below" | null;
}

export interface MarketPricingImpactItem {
  item: string;
  our_price: number;
  area_avg: number;
  gap_pct: number;
  direction: "above" | "below";
  volume_change_pct: number;
  weekly_revenue_impact_inr: number;
}

// Dish name + price only -- never which restaurant serves it.
export interface MarketDishPrice {
  name: string;
  price: number;
}

export interface MarketCategoryPricing {
  category: string;
  your_avg: number;
  area_avg: number;
  diff_pct: number;
  verdict: "above" | "below" | "in line";
  competitor_dishes_sampled: number;
  cheapest_dish: MarketDishPrice;
  priciest_dish: MarketDishPrice;
}

// Area aggregate only -- no restaurant is individually named.
export interface MarketLandscapeSummary {
  count: number;
  avg_rating: number | null;
  cost_for_two_min: number | null;
  cost_for_two_max: number | null;
  offers_count: number;
}

export interface MarketPositioningInsight {
  your_cost_for_two_estimate: number;
  rank: number;
  total: number;
  cheaper_than_count: number;
  pricier_than_count: number;
}

export interface MarketMenuBreadth {
  your_item_count: number;
  competitor_avg_item_count: number;
  competitors_sampled: number;
}

export interface MarketCuisineCrowding {
  cuisine: string;
  matching_count: number;
  total_checked: number;
}

export interface MarketVegMix {
  veg_count: number;
  total: number;
}

export interface MarketCompetitorPricing {
  restaurants_checked_count: number;
  comparisons: MarketPricingComparison[];
  deals_active_count: number;
  deals_summary: string;
  pricing_impact: MarketPricingImpactItem[];
  category_pricing: MarketCategoryPricing[];
  landscape_summary: MarketLandscapeSummary | null;
  positioning: MarketPositioningInsight | null;
  menu_breadth: MarketMenuBreadth | null;
  cuisine_crowding: MarketCuisineCrowding | null;
  veg_mix: MarketVegMix | null;
  fetched_at: string | null;
}

export interface MarketSlotDeal {
  time: string;
  deal_title: string;
  discount_pct: number;
  is_free: boolean;
}

export interface MarketSlotAvailability {
  time: string;
  avg_availability: number;
  signal: "HIGH" | "MEDIUM" | "LOW";
}

export interface MarketAreaOccupancy {
  signal: "HIGH" | "MEDIUM" | "LOW" | null;
  tonight_busy: boolean | null;
  competitors_checked: number;
  dineout_deals_count: number;
  dineout_deals_summary: string;
  slot_deals_found: MarketSlotDeal[];
  slot_availability_by_time: MarketSlotAvailability[];
  fetched_at: string | null;
}

export interface MarketProcurementItem {
  name: string;
  price: number;
  unit: string;
  in_stock: boolean;
}

// P6-A21 -- Open-Meteo, not Swiggy MCP, so independent of swiggy_connected.
export interface MarketWeather {
  condition: "heavy_rain" | "light_rain" | "very_hot" | "clear";
  avg_precipitation_pct: number | null;
  avg_temp_celsius: number | null;
  delivery_impact: string;
  dinein_impact: string;
  signal: string;
}

export interface MarketUpcomingHoliday {
  date: string;
  name: string;
  days_away: number;
}

// P6-A22 -- curated RSS trade press, not Swiggy MCP, so independent of swiggy_connected.
export interface MarketIndustryTrends {
  digest: string;
  headline_count: number;
  sources_used: number;
  fetched_at: string | null;
}

// P6-A23 -- FSSAI public notices, not Swiggy MCP, so independent of swiggy_connected.
export interface MarketRegulatoryNotice {
  title: string;
  uploaded_on: string;
  url: string;
}

export interface MarketComplianceAlerts {
  notices: MarketRegulatoryNotice[];
  notice_count: number;
  fetched_at: string | null;
}

export interface MarketPulseResponse {
  swiggy_connected: boolean;
  competitor_pricing: MarketCompetitorPricing | null;
  area_occupancy: MarketAreaOccupancy | null;
  procurement: MarketProcurementItem[];
  weather: MarketWeather | null;
  upcoming_holiday: MarketUpcomingHoliday | null;
  industry_trends: MarketIndustryTrends | null;
  compliance_alerts: MarketComplianceAlerts | null;
}

export async function getMarketPulse(forceRefresh = false): Promise<MarketPulseResponse> {
  const url = forceRefresh
    ? `${BASE_URL}/api/v1/market/pulse?force_refresh=true`
    : `${BASE_URL}/api/v1/market/pulse`;
  const res = await fetch(url, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Market pulse API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<MarketPulseResponse>;
}

// ── Live ingredient price lookup (on-demand, not tied to shortages) ───────────

export interface IngredientSearchResult {
  name: string;
  category: string;
  price: number;
  unit: string;
  in_stock: boolean;
}

export interface IngredientSearchResponse {
  swiggy_connected: boolean;
  query: string;
  results: IngredientSearchResult[];
}

export async function searchIngredient(query: string): Promise<IngredientSearchResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/market/ingredient-search?query=${encodeURIComponent(query)}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Ingredient search API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<IngredientSearchResponse>;
}

// ── Market trends (P6-MI11) — pricing/occupancy history across past runs ─────

export interface MarketPricePoint {
  date: string;
  area_avg: number;
}

export interface MarketOccupancyPoint {
  date: string;
  signal: "HIGH" | "MEDIUM" | "LOW";
}

export interface MarketTrendsResponse {
  price_trends: Record<string, MarketPricePoint[]>;
  occupancy_trend: MarketOccupancyPoint[];
  days_returned: number;
  note: string | null;
}

export async function getMarketTrends(days = 7): Promise<MarketTrendsResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/market/trends?days=${days}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Market trends API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<MarketTrendsResponse>;
}

// ── Chat conversation history (P6-A4) ─────────────────────────────────────────

export interface ChatSessionSummary {
  id: number;
  title: string | null;
  message_count: number;
  updated_at: string;
}

export interface ChatMessageDTO {
  role: "user" | "assistant";
  content: string;
}

export interface ChatSessionDetail {
  id: number;
  title: string | null;
  messages: ChatMessageDTO[];
}

export async function getChatSessions(): Promise<ChatSessionSummary[]> {
  const res = await fetch(`${BASE_URL}/api/v1/chat/sessions`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Chat sessions API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<ChatSessionSummary[]>;
}

export async function getChatSession(sessionId: number): Promise<ChatSessionDetail> {
  const res = await fetch(`${BASE_URL}/api/v1/chat/sessions/${sessionId}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Chat session API error ${res.status}: ${detail}`);
  }

  return res.json() as Promise<ChatSessionDetail>;
}

export async function deleteChatSession(sessionId: number): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/v1/chat/sessions/${sessionId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Delete chat session API error ${res.status}: ${detail}`);
  }
}

// ── Guest Concierge (Phase 6A-34) — no auth, consumer-facing ────────────────
// Deliberately does not use authHeaders(): concierge routes take no auth.

export async function getConciergeSession(sessionId: string): Promise<ConciergeSessionState> {
  const res = await fetch(`${BASE_URL}/api/v1/concierge/session/${sessionId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Concierge session API error ${res.status}`);
  return res.json() as Promise<ConciergeSessionState>;
}

export async function deleteConciergeSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/v1/concierge/session/${sessionId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) throw new Error(`Delete concierge session API error ${res.status}`);
}

export async function getConciergeHealth(): Promise<ConciergeHealth> {
  const res = await fetch(`${BASE_URL}/api/v1/concierge/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Concierge health API error ${res.status}`);
  return res.json() as Promise<ConciergeHealth>;
}

export async function transcribeConciergeAudio(blob: Blob): Promise<string> {
  const formData = new FormData();
  formData.append("file", blob, "recording.webm");

  const res = await fetch(`${BASE_URL}/api/v1/concierge/transcribe`, { method: "POST", body: formData });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Transcription failed ${res.status}: ${detail}`);
  }
  const data = (await res.json()) as { text: string };
  return data.text;
}

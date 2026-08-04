// types/planning.ts
// Mirrors apps/api/app/api/schemas/planning.py

export interface ForecastData {
  predicted_orders: number;
  predicted_orders_lower?: number;
  predicted_orders_upper?: number;
  predicted_peak_orders?: number;
  method: "prophet" | "baseline";
  confidence: "high" | "medium" | "low";
  target_date?: string;
  avg_friday_orders?: number;
  avg_peak_orders?: number;
  history?: Array<{
    date: string;
    total_orders: number;
    peak_orders_6pm_to_11pm: number;
  }>;
  hourly_projection?: Array<{
    hour: string;
    covers: number;
  }>;
  top_items?: Array<{
    item: string;
    category: string;
    total_ordered: number;
  }>;
  // P6-A21 -- weather/holiday demand-multiplier fields, never typed on the
  // frontend before even though the backend has returned them since P6-A21.
  predicted_orders_pre_adjustment?: number;
  adjustment_multiplier?: number;
  adjustment_reasons?: string[];
}

export interface ReservationData {
  date: string;
  total_reservations: number;
  total_guests: number;
  capacity: number;
  occupancy_pct: number;
  overbooking_risk: boolean;
  busiest_hour?: number;
  peak_hours?: Record<string, number>;
  waitlist_count: number;
}

export interface ComplaintData {
  data?: {
    unique_complaints?: string[];
    unique_positives?: string[];
    total_feedback?: number;
    sentiment_breakdown?: {
      negative: number;
      positive: number;
      neutral: number;
      negative_pct: number;
    };
  };
  issues?: Array<{
    issue: string;
    frequency: string;
    recommendation: string;
    priority: "high" | "medium" | "low";
  }>;
  overall_summary?: string;
  action_items?: string[];
  unique_complaints?: string[];
  unique_positives?: string[];
  total_feedback?: number;
  sentiment_breakdown?: {
    negative: number;
    positive: number;
    neutral: number;
    negative_pct: number;
  };
}

export interface MenuData {
  data?: {
    top_items?: Array<{
      item: string;
      category: string;
      total_ordered: number;
    }>;
    forecast_snapshot?: {
      predicted_orders?: number;
      predicted_peak_orders?: number;
      avg_friday_orders?: number;
      target_date?: string;
    };
    complaint_themes?: string[];
    shortage_ingredients?: string[];
    overstock_ingredients?: string[];
    note?: string;
  };
  top_items?: Array<{
    item: string;
    category: string;
    total_ordered: number;
  }>;
  highlight_items?: string[];
  deprioritize_items?: string[];
  promo_candidates?: string[];
  inventory_blockers?: string[];
  complaint_watchouts?: string[];
  operational_notes?: string[];
  reasoning?: string;
  priority?: string;
  risks?: string[];
  note?: string;
}

export interface InventoryData {
  data?: {
    total_items_checked?: number;
    shortage_alerts?: unknown[];
    overstock_alerts?: unknown[];
    high_demand_week?: boolean;
    demand_ratio?: number;
  };
  restock_actions?: string[];
  waste_reduction_actions?: string[];
  priority?: string;
  reasoning?: string;
  risks?: string[];
  note?: string;
  shortage_alerts?: unknown[];
  overstock_alerts?: unknown[];
}

export interface AgentRecommendations {
  forecast: Record<string, unknown> | null;
  reservation: ReservationData | null;
  complaint: ComplaintData | null;
  menu: MenuData | null;
  inventory: InventoryData | null;
}

export interface CriticResult {
  verdict:         "approved" | "rejected" | "revision" | "unknown";
  score:           number;
  notes:           string;
  cost_analysis?: {
    cost_pressure_score: number;
    benefit_score: number;
    tradeoff_score: number;
    pressure_components?: Record<string, number>;
    benefit_components?: Record<string, number>;
    tradeoff_notes?: string[];
    recommended_focus?: string[];
    signals?: Record<string, unknown>;
  } | null;
  dimension_scores?: Record<string, number> | null;
  revision_reasons?: string[];
  actionable_feedback?: string[];
  decision_log_id: number | null;
  sanity_checks?: {
    passed?: boolean;
    summary?: string;
    issues?: Array<{
      code: string;
      severity: string;
      message: string;
    }>;
  } | null;
  // Cross-agent contradictions (EvaluationSanityChecker._diff_assumptions) --
  // present on final_assembler's critic dict but was missing from this type.
  stale_assumptions?: Array<{ node: string; conflict: string }>;
}

export interface RagContext {
  complaints?: unknown[];
  sops?:       unknown[];
  [key: string]: unknown;
}

export interface SwiggyCompetitorPricing {
  area_avg_price:    number | null;
  cheapest_price:    number | null;
  most_expensive:    number | null;
  restaurants_found: number;
  dish_query:        string;
  fetched_at:        string;
}

export interface SwiggyPricingAlert {
  item:         string;
  your_price:   number;
  area_avg:     number;
  diff_pct:     number;
  direction:    "above" | "below";
}

export interface SwiggyOccupancyContext {
  signal:       "HIGH" | "MEDIUM" | "LOW";
  tonight_busy: boolean;
  restaurants_found: number;
  fetched_at:   string;
}

// Mirrors ProcurementEnricher.enrich()'s actual return shape (camelCase
// item fields, straight from the Swiggy Instamart response) -- NOT the
// snake_case this used to declare, which never matched the real payload.
export interface SwiggyProcurementOption {
  ingredient: string;
  price:      number;
  unit:       string;
  inStock:    boolean;
  spinId:     string;
}

// The backend wraps the array in a dict (app/api/schemas/planning.py:
// swiggy_procurement_options: Optional[Dict[str, Any]]), not a bare array --
// FridayRushResponse.swiggy_procurement_options below used to type it as a
// plain SwiggyProcurementOption[], which crashed the first real .find()
// call against it (options.find is not a function) since at runtime it's
// this wrapper object.
export interface SwiggyProcurementOutput {
  procurement_options: SwiggyProcurementOption[];
  prompt_text?: string;
  fetched_at?: string;
}

export interface MarketIntelOutput {
  competitor_pricing: SwiggyCompetitorPricing | null;
  area_occupancy:     SwiggyOccupancyContext | null;
  pricing_alerts:     SwiggyPricingAlert[];
  tonight_busy:       boolean | null;
  fetched_at:         string | null;
  // Condensed prose merging weather/trends/compliance/Swiggy signals
  // (MarketIntelService._build_live_signals_text, P6-A24) -- not on every
  // older stored run, hence optional.
  live_signals_text?: string;
}

// P6-A30 -- per-node/per-LLM-call observability data. This has always been
// captured in graph.py's run metadata (node_traces/llm_usage) but was never
// typed or surfaced on the frontend before -- the only fields read anywhere
// were a handful of run-level aggregates via untyped Record<string, unknown>
// casts (see PlanningRunMetadata below for those).
export interface LlmUsageRecord {
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  node: string | null;
}

export interface NodeTrace {
  node: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  // Absent (not just empty) on some real runs -- nodes that error before
  // recording usage, or older stored runs predating this field. Consumers
  // must default it, not assume it's always an array.
  llm_usage?: LlmUsageRecord[];
  node_cost_usd: number;
  // Only present on the error path (graph.py's exception branch) -- absence
  // means the node completed normally, not that it's guaranteed non-null.
  error?: string;
}

// Shape of FridayRushResponse.meta / PlanningRunDetail.metadata. Kept as an
// index signature too since not every historical run has every field (older
// runs predate P6-A27's session_id, etc.) and the backend may add fields
// here without a frontend release.
export interface PlanningRunMetadata {
  run_id?: string;
  session_id?: string;
  node_traces?: NodeTrace[];
  llm_usage?: LlmUsageRecord[];
  total_duration_ms?: number;
  total_tokens?: number;
  total_cost_usd?: number;
  llm_model?: string;
  llm_provider?: string;
  llm_fallback_used?: boolean;
  llm_fallback_provider?: string;
  planning_run_id?: number;
  cache_hit?: boolean;
  [key: string]: unknown;
}

export interface FridayRushResponse {
  scenario:        string;
  target_date:     string | null;
  status:          "ready" | "needs_review" | "blocked" | "unknown";
  generated_at:    string;
  recommendations: AgentRecommendations;
  rag_context:     RagContext | null;
  critic:          CriticResult;
  meta?:           Record<string, unknown>;
  // Swiggy enricher outputs (P6-S11/S12)
  market_intel?:              MarketIntelOutput | null;
  swiggy_competitor_context?: Record<string, unknown> | null;
  swiggy_occupancy_context?:  SwiggyOccupancyContext | null;
  swiggy_procurement_options?: SwiggyProcurementOutput | null;
  dineout_manager?:           Record<string, unknown> | null;
  // Natural-language "situation + tailored key takeaways" briefing (hero
  // content on /planning's results page). Absent on older stored runs or
  // when the LLM call failed open -- frontend falls back to a deterministic
  // rendering in that case.
  situation_summary?:         string | null;
}

// P6-A25 -- ad-hoc scenario profile derived from natural language, carried
// alongside a non-preset `scenario` id. Mirrors the backend's
// ScenarioProfilePayload (apps/api/app/api/schemas/planning.py).
export interface ScenarioProfile {
  id: string;
  label: string;
  description?: string;
  service_window: string;
  operational_focus: string;
  cuisine?: string | null;
}

// Shared callback shape for every "trigger a plan" entry point (Dashboard's
// PlanShiftModal, /planning's hero + accordion) -- one definition instead of
// four near-identical inline copies. scenarioOverride exists specifically
// for ScenarioRecommender-driven "run for today" fast paths: DashboardContext's
// selectedScenario only reflects a setSelectedScenario() call after the next
// render, so a handler can't call setSelectedScenario() then immediately
// trigger() in the same synchronous click handler and expect the new value --
// it must pass the recommended scenario id through explicitly instead.
export type PlanTriggerHandler = (
  date?: string,
  restaurantName?: string,
  restaurantId?: number,
  customProfile?: ScenarioProfile,
  scenarioOverride?: string,
) => void;

export interface FridayRushRequest {
  target_date?: string | null;
  simulation_mode?: boolean;
  // Widened from the 4-literal union (P6-A25) -- a custom id (e.g. "custom")
  // is valid when custom_profile is also supplied. The 4 presets still work
  // unchanged when scenario is one of them and custom_profile is omitted.
  scenario?: string;
  restaurant_id?: number;
  custom_profile?: ScenarioProfile | null;
}

export interface PlanningScenarioOption {
  // Widened from the 4-literal union (P6-A25) so a synthesized "custom" tile
  // (built from ScenarioProfile) can be passed through the same picker props
  // as the 4 presets.
  id: string;
  label: string;
  description: string;
  default_weekday: number;
  service_window: string;
  operational_focus: string;
}

// Run history entry -- stored in memory during the session
export interface RunHistoryEntry {
  id:          string | number;
  targetDate:  string;
  runAt:       string;
  status:      FridayRushResponse["status"];
  verdict:     CriticResult["verdict"];
  score:       number | null;
  // Threaded through from PlanningRunSummary.scenario (P6-A34) -- lets the
  // Planning idle-state's recent-runs table show scenario/shift-shape
  // columns without a second fetch per row.
  scenario:    string;
  // Real resolved title for a custom run (scenario itself is just "custom").
  scenarioLabel?: string | null;
  data?:       FridayRushResponse;
}

export interface PlanningRunSummary {
  id: number;
  scenario: string;
  // The real resolved scenario title (e.g. "Anniversary Dinner") -- for a
  // custom (natural-language-derived) run, `scenario` itself is just the
  // literal id "custom", never the actual name; null only for runs recorded
  // before this field existed.
  scenario_label: string | null;
  target_date: string | null;
  status: FridayRushResponse["status"];
  critic_verdict: CriticResult["verdict"] | null;
  critic_score: number | null;
  decision_log_id: number | null;
  generated_at: string | null;
  created_at: string | null;
  // AI infrastructure observability -- backs the /data Observability tab's
  // cross-run cost/token/duration breakdown, read straight from each run's
  // stored metadata (no per-row detail fetch needed).
  total_cost_usd: number | null;
  total_tokens: number | null;
  total_duration_ms: number | null;
  llm_model: string | null;
  llm_provider: string | null;
  cache_hit: boolean | null;
  llm_call_count: number | null;
  replan_count: number | null;
  risk_tags: string[];
}

export interface PlanningRunDetail extends PlanningRunSummary {
  final_response: FridayRushResponse;
  recommendations: AgentRecommendations | null;
  rag_context: RagContext | null;
  critic: CriticResult | null;
  metadata: Record<string, unknown> | null;
}

export interface DataHealth {
  orders: { count: number; date_range: Array<string | null> };
  reservations: { count: number; date_range: Array<string | null> };
  feedback: {
    count: number;
    date_range: Array<string | null>;
    negative: number;
    positive: number;
    neutral: number;
    negative_pct: number;
  };
  inventory: {
    items: number;
    shortage_alerts: number;
    critical_shortages: number;
    overstock_alerts: number;
  };
  menu: { items: number };
  scenario_coverage: Array<{
    scenario: "friday_rush" | "weekday_lunch" | "holiday_spike" | "low_stock_weekend";
    label: string;
    date: string;
    reservations: number;
    guests: number;
    waitlist: number;
    occupancy_pct: number;
  }>;
  status: "ok";
}

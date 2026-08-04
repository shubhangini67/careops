# CareOps AI API Reference

Reflects Phase 6A in progress.

Base URL: `http://localhost:8000`  
Base prefix: `/api/v1`  
Interactive docs: `http://localhost:8000/docs` (Swagger UI)

All request and response bodies use `application/json` unless noted. Streaming endpoints use `text/event-stream`.

---

## Authentication

### `POST /api/v1/auth/register`

Register a new user and organisation in one step.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | Yes | User email |
| `password` | string | Yes | Min 8 characters |
| `full_name` | string | No | Display name |
| `org_name` | string | Yes | Restaurant / org name |

**Response `201`**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "chef@example.com",
    "full_name": "Mario Rossi",
    "org_id": 1,
    "org_name": "Casa Mia",
    "role": "owner"
  }
}
```

---

### `POST /api/v1/auth/login`

Authenticate an existing user and receive a JWT.

**Request body**

| Field | Type | Required |
|-------|------|----------|
| `email` | string | Yes |
| `password` | string | Yes |

**Response `200`**: same shape as `/register`.

---

### `GET /api/v1/auth/me`

Returns the authenticated user's profile.

**Auth:** JWT required.

**Response `200`**

```json
{
  "id": 1,
  "email": "chef@example.com",
  "full_name": "Mario Rossi",
  "org_id": 1,
  "org_name": "Casa Mia",
  "role": "owner"
}
```

---

## Health

### `GET /api/v1/health`

Application liveness.

**Response `200`**

```json
{ "status": "ok", "service": "CareOps AI API", "environment": "local" }
```

---

### `GET /api/v1/health/dependencies`

Live connectivity check for PostgreSQL, Qdrant, and Redis.

**Response `200`**

```json
{
  "service": "CareOps AI API",
  "overall_ok": true,
  "dependencies": [
    { "name": "postgres", "ok": true, "detail": null },
    { "name": "qdrant",   "ok": true, "detail": null },
    { "name": "redis",    "ok": true, "detail": null }
  ]
}
```

`overall_ok` is `false` if any dependency fails. `detail` contains the error string when `ok` is `false`.

---

### `GET /api/v1/health/circuits`

Real-time circuit breaker state for all three Swiggy MCP endpoints.

**Auth:** None (public endpoint).

**Response `200`**

```json
{
  "circuits": [
    { "state": "closed", "recent_failures": 0, "resets_in_seconds": null },
    { "state": "closed", "recent_failures": 0, "resets_in_seconds": null },
    { "state": "closed", "recent_failures": 0, "resets_in_seconds": null }
  ]
}
```

Endpoints are ordered: `food`, `im` (Instamart), `dineout`.

`state` is `"open"` when the circuit has tripped (5 or more failures within a 5-minute window). `resets_in_seconds` shows time until auto-reset, currently a 10-minute open window. A closed circuit returns `resets_in_seconds: null`.

---

## Planning

### `GET /api/v1/planning/scenarios`

Returns all available scenario presets.

**Response `200`**

```json
{
  "scenarios": [
    {
      "id": "friday_rush",
      "label": "Friday Rush",
      "description": "High-demand dinner service with reservation pressure, inventory risk, and fast-turn execution needs.",
      "default_weekday": 4,
      "service_window": "18:00-22:00",
      "operational_focus": "Peak dinner demand, table turns, rush execution, and same-day stock protection."
    }
  ]
}
```

---

### `POST /api/v1/planning/run`

Executes the full LangGraph planning pipeline (see `docs/AGENTS.md` for the current node topology). Returns the **full response as a standard JSON object** once the pipeline completes. No streaming: use `/planning/stream` if you need the live pipeline diagram.

**Auth:** JWT required.

**Request body**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `scenario` | string | Yes |  | One of `friday_rush`, `weekday_lunch`, `holiday_spike`, `low_stock_weekend` |
| `target_date` | string | No | Next matching weekday | ISO date string, e.g. `"2026-06-12"` |
| `restaurant_id` | integer | No | `null` | Override org defaults with a named profile |
| `simulation_mode` | boolean | No | `false` | Use deterministic mock data |
| `force_critic_decision` | string | No | `null` | Override critic verdict for testing |
| `debug` | boolean | No | `false` | Include LangGraph execution trace in `meta` |

**Response `200`**

```json
{
  "scenario": "friday_rush",
  "target_date": "2026-06-12",
  "status": "ready",
  "cache_hit": false,
  "generated_at": "2026-06-12T16:00:00Z",
  "recommendations": {
    "forecast":     { "predicted_covers": 89, "peak_hour": "21:00", "confidence": "high", ... },
    "reservation":  { "reservations": 15, "occupancy_pct": 81.3, "peak_hour": "19:00", ... },
    "complaint":    { "total": 48, "negative_pct": 35, "top_issues": [...], ... },
    "menu":         { "top_items": [...], "items_to_avoid": [...], "strategy": "...", ... },
    "inventory":    { "shortage_alerts": 10, "critical_items": [...], ... }
  },
  "rag_context": {
    "complaints": [ ... ],
    "sops":       [ ... ]
  },
  "critic": {
    "verdict": "approved",
    "score": 0.92,
    "notes": "Plan addresses critical shortages and prioritises safe menu execution.",
    "dimension_scores": {
      "safety": 1.0, "feasibility": 0.70, "evidence": 0.80,
      "actionability": 0.90, "clarity": 0.90
    },
    "revision_reasons": [],
    "actionable_feedback": [],
    "cost_analysis": {
      "cost_pressure_score": 0.82,
      "benefit_score": 0.64,
      "tradeoff_score": 0.27,
      "recommended_focus": ["Favour low-complexity prep changes over forced execution changes."]
    },
    "stale_assumptions": [
      {
        "node": "menu_intelligence",
        "assumption_key": "assumed_covers_within_capacity",
        "assumed_value": true,
        "actual_value": 99.1,
        "conflict": "menu_intelligence assumed covers within capacity, but reservation node shows 99.1% occupancy: menu recommendations must account for kitchen throughput limits under near-full house"
      },
      {
        "node": "complaint_intelligence",
        "assumption_key": "assumed_high_complaint_volume",
        "assumed_value": false,
        "actual_value": 26.3,
        "conflict": "complaint_intelligence classified complaint volume as low, but negative feedback is 26.3%: borderline elevated complaint risk that may compound under high occupancy"
      }
    ]
  },
  "meta": {
    "planning_run_id": 42,
    "scenario": "friday_rush",
    "timestamp": "2026-06-12T16:00:00+00:00",
    "llm_usage": { "total_tokens": 6386, "total_cost_usd": 0.00405 },
    "node_traces": [ ... ]
  }
}
```

**Key response fields**

| Field | Description |
|-------|-------------|
| `status` | `ready`: plan approved or passable; `needs_review`: critic flagged issues; `blocked`: critical failure |
| `cache_hit` | `true` if the result was returned from Redis cache; `false` if the pipeline ran |
| `critic.verdict` | `approved`, `revision`, or `rejected` |
| `critic.score` | 0.0 – 1.0 composite quality score |
| `critic.stale_assumptions` | Cross-agent assumption conflicts detected by `EvaluationSanityChecker`. Empty array when no conflicts exist. Each item has `node`, `assumption_key`, `assumed_value`, `actual_value`, and `conflict`. |
| `meta.planning_run_id` | ID of the persisted `planning_runs` row |
| `meta.llm_usage.total_cost_usd` | Total LLM spend for this run |

---

### `POST /api/v1/planning/stream`  *(SSE)*

Identical request body to `/planning/run`. Returns a `text/event-stream` response so the frontend can power the live pipeline diagram during the run.

**Auth:** JWT required.

**How it works**

Two event types power the frontend pipeline diagram:

- `node_start` fires when a node begins execution; includes an optional `hint` string with a human-readable description of what the node is doing
- `node_complete` fires when the node finishes; may also include a completion `hint` (e.g. how many items were retrieved)
- The loading screen uses both event types to drive a 4-state node UI: idle, then running, then done

When the full pipeline finishes, a single `complete` event delivers the entire plan payload. The dashboard renders all sections at once from this final event.

Only plans with `critic.verdict == "approved"` are written to semantic cache. On a cache hit: all node events are emitted instantly with `{"node": "...", "cached": true}`, followed by the `complete` event.

**SSE event format**

```
event: node_start
data: {"node": "qdrant_enrichment", "hint": "Reading past plans from memory..."}

event: node_complete
data: {"node": "qdrant_enrichment", "hint": "Memory loaded: 2 past plans"}

event: node_start
data: {"node": "forecast", "hint": "Analysing demand signal..."}

event: node_complete
data: {"node": "forecast"}

event: node_start
data: {"node": "reservation"}

event: node_complete
data: {"node": "reservation"}

event: node_start
data: {"node": "complaint"}

event: node_complete
data: {"node": "complaint"}

event: node_start
data: {"node": "menu"}

event: node_complete
data: {"node": "menu"}

event: node_start
data: {"node": "inventory"}

event: node_complete
data: {"node": "inventory"}

event: node_complete
data: {"node": "aggregator"}

event: node_complete
data: {"node": "critic"}

event: complete
data: { ... full response payload: same shape as /planning/run ... }
```

Note: `ops_manager`, `replan_orchestrator`, and `final_assembler` do not emit SSE events: they are infrastructure or assembly nodes.

**Error event**

```
event: error
data: {"message": "Stream error: ..."}
```

---

### `POST /api/v1/planning/whatif`

What-if demand simulator. Recalculates cost/benefit scoring for a user-supplied cover count without running the LangGraph pipeline: no LLM calls, instant response.

**Auth:** JWT required.

**Request body**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `predicted_covers` | integer (1–1000) | Yes |  | Hypothetical cover count to evaluate |
| `avg_covers` | float | Yes |  | Historical baseline average covers from the existing run |
| `scenario` | string | No | `friday_rush` | Scenario label for context |
| `service_window` | string | No | `18:00-22:00` | Service window label for context |

**Response `200`**

```json
{
  "scenario": "friday_rush",
  "service_window": "18:00-22:00",
  "predicted_covers": 135,
  "avg_covers": 89.0,
  "demand_ratio": 1.52,
  "cost_pressure_score": 0.78,
  "benefit_score": 0.65,
  "tradeoff_score": 0.83,
  "pressure_components": { "demand": 0.8, "occupancy": 0.0, "inventory": 0.0 },
  "tradeoff_notes": ["High demand ratio suggests elevated operational pressure."],
  "recommended_focus": ["Prioritise staffing and prep capacity for the higher-than-baseline cover count."]
}
```

---

### `GET /api/v1/planning/recommend`

Suggests which scenario preset to run next, before the owner manually picks one.
Combines recent run history, live Swiggy market signals (if connected), calendar context
(weekend/holiday), and current inventory shortage pressure into a single LLM call. Falls back to a
deterministic rule-based pick if the LLM call fails: this endpoint never errors out.

**Auth:** JWT required.

**Query parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target_date` | string | Yes | ISO date string, e.g. `"2026-07-05"` |

**Response `200`**

```json
{
  "recommended_scenario": "holiday_spike",
  "reason": "Tomorrow is Diwali and area Dineout occupancy is HIGH. Expect 40-60% demand surge.",
  "confidence": "high",
  "signals_used": ["recent_approved_runs: 3", "holiday_detected", "occupancy_HIGH"]
}
```

| Field | Description |
|-------|-------------|
| `recommended_scenario` | One of `friday_rush`, `weekday_lunch`, `holiday_spike`, `low_stock_weekend` |
| `confidence` | `high`, `medium`, or `low`: `low` when the deterministic fallback was used |
| `signals_used` | Which signals informed the recommendation (for UI transparency) |

---

### `POST /api/v1/planning/scenario-from-text`

Turns a free-form description of tonight's service into a structured scenario profile, for a shift that does not fit any of the four fixed presets. Never raises; falls back to a deterministic profile so the required fields are always populated.

**Auth:** JWT required.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | Free-form description, for example "we are hosting a birthday event tonight, expecting a large turnout" |

**Response `200`**

```json
{
  "profile": {
    "id": "custom",
    "label": "Birthday Event Night",
    "description": "Large private event with elevated demand",
    "service_window": "18:00-23:00",
    "operational_focus": "Prioritize table turns and event-menu execution.",
    "cuisine": null
  }
}
```

The returned `profile` is passed back as `custom_profile` alongside a non-preset `scenario` value (for example `"custom"`) on the next `POST /planning/run` or `/planning/stream` call.

---

### `GET /api/v1/planning/compose-live-scenario`

Backs the "run for today" instant path. Unlike `/planning/recommend`, which always picks one of the four fixed presets, this composes a fresh, non-preset profile from what is actually true right now: real day of week, current time, weather, holiday, inventory shortage count, and area occupancy. This avoids the failure mode where the closest-fitting preset label does not match reality, for example labeling a rainy weekday evening as a weekend scenario.

**Auth:** JWT required.

**Query parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target_date` | string | Yes | ISO date string, e.g. `"2026-07-15"` |

**Response `200`**

```json
{
  "profile": {
    "id": "live-composed",
    "label": "Rainy Wednesday Dinner",
    "description": "Reduced walk-in traffic expected due to heavy rain",
    "service_window": "18:00-22:00",
    "operational_focus": "Shift toward delivery, reduce outdoor seating dependence.",
    "cuisine": null
  },
  "reason": "Heavy rain forecast during dinner service and low area Dineout occupancy suggest reduced walk-in demand tonight.",
  "confidence": "medium",
  "signals_used": ["current_time:19:30", "weather_heavy_rain", "occupancy_LOW"]
}
```

The returned `profile` is shaped identically to `/planning/scenario-from-text`'s and is safe to pass through as `custom_profile`.

---

### `POST /api/v1/planning/friday-rush`

Legacy scenario-specific route, kept for backward compatibility. New integrations should use `/planning/run` or `/planning/stream` with an explicit `scenario` field instead.

---

### `POST /api/v1/planning/transcribe`

Transcribes a short recorded voice clip to text, backing the microphone input on the Planning modal's free-text intake. Returns raw text only; the frontend shows it as an editable transcript before any plan is triggered, never auto-submitted.

**Auth:** JWT required.

**Request:** `multipart/form-data` with a `file` field (e.g. `audio/webm` from the browser's `MediaRecorder`).

**Response `200`**

```json
{ "text": "we're hosting a birthday event tonight, expecting a large turnout" }
```

**Error `400`**: empty audio upload. **Error `502`**: transcription failed upstream.

---

## Runs

### `GET /api/v1/runs`

Lists persisted planning runs in reverse-chronological order, org-scoped.

**Auth:** JWT required.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer (1–200) | `50` | Max runs to return |
| `scenario` | string |  | Filter by scenario id |
| `status` | string |  | Filter by status |
| `verdict` | string |  | Filter by critic verdict |
| `date_from` | string |  | ISO date: return runs on or after this date |
| `date_to` | string |  | ISO date: return runs on or before this date |

**Response `200`**

```json
{
  "runs": [
    {
      "id": 42,
      "scenario": "friday_rush",
      "target_date": "2026-06-12",
      "status": "ready",
      "critic_verdict": "approved",
      "critic_score": 0.92,
      "generated_at": "2026-06-12T16:00:00",
      "cache_hit": false
    }
  ]
}
```

---

### `GET /api/v1/runs/{run_id}`

Full detail for one persisted planning run.

**Auth:** JWT required.

**Response `200`**: includes full `recommendations`, `rag_context`, `critic`, and `meta` blocks (same shape as planning run response).

**Error `404`**: run not found or belongs to a different org.

---

### `GET /api/v1/runs/{run_id}/export`

Downloads a ReportLab-generated PDF chef brief for the run.

**Auth:** JWT required.  
**Response:** `application/pdf` file download.

The PDF includes: run summary, scenario, target date, critic verdict and score, dimension scores, agent recommendations, action items.

---

### `GET /api/v1/runs/{run_id}/export/excel`

Downloads a multi-sheet Excel workbook for the run.

**Auth:** JWT required.  
**Response:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` file download.

Sheets:
- **Summary**: scenario, date, verdict, critic score
- **Inventory & Staffing**: shortage alerts, overstock alerts, restock actions (chef view)
- **Cost Breakdown**: LLM usage, critic dimension scores, cost-aware analysis (owner view)

---

## Market

Live Swiggy market intelligence, independent of any planning run. Each enricher caches its own
result in Redis for 30 minutes (keyed by `org_id` + date), so repeated calls (e.g. every dashboard
load) don't re-hit the Swiggy MCP server each time.

### `GET /api/v1/market/pulse`

Fetches current competitor pricing, area occupancy, and Instamart procurement directly via the
planning-pipeline enrichers, without requiring a plan to be run first.

**Auth:** JWT required.

**Response `200`**

```json
{
  "swiggy_connected": true,
  "competitor_pricing": {
    "restaurants_checked": ["Biryani House", "Paradise", "Punjab Grill"],
    "comparisons": [
      { "item": "Butter Chicken", "your_price": 320.0, "area_avg": 265.0, "diff_pct": 20.8, "direction": "above" }
    ],
    "competitor_deals": [
      { "restaurant": "Biryani House", "deal_title": "20% off above Rs.300", "discount": 20, "code": "SAVE20" }
    ],
    "pricing_impact": [
      {
        "item": "Butter Chicken", "our_price": 320.0, "area_avg": 265.0,
        "gap_pct": 20.8, "direction": "above",
        "volume_change_pct": -16.6, "weekly_revenue_impact_inr": -8715.0
      }
    ],
    "fetched_at": "2026-07-05"
  },
  "area_occupancy": { "signal": "HIGH", "tonight_busy": true, "competitors_checked": 3, "fetched_at": "2026-07-05" },
  "procurement": [ { "name": "Tomatoes", "price": 45.0, "unit": "1kg", "in_stock": true } ]
}
```

`competitor_deals` (from `fetch_food_coupons`) and `pricing_impact` (a quantified
demand-elasticity revenue model) were added in the market intelligence expansion. Both are `[]`
when Swiggy is unavailable or no data qualifies: never `null`, safe to render unconditionally.

---

### `GET /api/v1/market/trends`

Per-dish price history and area occupancy signal history across past planning runs: no
new Swiggy calls, reads `market_intel` already stored in each run's persisted `final_response`.

**Auth:** JWT required.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer (1–90) | `7` | Number of data points to return |

**Response `200`**

```json
{
  "price_trends": {
    "butter chicken": [
      { "date": "2026-06-29", "area_avg": 265.0 },
      { "date": "2026-07-02", "area_avg": 270.0 }
    ]
  },
  "occupancy_trend": [
    { "date": "2026-06-29", "signal": "HIGH" },
    { "date": "2026-07-02", "signal": "MEDIUM" }
  ],
  "days_returned": 2,
  "note": "Run 3+ plans with Swiggy market intelligence enabled to see pricing trends."
}
```

`note` is only present when fewer than 3 qualifying data points exist: the frontend renders an
empty state in that case instead of a partial chart.

---

## Business

Revenue, profit, and complaint analytics for the Today dashboard: computed directly from `Order`,
`MenuItem`, `Feedback`, and `Expense`, independent of any planning run.

### `GET /api/v1/business/performance`

**Auth:** JWT required.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer (1–90) | `14` | Trailing window for the trend, dish ranking, and period P&L |

**Response `200`**

```json
{
  "period_days": 14,
  "yesterday": {
    "date": "2026-07-06", "revenue": 20189.0, "profit": 13321.0, "margin_pct": 66.0,
    "orders": 25, "avg_order_value": 807.56,
    "expenses": 4066.67, "net_profit": 9254.33, "net_margin_pct": 45.8
  },
  "today_so_far": { "...": "same shape as yesterday" },
  "trend": [ { "date": "2026-06-24", "revenue": 18420.0, "profit": 12100.0, "orders": 22 } ],
  "top_dishes": [ { "name": "Four Cheese", "category": "pizza", "revenue": 1500.0, "quantity": 5, "margin_pct": 16.7 } ],
  "bottom_dishes": [ "...same shape as top_dishes" ],
  "channel_split": { "dine_in_revenue": 12000.0, "delivery_revenue": 8189.0, "dine_in_orders": 15, "delivery_orders": 10 },
  "complaints_by_category": [ { "category": "Wait Time", "count": 6 } ],
  "peak_hours": [ { "hour": 19, "avg_orders": 4.2 } ],
  "total_expenses": 71933.38,
  "net_profit": 307646.62,
  "net_margin_pct": 53.8,
  "health_score": 86
}
```

`expenses`/`net_profit`/`net_margin_pct` on each `DaySnapshot`, and the top-level
`total_expenses`/`net_profit`/`net_margin_pct`/`health_score` fields, are the financial
scorecard. Expenses are prorated from the `Expense` ledger (one-time/daily/weekly/monthly
recurrence) into a daily-equivalent figure via `BusinessAnalyticsService.get_daily_expense_total`.
`health_score` (0–100) is a deterministic composite: 70% net margin over `days` (normalized against
a 30%-net-margin benchmark, capped at 100), 30% positive-sentiment share over the last 28 days of
feedback. Missing margin data (no revenue) defaults to 0; missing sentiment data defaults to a
neutral 50: see `BusinessAnalyticsService.compute_health_score`.

`yesterday`/`today_so_far` are `null` when that day has no orders yet: the frontend renders a
"no data yet" state rather than zeros.

---

## Action Queue

Approval-gated agentic recommendations: restock alerts, WhatsApp vendor-order drafts,
pricing/promo review flags. Auto-populated after every planning run by two built-in workflow
triggers: 2+ critical shortages queues a `restock_alert`; tonight-busy plus 2+ competitor
Dineout deals queues a `pricing_promo_review`. Both are `recommendation`-tier: informational only,
never auto-executed.

### `GET /api/v1/action-queue`

**Auth:** JWT required.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | *(none: all statuses)* | Filter: `pending`, `approved`, `executed`, `rejected`, `expired` |

**Response `200`**

```json
[
  {
    "id": 14, "category": "whatsapp_vendor_order", "tier": "approve_required", "status": "pending",
    "title": "Order Mozzarella Cheese from Ramesh Traders",
    "payload": { "vendor_id": 1, "vendor": "Ramesh Traders", "ingredient": "Mozzarella Cheese",
                 "message_draft": "Ramesh bhai, mozzarella is almost done..." },
    "approved_by": null, "executed_at": null, "error": null, "created_at": "2026-07-08T06:47:20",
    "approval_streak": 2
  }
]
```

`approval_streak` is a read-only count of how many times in a row this
`category` has been approved before (a rejection anywhere breaks the streak): informational only,
never bypasses approval. See `TrustLadderService.count_consecutive_approvals`.

### `POST /api/v1/action-queue/{action_id}/approve`

For a `whatsapp_vendor_order` action, approval and execution are the same step: this call also
triggers the real WhatsApp send via Twilio. On send failure, the action stays `approved`
with `error` populated rather than losing the approval decision. Other categories are approved only
- no execution step wired for them yet.

Shared logic lives in `action_execution_service.approve_and_execute`, called identically by this
route, the in-app chatbot's `approve_action` tool, and the MCP server's `approve_action` tool
: approving via any of the three surfaces behaves the same way.

### `POST /api/v1/action-queue/{action_id}/reject`

Transitions status to `rejected` only: never executes anything.

---

## Chat

### `POST /api/v1/chat`  *(SSE stream)*

RAG chatbot over the org's planning history and guest feedback. Streams token-by-token via SSE.

**Auth:** JWT required.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | Yes | User's question (1–1000 chars) |
| `history` | array | No | Prior turns: `[{"role": "user"/"assistant", "content": "..."}]` |

**SSE event format**

```
data: {"token": "Based"}
data: {"token": " on"}
data: {"token": " your"}
...
data: {"done": true}
```

**Data sources:** the last 10 `planning_runs` for the org (org-scoped) and the last 30 `feedback` records (not org-filtered: shared across the demo dataset). Responses are also checked against `SemanticChatCache` (Qdrant-backed, 24hr TTL): identical or near-identical questions return cached answers instantly without an LLM call.

**Within-session memory:** the last 8 turns are sent verbatim; older turns in the same session are compressed and injected as a summary to preserve conversational context.

**Example questions the chatbot handles**

- "What were the most common complaints recently?"
- "Which run had the lowest critic score and why?"
- "Which ingredients keep showing up as low stock?"
- "How is my restaurant performing overall?"
- "If I had to focus on one thing to improve our score, what would it be?"
- "What's the market situation right now?" maps to the `get_market_brief` tool
- "What's waiting for my approval?" maps to the `get_action_queue` tool
- "Approve the mozzarella reorder" maps to the `approve_action` tool: for a WhatsApp vendor order, this is
  the same step that actually sends the message, so only fires on the user's explicit approval, never
  on the model's own initiative

---

## Observability

### `GET /api/v1/observability/summary`

Returns a 7-day planning summary for the org.

**Auth:** JWT required.

**Response `200`**

```json
{
  "period_days": 7,
  "total_runs": 59,
  "success_rate": 0.81,
  "avg_critic_score": 0.81,
  "avg_duration_ms": 16600,
  "by_verdict": {
    "approved": 48,
    "revision": 10,
    "rejected": 1
  },
  "by_scenario": {
    "friday_rush": 39,
    "low_stock_weekend": 7,
    "weekday_lunch": 7,
    "holiday_spike": 6
  },
  "top_scenario": "friday_rush",
  "latest_run_at": "2026-06-07T10:39:57"
}
```

---

### `GET /metrics`

Prometheus scrape endpoint. Returns OpenMetrics-format metrics including HTTP request count, latency histograms, and error rate by route and method.

**Auth:** None (public scrape endpoint).

---

### `GET /debug/sentry-test`

Intentionally raises a `RuntimeError` to verify Sentry exception capture is working. Only useful during setup. Note: registered directly on the main app: not under the `/api/v1` prefix.

**Auth:** None.

---

### `POST /replay`

Single-generation LLM replay for Kindred debugging. Mounted directly on the application, not under `/api/v1`, matching Kindred's Configure Replay URL convention.

Accepts a `messages` array (or a plain `input` string as a fallback), extracts the system and user messages, and calls the LLM provider directly for that one generation. This never re-runs the LangGraph pipeline: it replays exactly one LLM call, the same call path every graph node already uses.

Five Kindred metadata fields are accepted either in the request body or as `X-Kindred-*` headers, and are propagated onto the corresponding Langfuse trace so Kindred can locate the original and replay by trace metadata.

**Auth:** Public endpoint; authorization is via Kindred's own metadata, not a JWT.

---

## Data Health

### `GET /api/v1/data-health`

Returns database coverage summary for the seeded operational data.

**Auth:** JWT required.

**Response `200`**

```json
{
  "orders":       { "count": 6495, "date_range": ["2026-01-16", "2026-05-31"] },
  "reservations": { "count": 1201, "date_range": ["2026-01-16", "2026-06-28"] },
  "feedback":     { "count": 160, "negative": 55, "positive": 75, "neutral": 30, "negative_pct": 34.4 },
  "inventory":    { "items": 18, "shortage_alerts": 11, "critical_shortages": 10, "overstock_alerts": 2 },
  "menu":         { "items": 27 },
  "scenario_coverage": [
    {
      "scenario": "friday_rush",
      "date": "2026-08-12",
      "reservations": 15,
      "guests": 61,
      "waitlist": 3,
      "occupancy_pct": 55.5
    }
  ]
}
```

---

## Settings

### `GET /api/v1/settings`

Returns the authenticated org's workspace settings.

**Auth:** JWT required.

**Response `200`**

```json
{
  "org_id": 1,
  "org_name": "Casa Mia",
  "settings": {
    "capacity": 110,
    "cuisine_type": "Italian",
    "peak_hours": "19:00-23:00",
    "timezone": "Asia/Kolkata",
    "critic_threshold": 0.75,
    "low_stock_threshold_pct": 25.0,
    "overstock_threshold_pct": 160.0
  }
}
```

---

### `PATCH /api/v1/settings`

Updates org settings. All fields are optional: only supplied fields are updated.

**Auth:** JWT required (owner role).

---

## Restaurant Profiles

### `GET /api/v1/restaurant-profiles`

Lists all restaurant profiles for the org.

**Auth:** JWT required.

**Response `200`**

```json
{
  "profiles": [
    {
      "id": 3,
      "name": "Casa Mia Rooftop",
      "cuisine": "Italian",
      "capacity": 75,
      "peak_hours": "18:00-22:00",
      "timezone": "Asia/Kolkata"
    }
  ]
}
```

---

### `POST /api/v1/restaurant-profiles`

Creates a new restaurant profile. Profile overrides org-level capacity and peak hours for a planning run when `restaurant_id` is supplied in the planning request.

**Auth:** JWT required (owner role).

---

### `PATCH /api/v1/restaurant-profiles/{id}`

Updates an existing profile.

---

### `DELETE /api/v1/restaurant-profiles/{id}`

Deletes a profile.

---

## Connectors

### `POST /api/v1/connectors/swiggy/sync`

Trigger a live Swiggy MCP sync. Calls `get_food_orders`, `track_food_order`, and
`get_booking_status` against the real Swiggy API. Requires `SWIGGY_ACCESS_TOKEN` and
`SWIGGY_ADDRESS_ID` set in `.env` (run `python scripts/get_swiggy_token.py` to obtain them).

**Auth:** JWT required.

**Response `200`**

```json
{
  "status": "success",
  "message": "Live Swiggy data synced. Check orders and feedback tables.",
  "results": {
    "orders":       {"synced": 5, "skipped": 2, "errors": 0},
    "feedback":     {"synced": 3, "skipped": 2, "errors": 0},
    "reservations": {"synced": 0, "skipped": 0, "errors": 0,
                     "note": "No Dineout bookings registered yet. Booking IDs are captured when book_table is called."}
  }
}
```

**Error `400`**: token or address not configured:
```json
{"detail": "SWIGGY_ACCESS_TOKEN not configured. Run: python scripts/get_swiggy_token.py"}
```

---

### `GET /api/v1/connectors/status`

Returns connection status and sync counts for all connectors registered for this org.
Used by the `/connectors` frontend page.

**Auth:** JWT required.

**Response `200`**

```json
{
  "connectors": [
    {
      "type": "swiggy",
      "name": "Swiggy",
      "logo": "/swiggy-logo.png",
      "connected": true,
      "last_sync_at": "2026-06-30T07:15:00",
      "sync_status": "success",
      "orders_synced": 47,
      "feedback_synced": 12,
      "address_configured": true
    }
  ]
}
```

---

## Guest Concierge

A no-auth, consumer-facing surface, entirely independent of the restaurant-operator routes above. None of the following routes depend on `get_current_user`.

### `POST /api/v1/concierge/chat` *(SSE stream)*

Sends a message to the Guest Concierge and streams the response.

**Auth:** None.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | No | Existing session id; a new one is created if omitted or not found |
| `message` | string | Yes | The guest's message |

**SSE event format**

```
data: {"session_id": "a1b2c3..."}
data: {"type": "status", "content": "Finding venues..."}
data: {"type": "tool_result", "tool": "find_venues", "data": {"venues": [...]}}
data: {"type": "text", "content": "I found "}
data: {"type": "text", "content": "a few "}
data: {"done": true}
```

Three chunk types stream over the connection: `status` (a friendly "doing X..." label while a tool call is in flight), `tool_result` (the structured data a tool just returned, rendered as a real card), and `text` (the narrated answer, streamed word by word). Any failure, tool-level or otherwise, degrades to a fixed, friendly `text` message: never a raw exception, stack trace, or internal tool name.

---

### `GET /api/v1/concierge/session/{session_id}`

Returns the current state of a session: occasion, headcount, budget spent and remaining, preferences, active bookings, active food and Instamart orders, suggested venues, and the Instamart cart.

**Auth:** None. **Error `404`**: session not found or expired (2-hour TTL).

---

### `DELETE /api/v1/concierge/session/{session_id}`

Clears a session. **Auth:** None. **Response:** `204`.

---

### `POST /api/v1/concierge/transcribe`

Voice input for the Guest Concierge, same contract as `/planning/transcribe` but with no auth requirement.

**Auth:** None.

**Request:** `multipart/form-data` with a `file` field.

**Response `200`**: `{ "text": "..." }`

---

### `GET /api/v1/concierge/health`

Reports which Guest Concierge tools are available right now.

**Auth:** None.

**Response `200`**

```json
{
  "swiggy_connected": true,
  "staging_enabled": false,
  "tools_available": ["find_venues", "check_table_availability", "find_food", "find_supplies", "..."],
  "tools_pending_staging": ["book_table", "order_supplies"]
}
```

`tools_pending_staging` lists tools that require Swiggy staging credentials (table booking, Instamart checkout); when staging is enabled they move into `tools_available`.

---

## Error responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid JWT |
| `403` | Action requires owner role |
| `404` | Resource not found or belongs to a different org |
| `422` | Request body validation failed (Pydantic) |
| `500` | Internal server error: check Sentry and structlog output |

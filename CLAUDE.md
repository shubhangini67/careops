# CareOps AI — Claude Code Master Reference

> **Read this file completely before touching any code.**

---

## Product vision

CareOps AI is a **two-sided service platform powered by Swiggy MCP**.

### Side 1 — Restaurant OS 

AI-powered operating system for restaurant operators. Operators log in, run
planning scenarios, get market-aware operational plans, manage procurement,
track financial health, approve actions.

### Side 2 — Guest Concierge 

Consumer-facing intelligent assistant. Guests describe what they want —
"plan my best friend's 25th birthday, 14 people, pizza lover, Rs.10k budget"
— and the concierge uses all 3 Swiggy MCP servers to plan their experience
end-to-end: finding venues, checking slots, surfacing deals, suggesting
Instamart supplies, ordering food, tracking everything.

**These two sides are INDEPENDENT.** The concierge does not connect to any
specific restaurant's CareOps AI data. It uses Swiggy's platform to serve
consumers directly. This is exactly what clause 1.1 of the signed Swiggy
Integration Agreement describes as the Proposed Arrangement.

---

## Compliance — signed Swiggy Integration Agreement (effective 2026-07-09)

**Clause 6.1 — Exclusivity:** Zomato stub removed (P6-A19). No other food
delivery/dining/quick-commerce platform integrations allowed.

**Clause 4(iv) — No competitive intelligence ON named restaurants:** Market
intel outputs are anonymised (P6-A20). All enricher outputs use area-level
aggregates only — no restaurant names, no individual pricing. "Area avg for
North Indian mains: Rs.265" not "Biryani House charges Rs.280."

**What remains fully compliant:**
- Instamart procurement (search_products) — no restaurant data
- Weather/trends/compliance signals — not Swiggy at all
- Planning pipeline — uses internal restaurant data
- Guest concierge — serving consumers through Swiggy (clause 1.1 purpose)

**Clause 3.4(ii):** Display "powered by Swiggy" wherever MCP is used.

---

## Current system state — what is actually built

### LangGraph pipeline — 13 nodes

```
ops_manager (scenario routing — presets OR custom_profile via ScenarioProfileService)
    │
live_signals (weather + trends + compliance + holiday — runs once, all nodes read from state)
    │
demand_forecast (Prophet + WeatherService signal adjustment, transparent pre/post values)
    │
qdrant_enrichment (shared RAG context for all parallel nodes)
    │
    ├── reservation          (ReservationService + OccupancyEnricher)
    ├── complaint_intelligence (ComplaintService + Qdrant RAG + sentiment)
    ├── inventory            (InventoryService + ProcurementEnricher: Instamart prices)
    ├── market_intel         (CompetitorEnricher + OccupancyEnricher + live signals merge)
    └── dineout_manager      (Dineout slot analysis — dormant: no real restaurant ID)
            │
menu_intelligence (synthesises all 5 parallel outputs + live_signals_text)
            │
aggregator (builds unified brief — includes [Live Signals] line for critic)
            │
critic (LLM scoring: 5 dimensions + 7 assumption diffs, replanning loop max 2 retries)
            │
replan_orchestrator (injects critic notes → menu_intelligence → re-aggregate)
            │
situation_summary (narrative summary for final output)
            │
final_assembler (builds API response with action_queue section)
```

### OrchestratorState — key fields

```python
# Scenario
scenario, scenario_profile, custom_profile, target_date, org_id

# Node outputs
forecast_output, reservation_output, complaint_output
menu_output, inventory_output

# Live signals (set by live_signals node, read by demand_forecast + market_intel)
weather_signal, trends_signal, compliance_alerts_signal, holiday_context

# Swiggy enrichment
swiggy_competitor_context    # from CompetitorEnricher (anonymised area data)
swiggy_occupancy_context     # from OccupancyEnricher (anonymised area signals)
swiggy_procurement_options   # from ProcurementEnricher (spinIds + prices)
swiggy_delivery_signal       # unused (personal account data limitation)
market_intel_output          # merged output from market_intel node
dineout_manager_output       # from dineout_manager node

# Assumption diffs (7 active)
menu_assumptions, inventory_assumptions, reservation_assumptions
complaint_assumptions, market_intel_assumptions, dineout_manager_assumptions

# Pipeline control
aggregated_recommendation, critic_output, situation_summary_output
final_response, replan_count, replan_context, execution_trace
```

### Backend services — complete list

```
infrastructure/
├── external/
│   ├── weather_service.py         WeatherService: Open-Meteo, demand multiplier
│   ├── trends_service.py          TrendsService: RSS industry trends
│   └── compliance_alerts_service.py ComplianceAlertsService: FSSAI notices
├── swiggy/
│   ├── client.py                  SwiggyMCPClient: JSON-RPC 2.0, OAuth, circuit breaker
│   ├── circuit_breaker.py         Redis-backed: 3 failures/5min → 30min open
│   ├── base_connector.py          BaseConnector ABC
│   ├── swiggy_connector.py        SwiggyConnector (sync orchestration)
│   ├── connector_repository.py    Per-org token CRUD
│   ├── provider_registry.py       Capability routing (Swiggy only — Zomato removed)
│   ├── enrichers/
│   │   ├── competitor.py          search_restaurants + get_restaurant_menu +
│   │   │                          fetch_food_coupons → anonymised area pricing,
│   │   │                          positioning, menu breadth, cuisine crowding,
│   │   │                          veg mix, deals count, pricing impact model
│   │   ├── occupancy.py           search_restaurants_dineout + get_available_slots +
│   │   │                          get_restaurant_details → anonymised occupancy signal,
│   │   │                          area deals count, slot availability summary
│   │   └── procurement.py         search_products → ingredient prices + spinIds
│   │                              (your_go_to_items removed: personal data)
│   ├── sync/                      order_sync, feedback_sync, reservation_sync
│   │                              (limited value: personal account data)
│   └── executor/                  EMPTY: staging creds needed
├── vector/
│   ├── embedding_service.py
│   ├── memory_service.py
│   ├── planning_memory.py
│   ├── qdrant_client.py
│   └── session_memory.py          Cross-session memory for chatbot
├── cache/                         Redis plan cache + semantic cache
├── llm/                           CometAPI provider, prompt utils
├── db/                            models.py, base.py (PostgreSQL + Alembic)
├── whatsapp/                      WhatsApp vendor coordination
└── observability/                 Langfuse tracing, dependency health

domain/services/
├── action_execution_service.py    Executes approved actions
├── action_queue_service.py        CRUD for action_queue table
├── business_analytics_service.py  Dish margin, complaint categories, peak hours,
│                                  expense proration, composite health score (0-100)
│                                  Used by: business.py + planning pipeline + chatbot
├── chat_service.py                Groq function calling chatbot (operator-facing)
│                                  Tools: query_runs, get_run_detail, get_inventory_status,
│                                  trigger_planning_run, swiggy_get_food_orders,
│                                  swiggy_search_products, swiggy_get_competitor_deals,
│                                  swiggy_get_area_occupancy, swiggy_get_common_dishes,
│                                  get_market_brief, get_action_queue, approve_action
├── complaint_service.py
├── cost_aware_scoring.py
├── critic_service.py
├── daily_briefing_service.py      On-demand AI executive summary (hourly cached)
├── evaluation_sanity.py           7 assumption diffs (O(N))
├── forecast_service.py            Prophet + _apply_signal_adjustments (weather)
├── inventory_service.py
├── live_scenario_composer.py
├── market_intel_service.py        Orchestrates enrichers concurrently
│                                  _build_live_signals_text: merges competitor +
│                                  occupancy + weather + trends + compliance
├── menu_service.py
├── reservation_service.py
├── run_service.py
├── scenario_profile_service.py    LLM: free-text → ScenarioProfilePayload
├── scenario_recommender.py        Suggests scenario from run history + market + calendar
├── trust_ladder_service.py        AUTO_EXECUTE / APPROVE_REQUIRED / RECOMMEND tiers
└── vendor_service.py

api/routes/
├── action_queue.py    GET /action-queue, POST /action-queue/{id}/approve|reject
├── auth.py            POST /auth/login, /auth/register
├── business.py        GET /business/performance (P&L, health score, expense ledger)
│                      GET /business/summary (AI executive summary, hourly cached)
├── chat.py            POST /chat (streaming), GET /chat/sessions, etc.
├── connectors.py      POST /connectors/swiggy/sync, GET /connectors/status
├── health.py          GET /health
├── market.py          GET /market/pulse (live enricher data)
│                      GET /market/ingredient-search (on-demand Instamart)
│                      GET /market/trends (price + occupancy history)
├── planning.py        POST /planning/run, POST /planning/stream
│                      GET /planning/recommend (ScenarioRecommender)
│                      POST /planning/scenario-from-text (ScenarioProfileService)
├── replay.py          Langfuse/Kindred replay support
├── restaurant_profiles.py
├── runs.py            GET /runs, GET /runs/{id}
├── settings.py
└── vendors.py         WhatsApp vendor coordination
```

### Frontend pages — complete list

```
/                   Home page (restaurant OS landing — guest concierge section to be added P6-B04)
/login              Auth
/register           Auth
/dashboard          Daily overview: health score, KPIs, live-intelligence context strip
                    (weather/holiday/trends/compliance/area-occupancy badges)
                    BriefingService AI executive summary
/planning           Flagship: trigger + watch streaming pipeline run
                    Per-node observability strip, evidence panel
                    PlanShiftModal: scenario tiles + free-text input + TodayContextStrip
                    What-if simulator, PDF/Excel export
/action-center      Pending approvals + full Action Queue history
/analytics          Historical: menu engineering matrix, channels, peak hours, complaints
/data               Merged run history + data-health + audit trail
/market             Live market intel: anonymised area pricing (CategoryPricingChart),
                    pricing impact (PricingImpactChart), occupancy (OccupancyBySlotChart),
                    Instamart ingredient lookup (IngredientPriceLookup),
                    price trends (MarketTrendChart)
/connectors         Swiggy connection status, sync trigger
/chat               Agentic operator chatbot with function calling + Swiggy tools
/restaurant-profiles Restaurant profile management
/settings           Org settings
/concierge          TO BE BUILT (Phase 6B) — guest-facing chat
(/operations, /runs, /runs/{id}, /data-health — redirect stubs only)
```

### Swiggy tools — current status

**Operator side (enrichers + chatbot):**

| Tool | Where | Output |
|------|-------|--------|
| `search_restaurants` | CompetitorEnricher | Anonymised area pricing, positioning |
| `get_restaurant_menu` | CompetitorEnricher | Category pricing aggregates |
| `fetch_food_coupons` | CompetitorEnricher | Area deals count (anonymised) |
| `search_restaurants_dineout` | OccupancyEnricher | Anonymised occupancy signal |
| `get_available_slots` | OccupancyEnricher | Area slot availability + deals count |
| `get_restaurant_details` | OccupancyEnricher | Anonymised area Dineout deals |
| `search_products` | ProcurementEnricher + chatbot | Live Instamart prices + spinIds |
| `get_food_orders` | chatbot (swiggy_get_food_orders) | Personal orders history |

**Guest concierge (Phase 6B — to be built):**

| Tool | Server | Consumer use |
|------|--------|-------------|
| `get_addresses` | Food/IM | Resolve guest's delivery address |
| `search_restaurants` | Food | Find food delivery options |
| `get_restaurant_menu` | Food | Browse menus |
| `update_food_cart` | Food | Add items to cart |
| `get_food_cart` | Food | View cart |
| `flush_food_cart` | Food | Clear cart |
| `fetch_food_coupons` | Food | Find COD-compatible deals |
| `apply_food_coupon` | Food | Apply best coupon |
| `place_food_order` | Food | Place real order (works now, COD, <Rs.1000) |
| `get_food_orders` | Food | Guest's order history |
| `get_food_order_details` | Food | Specific order detail |
| `track_food_order` | Food | Real-time delivery tracking |
| `report_error` | Food | Report order issues |
| `search_products` | Instamart | Find supplies + cake + drinks |
| `update_cart` | Instamart | Build supplies cart (spinId required) |
| `get_cart` | Instamart | View Instamart cart |
| `clear_cart` | Instamart | Clear Instamart cart |
| `checkout` | Instamart | BLOCKED: staging creds needed |
| `get_orders` | Instamart | Order history + check-then-retry |
| `track_order` | Instamart | Track delivery (needs lat+lng) |
| `get_saved_locations` | Dineout | Resolve lat/lng (NOT addressId) |
| `search_restaurants_dineout` | Dineout | Find dine-in venues |
| `get_restaurant_details` | Dineout | Deals, amenities, timings |
| `get_available_slots` | Dineout | Real slot availability |
| `create_cart` | Dineout | Internal to book_table |
| `book_table` | Dineout | BLOCKED: staging creds needed |
| `get_booking_status` | Dineout | Booking confirmation + check-then-retry |

**Staging creds unlock (executor/ folder is ready but empty):**
- `update_cart` + `get_cart` + `checkout` → Instamart procurement execution
- `create_cart` + `book_table` → Dineout table booking

---


```

---

## next what is being built now

Branch: `feature/phase6b-guest-concierge`

Tasks in order:
- P6-B01: ConciergeService backend (concierge_service.py)
- P6-B02: Concierge API route (concierge.py, no auth)
- P6-B03: Home page update (add guest concierge section)
- P6-B04: /concierge frontend page (consumer chat experience)
- P6-B05: Occasion intelligence + budget optimisation
- P6-B06: Instamart supply suggestions for events
- P6-B07: book_table execution (BLOCKED: staging creds)
- P6-B08: Instamart checkout (BLOCKED: staging creds)

---

## Critical Swiggy rules — for Claude Code

**BEFORE writing any Swiggy tool call:**
1. Check this file's tool table above for correct server + params
2. Read docs/SWIGGY_INTEGRATION.md sections 16-18 for response schemas

**Non-negotiable:**
- `checkout` and `book_table`: NOT idempotent. On 5xx → check-then-retry.
  checkout: call get_orders before retrying.
  book_table: call get_booking_status before retrying.
- Dineout uses lat/lng. Food + Instamart use addressId. NEVER mix.
- `update_cart` (Instamart): REPLACES entire cart. Not additive.
- All enrichers return None on failure. Never raise. Nodes handle None gracefully.
- `spinId` (not product id) for all Instamart cart operations.
- Required header on every call: Accept: application/json, text/event-stream
- Response format: result.structuredContent (not success/data)
- Dineout slots: only use deals where isFree=True in Builders Club v1
- Food orders: COD only, Rs.1000 cap per order in Builders Club v1
- fetch_food_coupons: only surface requiresOnlinePayment=False to guest

**Known Dineout response shape bugs (already fixed in occupancy.py):**
- search_restaurants_dineout: empty structuredContent needs render_restaurants_dineout follow-up
- get_restaurant_details: nested offers/restaurant fields
- get_available_slots: slots live in _meta, no numeric availabilityCount
Reference occupancy.py for the correct parsing — copy that pattern.

**OAuth:**
```
SWIGGY_ACCESS_TOKEN=eyJ...  (5-day TTL, run scripts/get_swiggy_token.py to refresh)
SWIGGY_ADDRESS_ID=cjpfcd75ofl5oefqs8mg  (Navi Mumbai — Food + Instamart)
# Dineout: use get_saved_locations to get lat/lng, not addressId
```

---

## Settings — key env vars

```python
# LLM
llm_provider: str          # "groq" default
groq_api_key: str
cometapi_key: str
cometapi_model_fast: str   # deepseek-v4-flash
cometapi_model_balanced: str  # gemini-3.5-flash
cometapi_model_strong: str    # claude-sonnet-4-6

# Swiggy
swiggy_access_token: str
swiggy_address_id: str
swiggy_dineout_restaurant_id: str  # empty — no real restaurant

# Infrastructure
qdrant_url: str            # http://localhost:6333
redis_url: str             # redis://localhost:6379/0

# Observability
langfuse_public_key: str
langfuse_secret_key: str
langfuse_host: str
```

---

## Patterns to follow — always check before writing new code

- Redis caching: infrastructure/cache/plan_cache.py
- Structlog logging: use log = structlog.get_logger()
- Settings: from app.core.settings import get_settings
- LangGraph state: app/orchestration/state.py
- Swiggy call pattern: infrastructure/swiggy/enrichers/procurement.py
- Dineout response parsing (buggy): infrastructure/swiggy/enrichers/occupancy.py
- Streaming chat: app/domain/services/chat_service.py + app/api/routes/chat.py
- Groq function calling: chat_service.py _TOOLS + handle_tool_call pattern
- Auth dependency: app/api/dependencies.py get_current_user
- New route registration: app/api/routes/__init__.py

---

## After every PR merge — update this file

Update "Current system state" with newly built files.
Update tool table (mark new tools as active).
Update frontend pages list.

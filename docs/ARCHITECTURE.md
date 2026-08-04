# CareOps AI Architecture

Reflects the implemented codebase, Phase 6A in progress.

---

## Overview

CareOps AI is a two-sided platform built on the Swiggy MCP. The restaurant-operator side coordinates structured operational data, live external signals, time-series forecasting, vector retrieval, LLM reasoning, and business-rule validation through a fifteen-node LangGraph pipeline. The guest-facing side, Guest Concierge, is an independent, no-auth agent that plans a guest's dining or event experience directly through Swiggy's Food, Instamart, and Dineout MCP servers. The frontend presents restaurant-operator results across a dedicated planning experience, a daily overview dashboard, an Action Center, an Analytics page, and a merged data and observability page; Guest Concierge is a separate, no-auth `/concierge` experience with no operator chrome.

Phase 5 added: SSE streaming, Redis caching, PDF/Excel export, what-if simulator, OpenTelemetry, Prometheus, Sentry, LangSmith regression evals with a golden dataset, multi-tenant workspace isolation (PostgreSQL and Qdrant), and a RAG chat assistant.

Phase 6A (in progress) added: Swiggy MCP integration with the connector pattern and circuit breaker, compliance remediation (removal of a competing-platform stub connector, anonymization of market intelligence output), an Action Queue with an informational trust-ladder badge, a financial scorecard, live intelligence signals (weather, industry trends, regulatory alerts) merged into the planning pipeline, dynamic scenario composition from live signals, Langfuse tracing with a Kindred replay endpoint, a redesign of the frontend information architecture splitting Dashboard and Planning into separate pages, a two-sided platform homepage with a dual entry point, and Guest Concierge.

---

## System shape

```
Claude Code / Claude Desktop
    MCP stdio protocol
mcp_server.py
    HTTP (JWT) and SSE
Next.js UI (App Router)
  /                    public homepage: two-sided platform, dual entry point
  /login, /register    restaurant-operator auth flow, shared split-screen layout
  /dashboard            daily overview, KPIs, health score, live-intelligence card
  /planning             flagship trigger-and-watch experience, streaming pipeline run
  /action-center        pending approvals and Action Queue history
  /analytics            historical drill-down
  /data                 merged run history and data-health view, exports
  /market               live Swiggy market intelligence
  /chat                 operator chat assistant, full page and floating widget
  /connectors           Swiggy connector status
  /restaurant-profiles, /settings
  /concierge             no-auth Guest Concierge: consumer chat, no operator chrome
  (/operations, /runs, /runs/{id}, /data-health are redirect stubs only)
    HTTP (JSON and SSE) with JWT, except Guest Concierge (no auth)
FastAPI application, mounted under /api/v1 unless noted
  auth: register, login, me
  health: liveness, dependencies, Swiggy circuit breaker state
  planning: scenarios, scenario-from-text, compose-live-scenario, run, stream,
            whatif, recommend, friday-rush (legacy), transcribe (voice input)
  market: pulse, ingredient-search, trends
  business: performance, summary
  action-queue: list, approve, reject
  runs: list, detail, export (PDF and Excel), data-health, observability summary
  chat: send message (SSE), list sessions, session detail
  restaurant-profiles: CRUD
  settings: get, update
  connectors: sync, status
  concierge: chat (SSE), session get/delete, transcribe, health -- no auth dependency
  /replay (Kindred single-generation replay, mounted outside /api/v1)
  /metrics (Prometheus, public)
LangGraph orchestration graph, fifteen nodes (see docs/AGENTS.md)
Service and data layer
  PostgreSQL     structured data plus the planning_runs audit table, org-scoped
  Qdrant         complaints and SOPs (RAG), planning_memory, semantic_cache, chat_semantic_cache
  Redis          plan cache by scenario and date; circuit breaker state per Swiggy endpoint
  LLM provider   Groq (default), Gemini (fallback), or CometAPI with per-node tier routing
```

---

## Connector layer (Phase 6)

External platform integrations live in `apps/api/app/infrastructure/swiggy/`. All connectors implement `BaseConnector` (ABC) with two methods:

| Method | When called | DB writes? | On failure |
|--------|------------|------------|------------|
| `sync()` | Nightly APScheduler job | Yes: writes to orders/reservations/feedback | Logged, error_count++ in connectors table |
| `enrich()` | At planning time, before fan-out | No | Returns `None`: node falls back to synthetic data |

**File structure:**
```
infrastructure/base_connector.py: BaseConnector ABC (sync + enrich contract), shared across all
                                  connector types, not Swiggy-specific

infrastructure/swiggy/
  __init__.py
  client.py             : SwiggyMCPClient (JSON-RPC 2.0, httpx, graceful degradation)
  circuit_breaker.py    : Redis-backed circuit breaker
  swiggy_connector.py   : SwiggyConnector (reference implementation)
  connector_repository.py: ConnectorRepository (DB: token, sync_status, error_count)
  provider_registry.py  : capability-to-provider routing
  enrichers/            : CompetitorEnricher, OccupancyEnricher, ProcurementEnricher
  executor/             : currently empty; ProcurementExecutor and DineoutExecutor are blocked on
                          Swiggy staging credentials for update_cart/get_cart/checkout/book_table

infrastructure/jobs/
  async_runner.py       : Redis-backed async job queue for planning runs (no external job library)
```

**Three Swiggy MCP servers:**
- `https://mcp.swiggy.com/food`: delivery orders, competitor menus
- `https://mcp.swiggy.com/im`: Instamart ingredient procurement
- `https://mcp.swiggy.com/dineout`: table reservations, competitor occupancy

**Token management:** OAuth tokens stored encrypted per `org_id` in the `connectors` table. `SWIGGY_ACCESS_TOKEN` in `.env` is dev-only. Production reads from `ConnectorRepository`.

**Governance layer:**

- **Circuit breaker** (`infrastructure/swiggy/circuit_breaker.py`): Redis-backed: 5 or more failures within a 5-minute window opens the circuit for that Swiggy endpoint, currently a 10-minute open window. `SwiggyMCPClient.call_tool()` checks the circuit before every HTTP call and records failure/success on every result. Endpoint tags: `food`, `im`, `dineout`. Exposed at `GET /api/v1/health/circuits`.
- **Provider registry** (`infrastructure/swiggy/provider_registry.py`): routes planning capabilities (`competitor_pricing`, `reservation_data`, `procurement`, `order_history`) to the highest-priority healthy provider. `get_provider_async()` combines DB `sync_status` with live circuit breaker state so a mid-day Swiggy degradation automatically falls through to the next candidate. Currently `swiggy` is the only provider for every capability: the multi-provider architecture stays ready for future connectors (POS systems, review platforms, loyalty/rewards, accounting/inventory tools).
- **Tool tracing**: every `SwiggyMCPClient` call appends a trace dict to `self._traces`; `drain_traces()` returns and clears them for downstream observability. Trace fields: `provider`, `endpoint`, `tool`, `status`, `duration_ms`, `attempt`, `error?`. Status values: `ok`, `circuit_open`, `auth_error`, `http_{code}`, `tool_error`, `exception`.

See the connector layer design decision in `docs/DECISIONS.md` for the full design rationale.

---

## Live-intelligence signals

Not Swiggy MCP: no consent/compliance gating applies to any of these.
Each is its own independently fail-open service, following the same
graceful-degradation contract as the Swiggy enrichers (`BaseConnector`):
never raise, return `None` on any failure.

- **Weather + holidays** (`infrastructure/external/weather_service.py`) -
  Open-Meteo, free, keyless REST API. `WeatherService.get_forecast(lat, lng,
  target_date)` averages temperature + precipitation probability across the
  target date's 18:00–22:00 dinner window, classifies into
  `heavy_rain`/`light_rain`/`very_hot`/`clear`, and returns a conservative
  `demand_multiplier` alongside descriptive `delivery_impact`/`dinein_impact`
  strings. Holiday lookup (`core/calendar_utils.py`, `get_date_context`) is
  a plain dict scan against `INDIAN_HOLIDAYS_2026`: shared between
  `ScenarioRecommender` and `demand_forecast_node` so the lookup isn't
  duplicated.
- **`demand_forecast_node`** applies both as a deterministic multiplier to
  Prophet's raw `predicted_orders`/`predicted_peak_orders`
  (`ForecastService._apply_signal_adjustments`): not just narrative prompt
  text. Transparent by construction: `predicted_orders_pre_adjustment`,
  `adjustment_multiplier`, and `adjustment_reasons` are preserved alongside
  the adjusted number.
- **`GET /market/pulse`** returns `weather` and `upcoming_holiday`
  independently of `swiggy_connected`: neither depends on a Swiggy
  connection existing.
- Default coordinates (`core/constants.py`:
  `DEFAULT_RESTAURANT_LAT`/`DEFAULT_RESTAURANT_LNG`, Navi Mumbai) are used
  until `RestaurantProfile` stores real per-restaurant coordinates.
- **Industry trends** (`infrastructure/external/trends_service.py`) -
  `TrendsService.get_digest()` fetches a curated list of Indian F&B/agri-
  business RSS feeds (`feedparser`, free/keyless, zero ToS risk: not
  Google Trends/pytrends, which scrapes a non-public endpoint) and
  summarizes headlines + article summaries into a short digest via the
  existing `create_llm_provider()` factory (no new LLM integration). Cached
  in Redis for 1 hour (news moves slower than Swiggy signals; an LLM call
  isn't free). Prompt is tuned for specificity (a fact + an operational
  implication per bullet) and stays neutral about any named platform rather
  than reading as scrutiny of it.
- **Regulatory alerts** (`infrastructure/external/compliance_alerts_service.py`)
 : `ComplianceAlertsService.get_alerts()` scrapes FSSAI's public
  notifications page (Gazette Notification category: finalized
  regulations, not drafts). Confirmed live: no RSS feed exists, but the page
  is plain server-rendered HTML (a category `<select>` + form reload, no
  JS/AJAX), so a lightweight BeautifulSoup parser is sufficient. Public
  government data: no ToS tension of any kind.
- **`GET /market/pulse`** also returns `industry_trends` and
  `compliance_alerts` independently of `swiggy_connected`: same treatment
  as weather/holidays.

**Unification**: all four signals merge into one "Area & Live
Signals" text inside the existing `market_intel_node`/`MarketIntelService`
(`MarketIntelService._build_live_signals_text`), rather than a new graph
node. Existing state field names (`swiggy_competitor_context`,
`swiggy_occupancy_context`, `market_intel_output`) are unchanged: only a
new `market_intel_output["live_signals_text"]` key was added: since 5+
files and the frontend already read the old names by string key.
`weather_signal`/`trends_signal`/`compliance_alerts_signal` are fetched once
by `demand_forecast_node` (it runs before the `qdrant_enrichment` fan-out,
so it can't read `market_intel_output`) and injected directly into its own
LLM narrative (`ForecastService.analyse_and_recommend`, text-only for
trends/compliance: only weather shifts the actual number);
`market_intel_node` reads the same three back from state rather than
re-fetching, and merges them with the Swiggy competitor/occupancy prompt
text into `live_signals_text`, which `menu_intelligence` (via
`MenuService.analyse_and_recommend`'s `market_context`) and the critic (via
`aggregator.py`'s `_build_critic_summary`, a condensed `[Live Signals]`
line: the full prose is menu_intelligence's job, not the critic's) both
read. Each of the five sources (competitor, occupancy, weather, trends,
compliance) stays independently optional through this whole chain: any
subset being `None` (simulated per-source failure) never blocks the others
or raises.

---

## Scenario intake modes

Full detail in `docs/PRODUCT_MODES.md`. Summary: `ops_manager_node` needs a
`scenario_profile` (`label`/`service_window`/`operational_focus`) regardless
of source. Two intake modes feed it, both converging on the same downstream
pipeline:

1. **Presets** (unchanged): `scenario` is one of the 4
   `SCENARIO_DEFINITIONS` keys, `ops_manager_node` resolves via
   `get_scenario_definition()`.
2. **Natural language** (new): free text goes to
   `POST /planning/scenario-from-text` (`ScenarioProfileService`, an LLM call
   with a deterministic fallback, same never-raise pattern as
   `ScenarioRecommender`), returning a fully-populated profile the frontend
   sends back as `custom_profile` alongside a non-preset `scenario` id (e.g.
   `"custom"`). `ops_manager_node` builds `scenario_profile` from that
   instead. `custom_profile` is a new `OrchestratorState` field, threaded
   through `make_initial_state`/`run_planning_scenario`/
   `stream_planning_scenario`, and bypasses both the semantic cache and the
   Redis plan cache (two different free-text descriptions would otherwise
   collide on the same cache key).

`ScenarioProfileService` always fills all three profile keys even in its
fallback path, since `complaint_service.py`/`inventory_service.py`/
`reservation_service.py` read them via direct dict-key access (not `.get()`)
once `scenario_profile` is truthy.

Frontend: the 4 preset tiles and the free-text input live side by side in
`PlanShiftModal.tsx` (`SCENARIO_OPTIONS`, previously duplicated verbatim in
`app/dashboard/page.tsx` and `TodayIdleState.tsx`, now a single shared
constant in `lib/scenarios.ts`).

---

## Information architecture history: Today and Planning

`/operations` (agent cards, forecast chart, critic banner) was first
merged directly into `/dashboard`'s success view: triggering a
plan and watching it build and complete happened in one continuous view.
A later pass split the two apart again into their current,
current-state form: `/dashboard` is now a daily overview page (KPIs,
health score, live-intelligence card, revenue and margin trends) and
`/planning` is the flagship trigger-and-watch experience (agent showcase,
live scenario composition, streaming pipeline run, what-if simulator).
`/operations`, `/runs`, `/runs/{id}`, and `/data-health` are all now thin
redirect stubs kept only so old bookmarks and links keep working; none of
them appear in `Sidebar.tsx`'s navigation.

`PlanShiftModal.tsx` carries a `TodayContextStrip`: condensed badges for
all four live signals (weather and holiday, industry
trends, regulatory alerts, plus the existing anonymised Swiggy area
occupancy signal), positioned above the scenario tiles and free-text
input so it is visible during scenario selection itself. Degrades
per-signal, same as its data sources.

---

## Guest Concierge

A no-auth, consumer-facing experience that plans a guest's dining or event occasion end-to-end, entirely independent of the restaurant-operator side described above: no shared session state, no restaurant data, no `org_id`, no user account.

**Service:** `ConciergeService` (`app/domain/services/concierge_service.py`) runs a Groq function-calling ReAct loop over 20 tools spanning Swiggy's Food, Instamart, and Dineout MCP servers directly, alongside session-management and budget-tracking tools. Session state (`ConciergeSession`) lives only in Redis, with a 2-hour TTL: occasion, headcount, budget, preferences, active bookings and orders, and the Instamart cart.

**API surface:** `POST /api/v1/concierge/chat` (SSE), `GET`/`DELETE /api/v1/concierge/session/{id}`, `POST /api/v1/concierge/transcribe` (voice input), `GET /api/v1/concierge/health`. None of these routes depend on `get_current_user`.

**Streaming protocol:** three chunk types stream over the same SSE connection: a `status` chunk describing which tool is in flight (rendered as a live "Finding venues..."-style indicator), a `tool_result` chunk with the structured data a tool call just returned (rendered as a real venue, slot, product, or order card, not narrated prose), and a `text` chunk streamed word by word for the model's narrated answer.

**Frontend:** `/concierge` is a standalone page. `Sidebar`, `TopBar`, and the operator `FloatingChatWidget` all gate on the current route in addition to auth state, so operator chrome never appears there, even for a logged-in operator previewing the flow. Session id persists in `localStorage`; a locally-stored (no-account) list of past sessions lets a guest resume or switch between plans.

**Honesty guarantees:** table booking and Instamart checkout are staging-gated (blocked on the same Swiggy staging credentials as the restaurant-operator side's `executor/`) and shown as a "pending" status rather than hidden or faked. Every tool failure and every unhandled exception degrades to one of a small set of fixed, friendly messages; a guest never sees a raw exception, stack trace, or internal tool name.

---

## Backend architecture

### API layer

The FastAPI application (`apps/api`) exposes routes under `/api/v1`, with the exception of `/replay` and `/metrics` which are mounted directly on the app at bare root paths. Routes are split across modules:

- `app/api/routes/auth.py`: register, login, `/auth/me`
- `app/api/routes/planning.py`: scenario listing, `/scenario-from-text`, `/compose-live-scenario`, `/run` (JSON), `/stream` (SSE), `/whatif`, `/recommend`, `/friday-rush` (legacy)
- `app/api/routes/market.py`: `/market/pulse`, `/market/ingredient-search`, `/market/trends`
- `app/api/routes/business.py`: `/business/performance` (financial scorecard)
- `app/api/routes/action_queue.py`: list, approve, reject Action Queue items
- `app/api/routes/runs.py`: audit run list, run detail, PDF export, Excel export, data-health, observability summary
- `app/api/routes/chat.py`: chat assistant SSE endpoint
- `app/api/routes/connectors.py`: Swiggy connector sync and status
- `app/api/routes/settings.py`: tenant org settings
- `app/api/routes/restaurant_profiles.py`: restaurant profile CRUD
- `app/api/routes/health.py`: liveness, dependency checks, Swiggy circuit breaker state
- `app/api/routes/replay.py`: Kindred single-generation replay endpoint, mounted outside `/api/v1`

Schemas (Pydantic request/response models) are in `app/api/schemas/`.

### Auth

JWT (HS256) authentication in `app/core/auth.py`. All planning, data, chat, and export routes are protected via `get_current_user`. Every planning run and chat session is stamped with `org_id` for tenant isolation.

Registration creates a user + org in one step. The `user_organizations` join table tracks membership and roles (owner / member).

### Orchestration layer

The planning pipeline is a LangGraph `StateGraph` in `app/orchestration/graph.py`, fifteen nodes total. Full per-node detail lives in `docs/AGENTS.md`; this is the structural summary:

```
ops_manager
    │
    ├── (error) → final_assembler → END
    │
    ▼
live_signals            ← fetches weather, holiday context, industry trends, compliance alerts once
    │
    ▼
demand_forecast          ← reads live_signals back from state; weather shifts the forecast number
    │
    ▼
qdrant_enrichment        ← retrieves past approved-run insights, injects past_plans into shared_context
    │
    ├───────────┬───────────────┬───────────┬──────────────────┐
    ▼           ▼               ▼           ▼                  ▼
reservation  complaint_    inventory   market_intel      dineout_manager
             intelligence
    └───────────┴───────────────┴───────────┴──────────────────┘
                            ▼
                    menu_intelligence   ← sequential after all 5; LangGraph fan-in fires exactly once
                            │
                            ▼
                        aggregator
                            │
                            ▼
                          critic
                            │
          ┌─────────────────┴──────────────────────┐
     (approved or                           (revision, replan_count < 2)
      replan_count ≥ 2)                            │
          ▼                                        ▼
   situation_summary                     replan_orchestrator ← injects critic feedback, max 2 cycles
          │                                        │
          ▼                              aggregator (loop)
    final_assembler
          │
         END
```

**Conditional routing:** after `ops_manager`, if `state["error"]` is set the graph skips to `final_assembler`. Otherwise it proceeds through `live_signals` and `demand_forecast`.

**Parallel execution:** five domain nodes (`reservation`, `complaint_intelligence`, `inventory`, `market_intel`, `dineout_manager`) fan out in parallel after `qdrant_enrichment`. `menu_intelligence` runs sequentially after all five complete, via LangGraph's native fan-in, so it can read inventory shortage data, reservation pressure, and live market signals before forming menu recommendations.

**Pipeline nodes added since the original nine-node graph:**

- `live_signals`: runs right after `ops_manager`, before `demand_forecast`. Fetches weather, Indian holiday context, industry trends, and regulatory alerts once per run and writes them to state, so `demand_forecast` and `market_intel` both read the same fetch instead of calling the same services twice.
- `market_intel`: merges the anonymised Swiggy competitor and occupancy signals with the three live-intelligence signals fetched by `live_signals` into one `market_intel_output["live_signals_text"]`, read by `menu_intelligence` and condensed for the critic.
- `dineout_manager`: analyses competitor Dineout slot and deal data (public data only, no named-restaurant output per the compliance remediation in `docs/DECISIONS.md`).
- `qdrant_enrichment`: runs after `demand_forecast`. Calls `PlanningMemoryService.retrieve()` to fetch the top-3 similar past approved-run insights from the `planning_memory` Qdrant collection, re-ranked with recency decay (`score × 2^(-age/14days)`), excluding runs older than 90 days. Injects `shared_context["past_plans"]`. Falls back to an empty list on any error: never blocks a run.
- `replan_orchestrator`: sits between `aggregator` and `critic`. If the critic returned a `revision` verdict in a prior cycle, this node injects the critic's structured feedback into `state["replan_context"]`. Enforces a maximum of 2 replan cycles: after that it passes through regardless of verdict to prevent infinite loops.
- `situation_summary`: sits between the critic-approved path and `final_assembler`, building a short narrative recap of the run for the final response.

**SSE streaming:** There are two distinct streaming mechanisms:

- `POST /api/v1/planning/stream`: the planning SSE endpoint. Emits **both `node_start` and `node_complete` events** per node. `node_start` includes a `hint` describing what the node is doing; `node_complete` includes a `hint` with the completion summary. The frontend loading screen uses these to drive a 4-state diagram (idle / running / done / skipped). A final `complete` event delivers the entire plan payload. `POST /api/v1/planning/run` is the non-streaming equivalent.
- `POST /api/v1/chat`: the chat SSE endpoint. Streams individual tokens word-by-word (`{"token": "..."}`), rendered progressively via ReactMarkdown. Completely separate from the planning SSE.

**Per-node tracing:** every node emits `node_start` / `node_end` structlog events with `duration_ms`, `llm_provider_used`, and `llm_fallback_used`. When LangSmith tracing is enabled (`LANGSMITH_TRACING=true`), each node also sends a trace span.

### Domain services

| Service | Responsibility |
|---------|----------------|
| `ForecastService` | Queries historical orders, runs Prophet time-series, applies weather/holiday adjustment, produces demand signal |
| `ReservationService` | Analyses booking density and occupancy risk |
| `ComplaintService` | Retrieves complaint patterns from Qdrant; RAG context feeds the LLM prompt |
| `MenuService` | Evaluates top and weak menu items; surfaces promotion guidance |
| `InventoryService` | Computes shortage and overstock alerts from stock vs threshold |
| `CriticService` | Validates the aggregated plan; scores across 5 dimensions |
| `ChatService` | Chat assistant: retrieves from Postgres runs and Feedback table, exposes Swiggy and Action Queue tools via function calling, streams via LLM factory |
| `RunService` | Persists planning runs to `planning_runs`; powers the runs and data-health API |
| `CostAwareScoringService` | Cost/benefit pressure score used by the critic |
| `EvaluationSanityChecker` | Automated sanity checks and cross-agent assumption diffing in critic evaluation |
| `PlanningMemoryService` | Stores approved run insights in Qdrant (`planning_memory`) with recency decay; retrieved by `qdrant_enrichment` to enrich planning context with similar past runs |
| `MarketIntelService` | Orchestrates the Swiggy competitor/occupancy enrichers concurrently and merges them with live-intelligence signals into `live_signals_text` |
| `ScenarioRecommender` | Suggests one of the four preset scenarios from run history, live market signals, calendar context, and inventory shortage count |
| `LiveScenarioComposer` | Composes a fresh, non-preset scenario profile from current live signals, rather than picking from the four fixed presets |
| `ScenarioProfileService` | Turns free-form scenario text into a full scenario profile via an LLM call, with a deterministic fallback |
| `DailyBriefingService` | Builds the condensed daily briefing content surfaced on the dashboard |
| `WorkflowTriggerService` | Coordinates triggering and tracking a planning run from the API layer |
| `ActionExecutionService` | Executes an approved Action Queue item (WhatsApp vendor message today; Instamart checkout once staging credentials land) |
| `TrustLadderService` | Counts consecutive approvals for an Action Queue category as an informational badge; does not change what requires approval |
| `VendorService` | Manages vendor and supplier records used by procurement actions |
| `ActionQueueService` | CRUD and status transitions for Action Queue items |
| `BusinessAnalyticsService` | Shared analytics (dish margin, complaint categories, peak hours, expense proration, composite health score) used identically by `business.py` and the planning pipeline |

### Redis caching

Redis serves two purposes in CareOps AI:

**Plan cache:** planning runs are cached by `(org_id, scenario, target_date)` key with a 1-hour TTL. **Only `approved` verdict plans are written to cache**: revision and rejected plans are not stored. On a cache hit, the full plan is returned immediately: zero LLM cost, zero pipeline execution. The response includes a `cache_hit: true` flag. Cache invalidation happens automatically on TTL expiry.

**Circuit breaker state:** per-Swiggy-endpoint failure counters (`circuit:fail:swiggy:{tag}`, 300s TTL) and open flags (`circuit:open:swiggy:{tag}`, 1800s TTL) are stored in Redis. These auto-expire so circuits reset without any manual intervention. `GET /health/circuits` reads these keys to return real-time state for all three Swiggy endpoints.

In addition, a **Qdrant-backed SemanticPlanCache** (`semantic_cache` collection, 0.92 cosine similarity, 1hr TTL) provides fuzzy plan retrieval for queries where an exact cache key match doesn't exist but a semantically similar approved plan does. The storage embedding is enriched with actual run conditions (demand_ratio, occupancy, shortages) at write time while the query embedding stays lightweight.

### Export layer

- **PDF**: `apps/api/app/infrastructure/pdf/report_generator.py` uses ReportLab to generate a structured chef brief with plan summary, agent outputs, critic verdict, dimension scores bar chart, and action items.
- **Excel**: `apps/api/app/infrastructure/excel/report_generator.py` uses openpyxl to produce a multi-sheet workbook: Summary, Inventory & Staffing (chef view), Cost Breakdown (owner view).

### RAG chatbot

`POST /api/v1/chat` accepts a message + conversation history and returns a streamed response via SSE.

- **Retrieval:** queries the last 10 `planning_runs` (org-scoped) and the last 30 `feedback` records (no org filter: shared demo dataset) to build a context window
- **LLM:** `_get_chat_client(settings)` factory: dispatches on `LLM_PROVIDER`. Routes to `AsyncGroq` (`llama-3.3-70b-versatile`) when `LLM_PROVIDER=groq`, or `AsyncOpenAI` against the CometAPI fast tier otherwise.
- **Within-session memory:** when `len(history) > 8`, older turns are compressed by `SessionMemoryService.build_summary_from_messages()` (no LLM call) and injected as a single `[Earlier in this session: ...]` assistant message. The last 8 turns are included verbatim so long conversations maintain continuity without blowing the token window.
- **Semantic cache:** `SemanticChatCache` (Qdrant collection `chat_semantic_cache`, 0.92 threshold, 24hr TTL) returns cached answers for semantically similar questions asked by the same org.
- **Frontend:** ReactMarkdown renders structured responses; multi-turn memory via message history in request body

### Infrastructure layer

| Module | Responsibility |
|--------|----------------|
| `db/models.py` | SQLAlchemy ORM: `users`, `organizations`, `user_organizations`, `restaurant_profiles`, `planning_runs`, `decision_logs`, `feedback`, `orders`, `reservations`, `inventory`, `menu_items` |
| `db/base.py` | SQLAlchemy `DeclarativeBase`: all ORM models inherit from this; Alembic reads `Base.metadata` |
| `api/dependencies.py` | `get_db()` session factory + FastAPI dependency provider for auth, LLM, memory, and orchestration |
| `llm/base.py` | `BaseLLMProvider` ABC: `complete()`, `complete_json()`, thread-safe usage tracking |
| `llm/factory.py` | `FallbackLLMProvider` + `create_llm_provider()`: reads `LLM_PROVIDER`, wires fallback |
| `llm/groq.py` | `GroqProvider`: groq SDK |
| `llm/gemini.py` | `GeminiProvider`: google-genai SDK |
| `llm/comet.py` | `CometProvider`: AsyncOpenAI SDK pointed at CometAPI (`api.cometapi.com/v1`); supports any of 500+ models via a single key |
| `llm/prompt_utils.py` | Centralised prompt builders for all agents: zero raw prompt strings in service files |
| `forecasting/` | Prophet-backed time-series forecaster |
| `vector/memory_service.py` | `MemoryService` and `EmbeddingService` for Qdrant retrieval with org payload filter |
| `vector/planning_memory.py` | `PlanningMemoryService`: approved run insights in Qdrant `planning_memory` with recency decay scoring |
| `cache/plan_cache.py` | Redis plan cache: `get_cached_plan` / `cache_plan` / `build_cache_key` by composite key |
| `cache/semantic_cache.py` | `SemanticPlanCache` (Qdrant-backed, approved-only, condition-enriched storage embedding) and `SemanticChatCache` (Q&A cache, 24hr TTL) |
| `swiggy/circuit_breaker.py` | Redis-backed circuit breaker: `is_open`, `record_failure`, `record_success`, `get_state` per provider + endpoint |
| `swiggy/provider_registry.py` | `ProviderRegistry`: capability-to-provider routing combining DB `sync_status` and live circuit breaker state |
| `observability/dependency_health.py` | PostgreSQL, Qdrant, Redis connectivity checks; `check_swiggy_circuits()` for circuit breaker health |
| `main.py` (OTel + Prometheus) | OpenTelemetry `ConsoleSpanExporter` and `prometheus_fastapi_instrumentator` wired directly in app startup |

### LLM provider abstraction

All agents depend on `BaseLLMProvider`, never on a concrete class. On any LLM exception the `FallbackLLMProvider` logs `llm_primary_failed_retrying_fallback` and transparently retries on the secondary provider. The provider used is surfaced in structlog output and in planning run metadata.

### Per-node model tier routing

When `LLM_PROVIDER=comet` and `COMET_TIERED=true`, the factory builds a tier-keyed `llm_registry` of `FallbackLLMProvider` instances and injects it into `OrchestratorState`. Each node reads its assigned tier from state and substitutes the tier provider for the default flat provider.

| Tier | Model | Assigned nodes | Fallback |
|------|-------|----------------|---------|
| `fast` | `deepseek-v4-flash` | demand_forecast, inventory, reservation | none |
| `balanced` | `gemini-3.5-flash` | complaint_intelligence, menu_intelligence | fast |
| `strong` | `claude-sonnet-4-6` | critic | balanced |

The lookup pattern used in every node is `(state.get("llm_registry") or {}).get("<tier>") or llm`: if the registry is absent (flat mode or Groq/Gemini), the injected default `llm` is used unchanged. Backward compatibility is total.

All tier provider usage is drained at the end of each run and merged into the `llm_usage` array, so cost tracking across models is accurate and per-model visible in every planning run's metadata.

`create_tiered_llm_providers()` in `factory.py` is the single construction point. Model names are fully configurable via `COMETAPI_MODEL_FAST`, `COMETAPI_MODEL_BALANCED`, and `COMETAPI_MODEL_STRONG` env vars: swapping models requires no code changes.

---

## Observability stack

| Tool | What it covers |
|------|----------------|
| **LangSmith** | Per-node traces when `LANGSMITH_API_KEY` set; `careops-golden-v1` dataset (50 runs); CI gate in `tests/unit/test_langsmith_evals.py` (local fixture, 90% pass rate) |
| **OpenTelemetry** | HTTP request tracing via `ConsoleSpanExporter` (swap for OTLP exporter in production) |
| **Prometheus** | `/metrics` scrape endpoint: request count, latency histograms, error rate |
| **Sentry** | Unhandled exception capture with FastAPI integration; `capture_exception` in LangGraph node wrappers; DSN-gated init |
| **structlog** | JSON log output across all nodes: `node`, `run_id`, `scenario`, `duration_ms`, `llm_provider_used` on every event |
| **LLM cost tracking** | `record_usage()` on every LLM call; aggregated `total_tokens`, `total_cost_usd` persisted in `planning_runs.metadata` |

---

## Multi-tenant isolation

Tenant isolation is enforced at three levels:

1. **PostgreSQL**: all run queries filter by `org_id` from the JWT; restaurant profiles and settings are org-scoped
2. **Qdrant**: complaint and SOP vectors use a payload filter `{"org_id": current_org_id}` on every retrieval call
3. **OrchestratorState**: `org_id` is carried in shared state so every node operates in the correct tenant context

---

## LangSmith regression evals

`scripts/build_golden_dataset.py` (root `scripts/` folder) builds the `careops-golden-v1` dataset from historical planning runs. The CI gate (`tests/unit/test_langsmith_evals.py`) runs evaluators against a local JSON fixture and requires a 90% pass rate to succeed.

---

## MCP server

`apps/api/mcp_server.py` is a stdio MCP server (Anthropic MCP SDK) exposing five tools:

| Tool | Description |
|------|-------------|
| `run_planning_scenario` | Triggers the full planning pipeline (see `docs/AGENTS.md` for current node topology) |
| `get_run_history` | Fetches recent planning runs with optional scenario/verdict filters |
| `get_market_brief` | Live market snapshot: category pricing, positioning, deals, area occupancy |
| `get_action_queue` | Lists pending (or other-status) Action Queue items |
| `approve_action` | Approves an action by ID: for a WhatsApp vendor order, this is the same step that sends the message |

All five call the CareOps AI API directly (`GET /market/pulse`, `GET /action-queue`, `POST /action-queue/{id}/approve`), so an owner can ask Claude Desktop about their restaurant and approve actions without opening the CareOps AI app at all: the same 3 capabilities are also exposed as in-app chatbot tools (`app/domain/services/chat_service.py`), sharing the same backend services (`ActionQueueService`, `action_execution_service.approve_and_execute`) so both surfaces behave identically.

Claude Code discovers the server automatically via `.mcp.json`. Claude Desktop uses `docs/mcp_claude_desktop_config.json`.

---

## LLM quality evaluations

| Suite | File | Metrics | Threshold |
|-------|------|---------|-----------|
| LangSmith regression | `tests/unit/test_langsmith_evals.py` | Pass rate against local fixture (`golden_runs.json`) | ≥ 90% |
| RAGAS | `evals/test_ragas_complaint.py` | Faithfulness, context precision on complaint RAG (answer_relevancy excluded: requires embeddings) | Faithfulness ≥ 0.8 |
| DeepEval | `evals/test_deepeval_quality.py` | HallucinationMetric on critic, AnswerRelevancyMetric on agents | Hallucination ≤ 0.5; Relevancy ≥ 0.7 |

---

## Frontend architecture

The frontend (`apps/web/careops-ui`) is a Next.js App Router application with JWT cookie auth.

### Pages

| Route | Purpose |
|-------|---------|
| `/` | Public homepage: two-sided platform overview, dual entry point (restaurant sign-in, guest sign-in) |
| `/login`, `/register` | Restaurant-operator JWT auth flow, shared split-screen layout |
| `/dashboard` | Daily overview: KPIs, health score, live-intelligence card, revenue and margin trends |
| `/planning` | Flagship trigger-and-watch experience: agent showcase, live scenario composition (presets, natural-language, and voice), SSE streaming pipeline run, what-if simulator |
| `/action-center` | Pending approvals and full Action Queue history |
| `/analytics` | Historical drill-down across menu performance, channels, peak hours, complaints |
| `/data` | Merged run history and data-health view: scenario filter, date range, critic score trend, run detail, PDF/Excel export |
| `/market` | Live Swiggy market intelligence, one card per capability, with trend charts; every card renders even when its signal is unavailable |
| `/chat` | Operator chat assistant: full page plus a floating widget available on every page, voice input |
| `/connectors` | Swiggy connector status and sync trigger |
| `/settings` | Workspace config: capacity, cuisine, peak hours, thresholds |
| `/restaurant-profiles` | Named restaurant profiles (owner only) |
| `/concierge` | No-auth Guest Concierge: consumer chat, real venue/food/supply cards, session history, voice input, no operator chrome |
| `/operations`, `/runs`, `/runs/{id}`, `/data-health` | Redirect stubs only, kept for backward-compatible links; not present in navigation |

### Key components

| Component | Purpose |
|-----------|---------|
| `Sidebar` | Primary app navigation: Dashboard, Planning, Action Center, Analytics, AI Assistant, plus owner-only Market, Data, Connectors, Restaurant Profiles, Settings |
| `TopBar` | Top app bar: page context, user controls |
| `HomeNav` | Public nav for the marketing homepage |
| `Footer` | Public marketing footer: Product / Resources / Company / Legal columns; homepage only |
| `ForecastChart` | Demand forecast bar/line chart with Recharts |
| `PlanShiftModal` | Scenario intake modal: preset tiles, free-text description, live-signals context strip |

### Streaming

The planning page uses `fetch` with a `ReadableStream` reader against `/api/v1/planning/stream`. Each `node_start`/`node_complete` event carries the node name and a hint: the pipeline diagram updates in real time. The full plan renders once the final `complete` event arrives.

The chat page streams against `/api/v1/chat`: individual tokens arrive word-by-word and render progressively via ReactMarkdown. A separate mechanism from the planning SSE.

---

## Data flow: planning run

1. User selects or describes a scenario and submits from the `/planning` page's trigger modal
2. Frontend opens an SSE connection to `POST /api/v1/planning/stream` with JWT
3. FastAPI resolves `get_current_user`, checks Redis cache: emits all node events instantly and returns on hit
4. On cache miss: loads org settings + restaurant profile, builds LangGraph graph, invokes it
5. Each node emits `node_start` (with hint) and `node_complete` (with completion hint) as it begins/finishes; loading screen diagram drives 4-state UI per node
6. `ops_manager` → `live_signals` → `demand_forecast` → `qdrant_enrichment` → [5 parallel nodes: reservation, complaint_intelligence, inventory, market_intel, dineout_manager] → `menu_intelligence` → `aggregator` → `critic` → [replan_orchestrator loop] → `final_assembler`
7. Final response includes plan, critic verdict, RAG context, cost metadata, and node traces
8. Run is persisted to `planning_runs`; result is stored in Redis cache

---

## Storage roles

| Store | Role |
|-------|------|
| **PostgreSQL** | All structured data: orders, reservations, feedback, inventory, menu_items, planning_runs, organizations, users, restaurant_profiles, connectors |
| **Qdrant** | `complaints_memory` and `sop_memory`: RAG retrieval, org-scoped payload filters |
| **Qdrant** | `planning_memory`: approved run insights with recency decay, used by `qdrant_enrichment` |
| **Qdrant** | `semantic_cache`: plan cache (0.92 cosine threshold, approved-only, 1hr TTL, condition-enriched storage embedding) |
| **Qdrant** | `chat_semantic_cache`: chatbot Q&A cache (0.92 threshold, 24hr TTL) |
| **Redis** | Plan cache: 1hr TTL by `(org_id, scenario, target_date)`; circuit breaker state per Swiggy endpoint |

---

## Cross-agent assumption diffing

Three domain nodes run in parallel (`reservation`, `complaint_intelligence`, `inventory`). `menu_intelligence` runs sequentially after all three via LangGraph fan-in. This means when the parallel nodes execute, they do so without knowledge of each other's results: but menu_intelligence does have access to all three outputs. However, a node can still make recommendations based on assumptions that are silently contradicted by another parallel node's findings.

To catch these contradictions automatically, each domain node writes an `assumptions` dict to shared state after its service call. The aggregator collects these into `bundle["assumptions"]`. When the critic node invokes `EvaluationSanityChecker.check_bundle()`, the checker diffs the assumptions cross-agent and returns a `stale_assumptions` list alongside the existing `issues` list.

**Diffs implemented (3 active):**

| Assumption | Checked against | Conflict |
|------------|-----------------|---------|
| `menu.assumed_covers_within_capacity = True` | `reservation.assumed_peak_occupancy_pct > 90` | Menu recommendations don't account for near-full-house throughput pressure |
| `reservation.assumed_peak_occupancy_pct > 85` | Forecast `confidence` or `confidence_band` indicating weak signal | High-occupancy planning on a weak forecast overstates certainty |
| `complaint.assumed_high_complaint_volume = False` | `complaint.assumed_negative_pct > 25` | Complaint node flagged volume as low but negative feedback is borderline elevated |

Note: `MenuService` self-queries `InventoryService` directly when `inventory_data=None`: both nodes use the same demand ratio and DB, so they always agree on shortage status regardless of execution order. See `docs/DECISIONS.md` for the full rationale behind this diffing approach.

The `stale_assumptions` list is injected into the critic's LLM prompt as a dedicated `## Cross-agent assumption conflicts` section. This gives the LLM concrete *why* reasoning about each inconsistency rather than requiring it to detect contradictions from raw data alone.

If a node errored and its `assumptions` dict is `None`, the checker gracefully skips diffing for that node.

---

## Architectural strengths

- Parallel fan-out across three domain agents (reservation, complaint, inventory) reduces pipeline latency; menu_intelligence runs sequentially after with access to their combined outputs, eliminating menu/inventory contradictions; AsyncOpenAI ensures the fan-out is truly concurrent, not serialised by event-loop blocking
- Per-node model tier routing: simple nodes get fast cheap models, the critic gets the strongest model; all via a single CometAPI key with no code changes to swap models
- SSE streaming makes every planning run feel interactive: results arrive node by node
- Redis cache eliminates repeat LLM cost for the same scenario on the same day
- Prompts centralized in `prompt_utils.py`: zero raw strings in service files
- RAG grounds complaint recommendations in real past guest issues, not generic LLM output
- Full tenant isolation at Postgres, Qdrant, and state levels
- LangSmith golden dataset + CI gate prevents quality regressions from shipping
- Sentry + OTel + Prometheus give three overlapping observability layers
- Cross-agent assumption diffing in `EvaluationSanityChecker` automatically surfaces contradictions between parallel nodes: scales to any number of agent pairs without enumerating every possible contradiction
- PlanningMemoryService provides long-term institutional memory: approved runs accumulate insight vectors in Qdrant; recency decay ensures recent context ranks higher without staling indefinitely
- Circuit breaker + provider registry give the Swiggy integration production-grade resilience: mid-day failures auto-route to fallback providers without operator intervention
- SemanticPlanCache (Qdrant-backed, approved-only) complements the Redis exact-match cache with fuzzy retrieval for scenarios with similar but not identical conditions

## Current limitations

- `executor/` (Instamart checkout, Dineout table booking) is still empty: blocked on Swiggy staging credentials, not a code gap, for both restaurant-side procurement and Guest Concierge
- RAGAS and DeepEval currently evaluate against static hand-written fixtures; candidate-refresh scripts exist (`scripts/build_ragas_dataset.py`, `scripts/build_deepeval_dataset.py`) but their output has not yet been promoted into the golden fixtures, so the eval suites do not yet reflect the live-signals and dynamic-scenario work shipped since they were written
- The autonomous procurement loop (weather/demand signal to ingredient shortage to real Instamart price check to Action Queue approval to real checkout or WhatsApp fallback) is not yet fully wired end-to-end
- Instamart event supplies are not yet exposed as a capability in the operator chat assistant
- Voice input (Whisper transcription) is live on the Dashboard, Planning, operator chat, and Guest Concierge; voice output (TTS) is not built
- `packages/core` shared contract package is empty

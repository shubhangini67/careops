# CareOps AI Implementation Plan

Phases 0 through 5 complete. Phase 6A in progress, including Guest Concierge. Task-level status lives in the project's Excel progress tracker and in `CLAUDE.md`; this document tracks phase-level delivery.

---

## Delivered: Phases 0–5

### Phase 0: Design
- Architecture, PRD, system design, data model, API contracts, evaluation rubric

### Phase 1: Core system
- Docker Compose stack (PostgreSQL, Qdrant, Redis)
- FastAPI backend with health, planning, runs, and data-health endpoints
- SQLAlchemy ORM models and Alembic migrations
- Seed scripts for demo data and Qdrant memory
- LangGraph nine-node orchestration graph with parallel fan-out
- All domain services (Forecast, Reservation, Complaint, Menu, Inventory, Critic)
- Frontend dashboard, runs page, and data-health page

### Phase 2: Intelligence
- Prophet time-series demand forecasting with peak detection
- Inventory shortage/overstock alerts
- Menu intelligence with promotion strategy
- Dashboard with scenario framing, agent output cards, critic verdict banner

### Phase 3: Multi-scenario
- Shared scenario runner (four presets)
- Persisted planning runs with full audit inspection
- CriticService with cost-aware scoring and revision feedback
- Runs page with full audit trail

### Phase 4: Productisation
- Multi-tenant JWT auth (users, orgs, org-scoped sessions)
- LangSmith per-node tracing
- Real health checks for all dependencies
- structlog JSON logging across all nodes
- LLM cost tracking per call and per run
- Settings and restaurant profiles UI + API
- LLM provider abstraction with Groq↔Gemini auto-fallback
- RAGAS + DeepEval quality evals
- MCP server for Claude Code / Claude Desktop

### Phase 5: Export, UX, Observability & Intelligence
- PDF export (ReportLab chef brief)
- Excel export (openpyxl multi-sheet owner workbook)
- Design polish: ember accent palette, Instrument Serif display font
- Frontend UX fixes: profile selector, validation, cost aggregates
- Redis plan caching: 1hr TTL, `cache_hit` flag
- SSE streaming: `node_complete` status events drive the loading screen pipeline diagram; full plan delivered in single `complete` event via `/planning/stream`
- What-if simulator: cover count slider, instant score update
- OpenTelemetry + Prometheus: `/metrics` scrape endpoint
- Sentry error capture with LangGraph node tags
- LangSmith regression evals: `careops-golden-v1` (50 runs), 90% CI gate
- Multi-tenant workspace isolation: Postgres `org_id` scoping + Qdrant payload filter
- RAG chatbot: `POST /api/v1/chat` SSE, AsyncGroq, ReactMarkdown
- Prelaunch polish: homepage redesign, professional footer, prompt_utils centralisation

### Post Phase 5: Architectural improvements

- Per-node model tier routing: `COMET_TIERED` activates `llm_registry` in state; critic gets strong tier, domain nodes get fast/balanced
- Cross-agent assumption diffing: each domain node writes assumptions dict to state; `EvaluationSanityChecker` cross-diffs post fan-out; `stale_assumptions` in critic prompt and response

---

## Current state

Phases 0 through 5 are complete. Phase 6A (Swiggy MCP integration, live intelligence signals, a real-product frontend information architecture, and Guest Concierge) is in progress.

Outstanding known gaps:
- `executor/` (Instamart checkout, Dineout table booking) is implemented but blocked on Swiggy staging credentials, for both restaurant-side procurement and Guest Concierge
- `packages/core` is empty: shared types between frontend and backend are not yet extracted
- RAGAS and DeepEval currently evaluate against static hand-written fixtures; candidate-refresh scripts exist but their output has not yet been promoted into the golden fixtures
- Voice output (TTS) is not built; voice input (Whisper transcription) is live everywhere it's wired in

---

## Phase 6A: Swiggy MCP integration, live signals, IA redesign, and Guest Concierge

### Delivered

**Foundation and connector layer:**
- `BaseConnector` ABC (`sync()` and `enrich()` pattern), shared across all connector types
- `SwiggyMCPClient`: JSON-RPC 2.0 to all three Swiggy MCP servers, with circuit breaker and tool tracing
- `connectors` table and `ConnectorRepository` for per-org token storage and sync status
- Async job queue for planning runs
- Nightly sync services for orders, feedback, and reservation status (personal-account-scoped data, used only as chatbot context, not restaurant data)

**Market intelligence and compliance:**
- `CompetitorEnricher`, `OccupancyEnricher`, `ProcurementEnricher`, and `MarketIntelService`, orchestrating Swiggy enrichment concurrently
- `market_intel` and `dineout_manager` graph nodes
- Removal of the competing-platform (Zomato) stub connector for Integration Agreement exclusivity compliance
- Anonymisation of all market intelligence output to area-level aggregates, no named competitor restaurants, prices, or deals, for competitive-intelligence compliance

**Live intelligence signals (independent of Swiggy):**
- `WeatherService` (Open-Meteo) and Indian holiday context, applying a real deterministic multiplier to the Prophet forecast
- `TrendsService`: curated Indian food and beverage industry RSS digest
- `ComplianceAlertsService`: FSSAI public regulatory notices
- A `live_signals` graph node fetching all three once per run, unified with Swiggy area signals inside `market_intel`
- Market Intelligence page: weather/trends/compliance cards always render, showing an honest "unavailable" state rather than vanishing when a signal fails; real `console.error` logging on every fetch/refresh failure

**Scenario intake:**
- `ScenarioProfileService`: free-text scenario description to a full scenario profile via an LLM call, with a deterministic fallback
- `LiveScenarioComposer`: composes a scenario profile from current live signals rather than picking from the four fixed presets
- `ScenarioRecommender`: suggests a preset from run history, market signals, and calendar context

**Action Queue and financial scorecard:**
- `ActionQueueService`, `ActionExecutionService`, `TrustLadderService`, `VendorService`, backing an approve/reject flow with an informational trust-ladder badge; `TrustLadderService` deliberately never auto-promotes a category to skip approval, by design
- Per-org expense ledger with cost proration, real net profit and net margin, and a composite health score

**Observability:**
- `PlanningMemoryService` (Qdrant long-term memory with recency decay), `SemanticPlanCache`, `SemanticChatCache`
- Graph expanded to fifteen nodes total: `live_signals`, `qdrant_enrichment`, `market_intel`, `dineout_manager`, `replan_orchestrator`, `situation_summary` added since the original nine-node graph
- Langfuse tracing on every planning run (per-node spans, per-generation LLM traces) and a Kindred replay endpoint for single-generation prompt replay debugging

**Frontend:**
- Information architecture redesign: `/dashboard` (daily overview) and `/planning` (flagship trigger-and-watch experience) split into separate pages
- `/action-center`, `/analytics`, and a merged `/data` page (replacing separate `/runs` and `/data-health` pages, with backward-compatible redirect stubs)
- Market intelligence panel, connector status page, restaurant profiles, and settings pages
- Homepage redesigned around the two-sided platform (dual entry: restaurant sign-in, guest sign-in); `/login`/`/register` redesigned on a shared split-screen layout
- Voice input (Whisper transcription via Groq) added to the Dashboard ask-bar, Planning modal, operator chat page, and floating widget
- Fixed a class of SSR hydration mismatches: four components/hooks (`SwiggyLiveMarketPanel`, `TodayIdleState`, `usePlanTriggerData`, `useScenarioRecommendation`) read `localStorage` inside a `useState` lazy initializer, which disagreed with the server's render and forced React to discard and regenerate the tree on every load; the cache read now happens inside the existing effect instead

**Guest Concierge (originally scoped as a separate Phase 6B):**
- `ConciergeService`: Groq function-calling ReAct loop over 20 tools across Swiggy Food, Instamart, and Dineout MCP servers, Redis-backed session state (2-hour TTL), no restaurant-operator data or auth
- No-auth `/concierge` API routes (chat, session, transcribe, health) and a consumer-facing `/concierge` frontend page; operator chrome (Sidebar/TopBar/FloatingChatWidget) never leaks onto it, even for a logged-in operator previewing the flow
- Real venue, slot, product, and order cards rendered from structured tool results, not narrated as prose; a friendly "doing X..." status indicator while a tool call is in flight
- Locality-aware Dineout venue search (Swiggy's own geocoding via `entityType="locality"`), replacing a fixed default location
- Proactive Instamart supply suggestions for birthday/party occasions
- Local (no-account) previous-plans history, voice input, light/dark theme toggle, logout affordance for an operator previewing the flow
- Staging-gated actions (table booking, Instamart checkout) shown honestly as "pending", never hidden or faked
- Hard rule enforced end to end: no raw exception, log, or internal tool name ever reaches a guest; every failure degrades to a fixed, friendly message

### Upcoming

- Autonomous procurement loop wired fully end-to-end: weather or demand signal to ingredient shortage to real Instamart price check to Action Queue approval to real checkout or WhatsApp fallback, currently blocked on Swiggy staging credentials for the checkout step
- Guest Concierge table booking and Instamart checkout execution, blocked on the same staging credentials
- Instamart event supplies exposed as a capability in the operator chat assistant
- Voice output (TTS response), for both the operator chat and Guest Concierge
- Promotion of RAGAS and DeepEval candidate datasets into the golden eval fixtures

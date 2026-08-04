# CareOps AI Roadmap

Phase 5 complete. Phase 6A in progress, including Guest Concierge.

---

## Completed

### Phase 0: Design
- Architecture, PRD, system design, data model, API contracts, evaluation rubric

### Phase 1: Core system
- Local Docker Compose stack for PostgreSQL, Qdrant, and Redis
- FastAPI application with health, planning, runs, and data-health endpoints
- SQLAlchemy ORM models and Alembic migrations
- Seed scripts for demo data and Qdrant memory
- LangGraph nine-node orchestration graph with parallel fan-out
- ForecastService, ReservationService, ComplaintService, MenuService, InventoryService
- CriticService with five-dimension scoring
- Frontend dashboard, runs page, and data-health page

### Phase 2: Intelligence
- Prophet time-series demand forecasting with peak detection
- Inventory shortage/overstock alerts with feasibility-aware planning
- Menu intelligence with promotion strategy
- Dashboard enhancement: scenario framing, agent output cards, critic verdict banner

### Phase 3: Multi-scenario
- Shared scenario runner supporting four scenario presets
- Persisted planning runs with full audit inspection
- CriticService with cost-aware scoring, sanity checks, and revision feedback
- Runs page with full audit trail

### Phase 4: Productisation
- Multi-tenant auth: users, orgs, JWT (HS256), protected routes, login/register UI
- LangSmith tracing: `LANGSMITH_TRACING` enabled, per-node traces
- Real health checks: live PostgreSQL, Qdrant, Redis connectivity pings
- Structured logging: structlog JSON output across all orchestration nodes
- LLM cost tracking: `prompt_tokens`, `completion_tokens`, `cost_usd` per call; aggregated in run metadata
- Admin + settings UI: tenant config (capacity, peak hours, thresholds)
- Runs UI: scenario filter, date range picker, critic score trend chart, diff modal
- Configurable restaurant profiles: CRUD API, profile injected into planning prompts
- LLM provider abstraction: `BaseLLMProvider` ABC, `FallbackLLMProvider`, Groq↔Gemini auto-fallback
- RAGAS evals: faithfulness (≥ 0.8) and context precision on complaint RAG pipeline
- DeepEval quality tests: HallucinationMetric on critic output, AnswerRelevancyMetric on agent outputs
- MCP server: `run_planning_scenario` + `get_run_history` via Anthropic MCP SDK; Claude Code + Desktop

### Phase 5: Export, UX, Observability & Intelligence
- PDF export: ReportLab chef brief with plan summary, agent outputs, critic verdict, dimension scores, action items
- Excel export: role-aware `.xlsx`; Inventory & Staffing sheet (chef view), Cost Breakdown sheet (owner view), openpyxl
- Design polish: unified dark theme, ember accent palette, Instrument Serif display font, card hover elevation
- Frontend UX fixes: restaurant profile selector on dashboard, input validation, cost/token aggregate on runs list, back navigation
- Redis caching: 1hr TTL plan cache by scenario + date; `cache_hit` flag in response; zero LLM cost on hits
- SSE streaming: `POST /api/v1/planning/stream` emits `node_complete` status events (node name only) as each LangGraph node finishes; loading screen pipeline diagram updates in real time; full plan delivered in single `complete` event
- What-if simulator: cover count slider; cost pressure, benefit, and tradeoff scores update instantly without a full re-run
- OpenTelemetry + Prometheus: OTel HTTP tracing on every request; `/metrics` Prometheus scrape endpoint; observability summary API and frontend panel
- Sentry error tracking: `sentry-sdk` FastApiIntegration; DSN-gated init; `capture_exception` in LangGraph nodes; `/debug/sentry-test` smoke test
- LangSmith regression evals: `build_golden_dataset.py` builds `careops-golden-v1` (50 runs); CI gate pytest with 90% pass rate threshold
- Multi-tenant workspace isolation: PostgreSQL `org_id` scoping on all run queries; Qdrant payload filter per org on complaint/SOP vectors; `org_id` in `OrchestratorState`; branded loading screen (Instrument Serif italic)
- RAG chatbot: `POST /api/v1/chat` SSE endpoint; AsyncGroq llama-3.3-70b streaming; RAG from Postgres runs + Feedback table; ReactMarkdown frontend; Ask AI in NavBar
- Prelaunch polish: homepage pipeline redesign with glowing connectors, plain-language copy; professional Footer; NavBar/dashboard/ForecastChart polish; prompt refinements across all services

### Post Phase 5: Architectural improvements

- **Per-node model tier routing**: `COMET_TIERED=true` activates tier-keyed `llm_registry` in `OrchestratorState`; each parallel node reads its assigned tier at runtime; critic always gets the strong tier
- **Cross-agent assumption diffing**: each domain node writes its assumptions to state after its service call; `EvaluationSanityChecker` cross-diffs them post fan-out; `stale_assumptions` injected into critic prompt and returned in `critic.stale_assumptions` in the API response

---

## Known gaps

- `executor/` (Instamart checkout, Dineout table booking) is implemented but blocked on Swiggy staging credentials, both for restaurant-side procurement and Guest Concierge
- `packages/core` is empty; types are not yet shared between frontend and backend
- RAGAS and DeepEval currently evaluate against static hand-written fixtures; candidate-refresh scripts exist but their output has not yet been promoted into the golden fixtures
- `test_langgraph_flow.py` references a removed module and is excluded from the test run
- `test_llm_provider.py` (Gemini integration test) fails on free-tier rate limits; environment-dependent
- Voice interface has transcription (Whisper via Groq) live everywhere it's wired in, but no TTS response yet

---

## Phase 6A: in progress (Swiggy MCP integration, live signals, IA redesign, Guest Concierge)

Phase 6A integrates Swiggy's MCP servers (Food, Instamart, Dineout) to replace synthetic market data with live platform signals, adds intelligence signals independent of Swiggy (weather, industry trends, regulatory alerts), redesigns the frontend information architecture around a real product shape, and delivers Guest Concierge as a second, independent product surface.

### Completed

- BaseConnector ABC (`sync()` and `enrich()` pattern) and `SwiggyMCPClient` (JSON-RPC 2.0, graceful degradation, circuit breaker, tool tracing)
- `connectors` table, `ConnectorRepository`, async job queue, nightly sync services (orders, feedback, reservation status)
- `CompetitorEnricher`, `OccupancyEnricher`, `ProcurementEnricher`, `MarketIntelService`, and the `market_intel` and `dineout_manager` graph nodes
- Compliance remediation: removal of the competing-platform (Zomato) stub connector for exclusivity; anonymisation of all market intelligence output to area-level aggregates for the competitive-intelligence clause
- `PlanningMemoryService` (Qdrant long-term memory, recency decay), `SemanticPlanCache`, `SemanticChatCache`
- Live intelligence signals independent of Swiggy: `WeatherService` (Open-Meteo, real forecast-adjusting multiplier), `TrendsService` (curated RSS digest), `ComplianceAlertsService` (FSSAI public notices), unified via the `live_signals` node and `market_intel`
- Scenario intake overhaul: natural-language scenario text (`ScenarioProfileService`), live dynamic composition (`LiveScenarioComposer`, `GET /planning/compose-live-scenario`), alongside the four existing presets
- Action Queue with an informational trust-ladder badge (consecutive-approval streak counter, never auto-promotes); financial scorecard with a per-org expense ledger, real net profit and net margin, and a composite health score
- Langfuse tracing on every planning run and a Kindred replay endpoint for single-generation prompt replay debugging
- Graph expanded to fifteen nodes total (`live_signals`, `qdrant_enrichment`, `market_intel`, `dineout_manager`, `replan_orchestrator`, `situation_summary` added since the original nine-node graph)
- Frontend information architecture redesign: `/dashboard` and `/planning` split into separate pages, `/action-center`, `/analytics`, and a merged `/data` page replacing separate `/runs` and `/data-health` pages, with backward-compatible redirect stubs
- Voice input (Whisper transcription via Groq) added to the Dashboard ask-bar, Planning modal, operator chat page, and floating widget
- Homepage redesigned around the two-sided platform, with a dual entry point (restaurant sign-in, guest sign-in); `/login`/`/register` redesigned on a shared split-screen layout
- Market Intelligence page: weather, industry trends, and regulatory alerts cards always render, with an honest "unavailable" state instead of disappearing when a signal is missing; fixed a class of SSR hydration mismatches caused by reading `localStorage` in `useState` lazy initializers across four components/hooks
- **Guest Concierge**: `ConciergeService` (Groq function-calling ReAct loop over 20 Swiggy Food/Instamart/Dineout tools, Redis-backed sessions), no-auth `/concierge` API routes and frontend page, real venue/slot/product/order cards, proactive Instamart supply suggestions, local previous-plans history, voice input, staging-gated actions shown honestly as pending, and a hard no-raw-error rule for every guest-facing failure

### Upcoming

- Autonomous procurement loop wired fully end-to-end (shortage detection through real Instamart checkout), blocked on Swiggy staging credentials for the checkout step
- Guest Concierge table booking and Instamart checkout execution, blocked on the same staging credentials
- Instamart event supplies exposed as a capability in the operator chat assistant
- Voice output (TTS response), for both the operator chat and Guest Concierge
- Promotion of RAGAS and DeepEval candidate datasets into the golden eval fixtures

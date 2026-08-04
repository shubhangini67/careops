# CareOps AI API

FastAPI backend for CareOps AI. Owns the orchestration entrypoints, domain services, DB models, run persistence, exports, chat, observability, and eval suites.

Phase 6A in progress.

---

## Backend scope

- Multi-tenant JWT authentication (register, login, org-scoped sessions)
- Fifteen-node LangGraph planning pipeline with SSE streaming (see `docs/AGENTS.md`)
- Redis plan caching: 1hr TTL, zero LLM cost on cache hits
- PDF export (ReportLab chef brief) and Excel export (openpyxl, multi-sheet workbook)
- Chat assistant (`/chat`): SSE streaming over Postgres run history and feedback, plus Swiggy market and Action Queue tools via function calling
- Observability: OpenTelemetry HTTP tracing, Prometheus `/metrics`, Sentry exception capture, Langfuse tracing with a Kindred replay endpoint
- LangSmith per-node traces and the `careops-golden-v1` golden dataset (50 runs) with a 90% CI gate
- RAGAS and DeepEval quality evals on complaint RAG and critic output
- Data-health and observability summary endpoints, merged into the frontend's `/data` page
- MCP server (`mcp_server.py`) for Claude Code / Claude Desktop integration

### Swiggy integration and live intelligence

- `SwiggyMCPClient`: JSON-RPC 2.0 client to Swiggy Food, Instamart, and Dineout MCP servers
- `BaseConnector` ABC (`infrastructure/base_connector.py`): `sync()` and `enrich()` pattern for all external platform connectors
- Circuit breaker: Redis-backed, per-endpoint; 5 or more failures within a 5-minute window opens a 10-minute circuit; `GET /api/v1/health/circuits`
- Provider registry: `get_provider_async()` combines DB connector status and live circuit state
- Market intelligence output is anonymised to area-level aggregates: no named competitor restaurants, prices, or deals (compliance with the signed Swiggy Integration Agreement)
- Live intelligence signals independent of Swiggy: weather and holidays (Open-Meteo), industry trends (curated RSS), regulatory alerts (FSSAI public notices), all merged into the planning pipeline
- `PlanningMemoryService`: Qdrant long-term memory of approved runs with recency decay (half-life 14 days)
- `SemanticPlanCache`: Qdrant-backed, approved-only, condition-enriched asymmetric embedding
- `SemanticChatCache`: chat assistant Q&A cache (0.92 cosine, 24hr TTL)
- Action Queue with an informational trust-ladder badge (consecutive-approval streak, not an auto-execution mechanic); financial scorecard with real net profit, net margin, and a composite health score

---

## Guest Concierge

`ConciergeService` (`domain/services/concierge_service.py`) is a second, independent agent alongside the restaurant-operator pipeline above: a no-auth, ReAct tool-calling loop that plans a guest's occasion end to end over Swiggy's Food, Instamart, and Dineout MCP servers.

- No auth, no organization data, no database persistence: session state lives in Redis for two hours (`ConciergeSession`), keyed by `session_id`, and nowhere else
- A Groq function-calling loop over roughly twenty tools spanning venue search and booking (Dineout), food ordering (Food, COD only, capped at Rs.1000 per order in Builders Club v1), and event supplies (Instamart)
- Voice input via `POST /concierge/transcribe`, reusing the same Whisper transcription used on the restaurant-operator side
- Streams friendly status updates ("finding venues...") rather than raw tool output or exception text to the guest
- Table booking (`book_table`) and Instamart checkout (`checkout`) are implemented and blocked on Swiggy staging credentials; both are surfaced to the guest as pending, never faked as complete

Routes live in `api/routes/concierge.py`: `POST /concierge/chat` (SSE), `GET`/`DELETE /concierge/session/{id}`, `POST /concierge/transcribe`, `GET /concierge/health`.

---

## Route surface

Full detail for every endpoint lives in `docs/APIS.md`. Summary:

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/auth/register` | Public | Register user + org |
| `POST` | `/api/v1/auth/login` | Public | JWT access token |
| `GET` | `/api/v1/auth/me` | JWT | Current user profile |
| `GET` | `/api/v1/health` | Public | Liveness |
| `GET` | `/api/v1/health/dependencies` | Public | PostgreSQL / Qdrant / Redis |
| `GET` | `/api/v1/health/circuits` | Public | Swiggy circuit breaker state (open/closed, failures, TTL) |
| `GET` | `/api/v1/planning/scenarios` | Public | Scenario presets |
| `POST` | `/api/v1/planning/scenario-from-text` | JWT | Free-text scenario to a full profile |
| `GET` | `/api/v1/planning/compose-live-scenario` | JWT | Dynamic scenario composed from current live signals |
| `POST` | `/api/v1/planning/run` | JWT | Execute pipeline (full JSON response) |
| `POST` | `/api/v1/planning/stream` | JWT | Execute pipeline (SSE: node_start, node_complete, complete events) |
| `POST` | `/api/v1/planning/whatif` | JWT | What-if simulator (no LLM, deterministic) |
| `GET` | `/api/v1/planning/recommend` | JWT | Suggests a preset from history, market signals, and calendar |
| `POST` | `/api/v1/planning/friday-rush` | JWT | Legacy alias, kept for backward compatibility |
| `GET` | `/api/v1/market/pulse` | JWT | Live market signals: area intel, weather, trends, compliance |
| `GET` | `/api/v1/market/ingredient-search` | JWT | On-demand Instamart ingredient search |
| `GET` | `/api/v1/market/trends` | JWT | Per-dish price and occupancy history across past runs |
| `GET` | `/api/v1/business/performance` | JWT | Financial scorecard: net profit, net margin, health score |
| `GET` | `/api/v1/business/summary` | JWT | AI-generated daily executive summary |
| `GET/POST` | `/api/v1/action-queue` | JWT | List and act on Action Queue items |
| `GET` | `/api/v1/runs` | JWT | List runs (org-scoped) |
| `GET` | `/api/v1/runs/{id}` | JWT | Run detail |
| `GET` | `/api/v1/runs/{id}/export` | JWT | PDF chef brief |
| `GET` | `/api/v1/runs/{id}/export/excel` | JWT | Excel workbook |
| `POST` | `/api/v1/chat` | JWT | Chat assistant (SSE stream) |
| `GET` | `/api/v1/observability/summary` | JWT | 7-day planning stats |
| `GET` | `/api/v1/data-health` | JWT | Database coverage |
| `POST` | `/api/v1/connectors/swiggy/sync` | JWT | Trigger Swiggy connector sync |
| `GET` | `/api/v1/connectors/status` | JWT | Connector sync status |
| `GET/PATCH` | `/api/v1/settings` | JWT | Org workspace settings |
| `GET/POST` | `/api/v1/restaurant-profiles` | JWT | List / create profiles |
| `GET/PATCH/DELETE` | `/api/v1/restaurant-profiles/{id}` | JWT | Get / update / delete profile |
| `POST` | `/replay` | Kindred metadata | Kindred single-generation prompt replay (not under `/api/v1`) |
| `GET` | `/metrics` | Public | Prometheus scrape |
| `GET` | `/debug/sentry-test` | Public | Sentry smoke test (not under `/api/v1`) |
| `POST` | `/api/v1/concierge/chat` | Public | Guest Concierge chat turn (SSE) |
| `GET/DELETE` | `/api/v1/concierge/session/{id}` | Public | Get or clear a concierge session |
| `POST` | `/api/v1/concierge/transcribe` | Public | Guest Concierge voice transcription |
| `GET` | `/api/v1/concierge/health` | Public | Concierge tool availability |

---

## Scenario intake

Four presets, natural-language free text, or live dynamic composition, all converging on the same `scenario_profile` the pipeline reads. Full detail in `docs/PRODUCT_MODES.md`.

| Id | Label | Service window |
|----|-------|----------------|
| `friday_rush` | Friday Rush | 18:00 to 22:00 |
| `weekday_lunch` | Weekday Lunch | 12:00 to 15:00 |
| `holiday_spike` | Holiday Spike | 17:00 to 22:00 |
| `low_stock_weekend` | Low-Stock Weekend | 18:00 to 22:00 |

---

## Local run

```bash
cd apps/api
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
python ..\..\scripts\seed_demo_data.py
python ..\..\scripts\seed_qdrant_memory.py

uvicorn app.main:app --reload
```

API at `http://localhost:8000` · Swagger at `http://localhost:8000/docs`

---

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `local` | Environment tag |
| `POSTGRES_URL` |  | PostgreSQL connection string |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `REDIS_URL` | `redis://localhost:6379` | Redis endpoint |
| `LLM_PROVIDER` | `groq` | Primary LLM: `groq`, `gemini`, or `comet` |
| `GROQ_API_KEY` |  | Required for planning and chat |
| `GEMINI_API_KEY` |  | Optional fallback |
| `JWT_SECRET_KEY` |  | HS256 signing key |
| `LANGSMITH_TRACING` | `false` | Enable LangSmith per-node traces |
| `LANGSMITH_API_KEY` |  | LangSmith API key |
| `SENTRY_DSN` |  | Sentry DSN: init is skipped if unset |
| `COMETAPI_KEY` |  | CometAPI key: enables 500+ models via OpenAI-compat endpoint |
| `COMETAPI_MODEL_FAST` | `deepseek-v4-flash` | Fast tier model (demand forecast, reservation, inventory) |
| `COMETAPI_MODEL_BALANCED` | `gemini-3.5-flash` | Balanced tier (complaint intelligence, menu) |
| `COMETAPI_MODEL_STRONG` | `claude-sonnet-4-6` | Strong tier (aggregator, critic) |
| `COMET_TIERED` | `false` | Enable per-node model tier routing (CometAPI only) |
| `SWIGGY_ACCESS_TOKEN` |  | Dev-only Swiggy OAuth token (prod uses `connectors` table) |
| `SWIGGY_ADDRESS_ID` |  | Dev-only Swiggy address ID for sync |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` |  | Enables Langfuse tracing; fail-open when unset |
| `LANGFUSE_HOST` / `LANGFUSE_BASE_URL` |  | Langfuse ingestion endpoint (both names supported) |
| `KINDRED_AGENT_ID` / `KINDRED_API_KEY` |  | Registered for the Kindred replay integration |

---

## Domain services

Full list and one-line purpose for all domain services lives in `docs/ARCHITECTURE.md`. The core planning-pipeline set:

| Service | File | Responsibility |
|---------|------|----------------|
| `ForecastService` | `services/forecast_service.py` | Prophet time-series demand forecasting, weather and holiday adjusted |
| `ReservationService` | `services/reservation_service.py` | Booking density and occupancy risk |
| `ComplaintService` | `services/complaint_service.py` | Qdrant RAG over guest feedback |
| `MenuService` | `services/menu_service.py` | Menu performance and promotion strategy |
| `InventoryService` | `services/inventory_service.py` | Shortage and overstock alerts |
| `MarketIntelService` | `services/market_intel_service.py` | Orchestrates Swiggy area signals and merges them with live intelligence signals |
| `CriticService` | `services/critic_service.py` | 5-dimension plan scoring and verdict |
| `ChatService` | `services/chat_service.py` | Chat assistant: SSE streaming, Swiggy and Action Queue tool calling |
| `RunService` | `services/run_service.py` | Planning run persistence and retrieval |
| `ActionQueueService` | `services/action_queue_service.py` | Action Queue CRUD and status transitions |
| `BusinessAnalyticsService` | `services/business_analytics_service.py` | Financial scorecard: expense proration, net profit, health score |
| `EvaluationSanityChecker` | `services/evaluation_sanity.py` | Automated sanity checks and cross-agent assumption diffing; produces `stale_assumptions` for the critic prompt |

---

## Tests

```bash
# Unit + integration
pytest tests/unit -q
pytest tests/integration -q --ignore=tests/integration/test_langgraph_flow.py

# LangSmith regression evals (requires LANGSMITH_API_KEY + GROQ_API_KEY)
python ../../scripts/build_golden_dataset.py
pytest tests/unit/test_langsmith_evals.py -v

# RAGAS + DeepEval quality evals
pytest evals/test_ragas_complaint.py -v -W ignore::DeprecationWarning
pytest evals/test_deepeval_quality.py -v -W ignore::DeprecationWarning
```

---

## MCP server

```bash
python mcp_server.py
```

Exposes five tools: `run_planning_scenario`, `get_run_history`, `get_market_brief`, `get_action_queue`, `approve_action`. Auto-discovered via `.mcp.json` in the project root. Claude Desktop uses `docs/mcp_claude_desktop_config.json`. Set `CAREOPS_EMAIL` and `CAREOPS_PASSWORD` in `.mcp.json` to a registered user.

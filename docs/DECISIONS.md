# Architecture and Product Decisions
# CareOps AI

Phase 6A in progress.

---

## Decision Log Format
Each entry records a meaningful architecture, product, or workflow decision.

---

## CareOps AI will be built as a multi-agent decision system, not a chatbot
**Status:** Accepted

### Context
The project aims to stand out as a capstone and prototype. A simple chatbot or basic RAG assistant would not adequately demonstrate system design depth.

### Decision
The product will be positioned and implemented as an AI-powered restaurant operations intelligence platform using multiple specialised agents coordinated by LangGraph.

### Consequences
- Stronger architecture complexity and clearer separation of responsibilities
- Higher implementation complexity, controlled phase by phase

---

## The flagship demo scenario will be Friday Night Rush Optimization
**Status:** Accepted

### Context
The project needs a clear demo story rather than a broad and vague collection of features.

### Decision
The primary use case for design and implementation will be optimising Friday evening operations for a pizza-heavy restaurant. Three additional scenarios (weekday lunch, holiday spike, low-stock weekend) extend the same pipeline.

### Consequences
- Focused development and demo clarity
- All features serve the central scenario logic

---

## The system will use a hybrid architecture
**Status:** Accepted

### Decision
CareOps AI combines: structured SQL data (PostgreSQL), vector retrieval (Qdrant), LLM reasoning (Groq/Gemini), time-series forecasting (Prophet), Redis caching, and business-rule validation (critic). No single technology handles all intelligence needs.

### Consequences
- Avoids forcing LLMs into every task
- Produces stronger architecture maturity

---

## LLM provider will sit behind an abstraction layer; Groq is the default
**Status:** Accepted (updated below: Groq later became the default provider, replacing Gemini)

### Context
The project must stay free-tier friendly while remaining expandable.

### Decision
All LLM calls go through `BaseLLMProvider`. `create_llm_provider()` reads `LLM_PROVIDER` from environment and constructs a `FallbackLLMProvider`. Groq is the default provider; Gemini is the automatic fallback.

### Consequences
- Switching providers requires only a config change
- Provider used is logged and persisted in run metadata

---

## Qdrant will be used as the vector database
**Status:** Accepted

### Decision
Qdrant stores complaint patterns and SOPs in shared collections with payload filters for org isolation (see the Qdrant collection strategy decision below). Used for RAG retrieval in the complaint intelligence node and the chat agent.

### Consequences
- Production-grade vector retrieval with metadata-aware filtering
- Requires Docker setup

---

## PostgreSQL will be the primary operational database
**Status:** Accepted

### Decision
PostgreSQL stores all structured data: reservations, menu items, orders, inventory, feedback, decision logs, planning runs, organizations, users, restaurant profiles.

### Consequences
- Strong relational modelling and migration support (Alembic)
- All run queries are org-scoped via `org_id`

---

## Redis will handle plan caching from Phase 5
**Status:** Accepted (promoted from "future" in Phase 5)

### Decision
Redis caches planning run results by `(org_id, scenario, target_date)` with a 1-hour TTL. A `cache_hit: true` flag is returned in the response. Zero LLM cost on cache hits.

### Consequences
- Repeat runs same day return immediately
- Cache invalidates automatically on TTL expiry

---

## Docker Compose for local infrastructure reproducibility
**Status:** Accepted

### Decision
PostgreSQL, Qdrant, and Redis run via Docker Compose with persistent volumes. Data survives container restarts; `docker compose down -v` resets everything.

### Consequences
- Cleaner local setup and demo story
- Portable across developer machines

---

## Qdrant collection strategy: shared collection with payload filters
**Date:** 31 May 2026  
**Status:** Accepted

### Decision
Use a single shared Qdrant collection with payload pre-filters instead of per-tenant collections.

Filter pattern:
- `org_id`: tenant isolation
- `doc_type`: semantic separation (`complaint` / `sop`)

### Rationale
Per-tenant collections cause collection sprawl at multi-tenant scale (100 restaurants = 200+ collections). Qdrant payload pre-filtering on a shared collection is the recommended production pattern.

### Impact
Implemented as part of the multi-tenant workspace isolation work. All Qdrant retrieval calls include an `org_id` payload filter.

---

## Groq as default LLM provider (replacing Gemini default)
**Date:** June 2026  
**Status:** Accepted

### Decision
`LLM_PROVIDER` defaults to `groq`. Gemini becomes the automatic fallback.

### Rationale
Groq free tier has higher RPM limits than Gemini, making development and demo runs smoother. The `FallbackLLMProvider` retries on Gemini transparently when Groq hits a rate limit.

### Consequences
- Both `GROQ_API_KEY` and `GEMINI_API_KEY` should be set in `.env`
- Cost rates tracked separately per provider in `llm/base.py`

---

## RAGAS + DeepEval for LLM output quality gating
**Date:** June 2026  
**Status:** Accepted

### Decision
Use RAGAS for complaint RAG faithfulness evaluation and DeepEval for hallucination and relevancy checks. Both run as separate pytest suites in `apps/api/evals/` outside normal `testpaths`.

### Thresholds
- RAGAS faithfulness: ≥ 0.8
- DeepEval hallucination: ≤ 0.5
- DeepEval relevancy: ≥ 0.7

### Consequences
- Live LLM calls required; evals are not part of standard CI
- Datasets must be updated manually when prompts change significantly

---

## MCP server via stdio, not HTTP
**Date:** June 2026  
**Status:** Accepted

### Decision
The MCP server is a standalone stdio subprocess (`mcp_server.py`) rather than an HTTP endpoint embedded in FastAPI. It communicates with the FastAPI backend over HTTP with JWT auth.

### Rationale
stdio is the standard transport for local MCP servers in Claude Code and Claude Desktop. Keeps clear separation between the planning API and the tool interface.

### Consequences
- `mcp_server.py` is spawned as a subprocess by Claude
- JWT obtained on first tool call and reused for the session
- FastAPI has no knowledge of MCP

---

## Static eval datasets
**Date:** June 2026  
**Status:** Accepted

### Decision
RAGAS and DeepEval eval datasets are hand-crafted static JSON, not captured from live planning runs.

### Rationale
Live capture requires a full running stack during test collection and produces non-deterministic results. Static datasets are reproducible and version-controlled.

### Consequences
- Datasets must be manually updated when prompts or critic behaviour changes significantly
- For production use, datasets should be rebuilt from live captures periodically

---

## LangSmith golden dataset as primary regression quality gate
**Date:** June 2026  
**Status:** Accepted

### Decision
Build `careops-golden-v1` (50 curated planning runs) in LangSmith and use a pytest CI gate (`tests/unit/test_langsmith_evals.py`) running against a local JSON fixture, requiring ≥ 90% pass rate.

### Rationale
RAGAS/DeepEval cover individual component quality. The golden dataset gate covers end-to-end plan quality: catching regressions that pass component evals but produce worse plans overall.

### Consequences
- `build_golden_dataset.py` must be re-run when the system changes significantly
- 90% threshold is intentionally strict: allows one or two borderline runs in 50

---

## Prompts centralised in `prompt_utils.py`
**Date:** June 2026  
**Status:** Accepted

### Decision
All LLM prompt construction is centralised in `app/infrastructure/llm/prompt_utils.py`. No raw prompt strings exist in service files.

### Rationale
Scattered prompt strings in service files make prompt iteration, testing, and auditing difficult. A single module is the authoritative source for all prompt templates.

### Consequences
- Changing a prompt requires editing one file only
- Easier to review prompt quality and catch regressions

---

## Assumption diffing in EvaluationSanityChecker instead of enumerated contradiction pairs
**Date:** June 2026  
**Status:** Accepted

### Context
The original `EvaluationSanityChecker` caught cross-agent contradictions via hardcoded rule pairs (e.g. "if inventory flags item X as low, the menu shouldn't promote X"). As the menu and agent set grow, enumerating every possible pair becomes a combinatorial explosion that is impossible to maintain exhaustively.

### Decision
Each domain node now declares the assumptions it acted on when producing its output. These assumptions are derived from the node's own computed values: not hardcoded: and written as a small dict to `OrchestratorState` alongside the node's output (`menu_assumptions`, `inventory_assumptions`, `reservation_assumptions`, `complaint_assumptions`). The aggregator collects these into the recommendation bundle. `EvaluationSanityChecker.check_bundle()` then cross-diffs the assumptions: for each assumption in node A, it checks whether it is contradicted by a known fact in node B's output.

The result is a `stale_assumptions` list returned alongside the existing `issues` list. Conflicts surface automatically from structural mismatch: no enumeration of pairs is needed. The critic receives the stale assumptions explicitly in its prompt so it can reason about *why* a contradiction exists rather than detecting it from raw data.

### Rationale
The combinatorial explosion problem: N agents → O(N²) contradiction pairs to enumerate. The assumption-diff approach scales linearly with agent count: adding a new agent requires only that the new node writes its own assumptions dict. No changes to the checker or other nodes.

A secondary benefit: assumptions make node reasoning explicit and auditable. If a node made recommendations based on a stale belief, that belief is now visible in the run output rather than implicit in the LLM's prompt context.

The hardcoded checks are **kept as a secondary layer**: they catch concrete policy violations (capacity limits, impossible inventory quantities, long-horizon actions) that are structural rather than assumption-based.

### Consequences
- Each domain node must derive and write its own `assumptions` dict: this is a new contract for any future domain node added to the pipeline
- Graceful degradation: if a node errored and its assumptions dict is `None`, the checker skips diffing for that node without crashing
- `stale_assumptions` is always present in `check_bundle()` output (may be an empty list): callers that previously only used `passed`, `issues`, and `summary` are unaffected

### Post-implementation note (June 2026)

**Diff 1 removed.** The original implementation included a fourth diff (`assumed_no_active_stockouts` in `menu_intelligence` vs the inventory node's shortage list). This was dropped after discovering it would always agree: `MenuService.analyse_and_recommend()` contains a self-healing fallback that directly instantiates `InventoryService` and queries the DB whenever `inventory_data=None`. Although `menu_intelligence` now runs after `reservation`, `complaint_intelligence`, and `inventory` complete (LangGraph fan-in), `MenuService` still queries the DB directly: both nodes use the same demand ratio and the same DB, so they always agree on shortage status. The `assumed_no_active_stockouts` field has been removed from `menu_assumptions`. Three diffs remain active: Diff 2 (menu covers capacity vs reservation occupancy), Diff 3 (high-occupancy planning on weak forecast), and Diff 4 (complaint volume gray zone).

---

## Connector layer design: BaseConnector ABC with sync() and enrich() methods
**Date:** June 2026
**Status:** Accepted

### Context
Phase 6 adds Swiggy MCP as a live data source. Without a common interface, each integration would be a bespoke pile of HTTP calls with no shared error handling, token management, or degradation contract.

### Decision
All external platform integrations implement `BaseConnector` (ABC defined in `infrastructure/base_connector.py`, shared across all connector types, not Swiggy-specific) with two methods:

- `sync()`: nightly job. Pulls historical data from the platform and writes it to the unified Postgres layer (orders, reservations, feedback). Side effects are allowed. Returns a summary dict.
- `enrich()`: at planning time. Fetches live market signals (competitor prices, area occupancy, ingredient availability). Must NOT write to the DB. Must return `None` on any failure. Nodes fall back to synthetic data when `enrich()` returns `None`.

`SwiggyConnector` is the reference implementation. Extending this pattern to a food-delivery, dining-out, or quick-commerce competitor (Zomato, EazyDiner) is not permitted while the signed Swiggy Integration Agreement's exclusivity clause is in effect (see the Zomato stub removal decision below). Future connectors are scoped to non-competing categories: POS systems, loyalty and rewards platforms, accounting and inventory tools, review aggregators, payment processors. `pos_square` and `google_reviews` already prove the pattern extends cleanly to these.

OAuth tokens are stored encrypted per `org_id` in the `connectors` table, managed by `ConnectorRepository`. `SWIGGY_ACCESS_TOKEN` in `.env` is a dev-only convenience for single-org testing: production always reads from the connectors table.

### Rationale
- Single interface means one error-handling pattern across all integrations.
- The sync/enrich split keeps planning-time code read-only and fast; nightly jobs handle slow writes.
- `enrich()` returning `None` as the degradation contract means no try/except in LangGraph nodes: they just check `if enrichment is None`.
- Per-org token storage in the DB (not env vars) is required for true multi-tenancy.

### Consequences
- Every new connector must implement both `sync()` and `enrich()`: even if one is a no-op for that platform.
- `ConnectorRepository.list_active()` is the entry point for nightly sync jobs: it returns only connectors with a token set.
- The `connectors` table unique constraint `(org_id, connector_type)` prevents duplicate registrations.

---

## SSE streaming for planning runs and chat
**Date:** June 2026  
**Status:** Accepted

### Decision
`POST /api/v1/planning/stream` and `POST /api/v1/chat` return `text/event-stream` responses. `POST /api/v1/planning/run` is a standard JSON endpoint: no streaming.

- **Planning SSE (`/planning/stream`)**: emits `node_complete` events carrying only the node name as each LangGraph node finishes; the loading screen pipeline diagram updates in real time. The full plan arrives in a single final `complete` event and renders all at once.
- **Chat SSE (`/chat`)**: streams individual tokens word-by-word via AsyncGroq. Entirely separate mechanism.

### Rationale
The planning pipeline takes 10–30 seconds. Emitting node status as each completes makes the experience feel interactive: the user sees the pipeline progress rather than a blank loading spinner.

### Consequences
- FastAPI returns a `StreamingResponse` for `/planning/stream` and `/chat`
- Planning `node_complete` events carry `{"node": "nodename"}` only: no output data in the stream
- The full plan renders all at once from the single `complete` event
- Frontend must handle stream teardown and error events

---

## Circuit breaker pattern for Swiggy MCP calls
**Status:** Accepted

### Context
Swiggy MCP servers can experience transient degradation or be temporarily unreachable. Without protection, every planning run that uses a Swiggy enricher would block on the timeout for every call, cascading latency into the planning pipeline.

### Decision
Implement a Redis-backed circuit breaker per Swiggy endpoint (`food`, `im`, `dineout`). Five or more failures within a 5-minute window opens the circuit for a 10-minute window. `SwiggyMCPClient.call_tool()` checks the circuit before every HTTP call and records outcomes. The provider registry's async method also checks the circuit before routing.

### Consequences
- Degraded Swiggy endpoints fail fast instead of blocking the pipeline
- Circuit state is observable via `GET /api/v1/health/circuits`
- Fail-open policy: if Redis is down, `is_open()` returns False so calls are attempted rather than blocked
- No code changes needed to add a new endpoint: the circuit key is derived from the URL

---

## Planning memory with recency-weighted retrieval
**Status:** Accepted

### Context
Past approved planning runs contain valuable operational signals (what worked, what was flagged, under what conditions). A naive embedding store without time-weighting treats a run from 89 days ago the same as one from yesterday.

### Decision
Store approved run insights in a Qdrant `planning_memory` collection. At retrieval time, apply recency decay `score × 2^(-age/RECENCY_HALF_LIFE_DAYS)` with a 14-day half-life and a 90-day maximum age cutoff. Over-fetch 2×top_k candidates, re-rank by decayed score, return top-k.

### Consequences
- Recent runs strongly influence future planning; old runs fade gracefully
- The decay formula is interpretable: a 14-day-old run has half the weight of today's, a 28-day-old run has a quarter
- 90-day cutoff prevents very old operational contexts from surfacing (restaurant conditions change)
- No database migration needed: pure Qdrant

---

## Asymmetric embeddings for SemanticPlanCache
**Status:** Accepted

### Context
Using the same text for both storage and retrieval embeddings in the plan cache causes precision loss. At storage time we know the actual run conditions (demand_ratio, occupancy, shortages); at query time we only know scenario + date. Using the same embedding for both means rich storage context is "wasted": the query can't match on conditions it doesn't yet know.

### Decision
Use two distinct embeddings: `_query_text()` (lightweight, retrieval-side: `"org:{id} scenario:{scenario} date:{date}"`) and `_storage_text()` (enriched, write-side: same base + `demand_ratio`, `occupancy%`, `shortages`, `verdict`). This is an intentional asymmetry: the storage embedding is richer so future queries with similar scenarios on similar dates can score higher when conditions were similar, without requiring the caller to know those conditions at query time.

### Consequences
- Future runs under similar pressure (high demand, same shortages) will match historical runs more accurately
- The retrieval-side embedding stays simple: no caller changes needed
- Approved-only writes ensure the cache only returns plans that passed quality review

---

## Remove the Zomato stub connector for exclusivity compliance
**Date:** July 2026
**Status:** Accepted

### Context
A signed Swiggy Integration Agreement (effective 2026-07-09) includes an exclusivity clause barring partnership with any other food delivery, dining-out, or quick-commerce platform for a similar solution, enforceable by injunctive relief, not just damages. A codebase audit found more than a name in one file: a genuine no-op `ZomatoConnector` stub, `zomato` listed alongside `swiggy` in `provider_registry.py`'s capability-to-provider lists, `eazydiner` listed under reservation data, and a live "Zomato" card on the `/connectors` page.

### Decision
Remove `apps/api/app/infrastructure/zomato/` entirely, remove `zomato` and `eazydiner` from `provider_registry.py`'s capability lists, remove the frontend connector card, remove `ConnectorType.zomato` from `models.py`, and delete the Zomato connector test file. Leave `FeedbackSource.zomato` untouched: it is a provenance tag for feedback that originated from a Zomato review, not a live Zomato connection.

### Consequences
- The multi-provider connector architecture (`BaseConnector`, `provider_registry.py`, `ConnectorType`) stays fully intact; only the specific competing-platform provider was removed
- No Alembic migration needed: `connector_type` is a plain `String(50)` column, not a database enum
- Future connectors must not be a food delivery, dining-out, or quick-commerce platform while the exclusivity clause is in effect (see the connector layer design decision above)

---

## Anonymise market intelligence to area-level aggregates
**Date:** July 2026
**Status:** Accepted

### Context
The same Swiggy Integration Agreement prohibits using the Swiggy MCP, directly or indirectly, to gather competitive intelligence on Swiggy restaurants or sellers, or to benchmark a competing product. `CompetitorEnricher` and the competitor-facing calls in `OccupancyEnricher` did exactly this: named restaurants, named prices, named deals, surfaced in the result dict, the LLM prompt, the `/market/pulse` API response, the operator chat assistant's Swiggy tools, and the `/market` page UI.

### Decision
Replace every named-restaurant output with area-level aggregates only: `area_restaurant_count`, `deals_active_count` and `deals_summary`, `landscape_summary` (count, average rating, cost-for-two range, offers count). `category_pricing`'s `cheapest_dish`/`priciest_dish` keep the dish name, which is not restaurant-identifying, but drop which restaurant serves it.

### Consequences
- Every consumer of market intelligence data was updated to match: `market_intel_service.py`, the `market_intel` node, `workflow_trigger_service.py`, `mcp_server.py`'s `get_market_brief`, `chat_service.py`'s Swiggy tools, `market.py`'s Pydantic models, and the frontend market panel
- The planning pipeline's competitive signal is weaker in specificity but compliant; the critic and menu intelligence node still receive directional signal (an area is crowded, deals are active) without naming a competitor

---

## Live-intelligence signals fetched independently of the Swiggy MCP
**Date:** July 2026
**Status:** Accepted

### Context
Weather, industry trends, and regulatory alerts are valuable planning signals that do not require Swiggy data at all, and are not subject to the Integration Agreement's consent or competitive-intelligence constraints.

### Decision
Build three independently fail-open services under `infrastructure/external/`: `WeatherService` (Open-Meteo, free and keyless), `TrendsService` (curated Indian food and beverage RSS feeds, summarised via the existing LLM provider factory), and `ComplianceAlertsService` (FSSAI's public notifications page, parsed with BeautifulSoup). Each returns `None` on failure and never raises, matching the Swiggy enricher contract. A new `live_signals` node fetches all three once, early in the graph, so `demand_forecast` and `market_intel` both read the same fetch instead of calling the same services twice. Weather also applies a real deterministic multiplier to the Prophet forecast number, not just narrative prompt text.

### Consequences
- `GET /market/pulse` returns weather, trends, and compliance alerts independently of whether Swiggy is connected
- All five signal sources (competitor, occupancy, weather, trends, compliance) are independently optional through the whole pipeline: any subset being unavailable never blocks the others

---

## Langfuse session scoped to the individual run, not the organisation
**Date:** July 2026
**Status:** Accepted

### Context
Kindred's replay debugging tool matches an original trace to its replay by polling Langfuse trace metadata, keyed by `session_id`. The original implementation set `session_id = f"org-{org_id}"`, pooling every run from one organisation into a single Langfuse session. Live testing found this actively broke Kindred's original-to-replay matching: one session had pooled 199 unrelated observations across many unrelated runs.

### Decision
Scope `session_id` to the individual `run_id` instead of the organisation.

### Consequences
- Original and replay trace-tree structure now line up one to one
- Kindred's own Reproducibility comparison view still does not render the original output for the "Agent Output" step even with the session fix; this was directly verified via Langfuse's public API to be a gap in Kindred's own matching and rendering, not a data problem on this side

---

## Guest Concierge is compliant under clause 1.1, not gated on separate Swiggy consent
**Date:** August 2026
**Status:** Accepted

### Context
Guest Concierge is a no-auth, consumer-facing assistant that plans a guest's event end-to-end via Swiggy's Food, Instamart, and Dineout MCP servers. Clause 1.1 of the signed Integration Agreement describes exactly this shape of integration, a consumer-facing assistant serving guests directly through Swiggy's platform, independent of any specific restaurant's CareOps AI data, as the Proposed Arrangement the agreement itself covers.

### Decision
Build Guest Concierge as part of Phase 6A. It is architecturally and operationally independent of the restaurant-operator side: no shared session state, no restaurant data, no auth, and its own no-auth `/concierge` API surface and frontend page.

### Consequences
- The existing compliance guardrails (the Zomato stub removal for exclusivity, and anonymised market intelligence for the competitive-intelligence clause) apply to the restaurant-operator side's Swiggy usage; Guest Concierge's Swiggy usage is direct, real, and consumer-facing by design, which is what clause 1.1 describes, not a competitive-intelligence or exclusivity concern
- Staging-gated actions (real Instamart checkout, real Dineout table booking) still require separate Swiggy staging credentials regardless of this decision: this is an infrastructure/credentials blocker, not a compliance one

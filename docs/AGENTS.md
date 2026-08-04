# CareOps AI Orchestration Nodes

Reflects the implemented LangGraph graph and chat agent, Phase 6A in progress.

---

## Overview

CareOps AI's planning pipeline is implemented as a LangGraph `StateGraph` with fifteen registered nodes: a sequential head from `ops_manager` through `live_signals`, `demand_forecast`, and `qdrant_enrichment`, a five-way parallel fan-out, `menu_intelligence` as a sequential fan-in, and a sequential tail through aggregation, the critic, an optional replan loop, a narrative summary, and final assembly.

The graph is constructed per request by `build_graph(deps)` in `app/orchestration/graph.py`. Dependencies (database session, LLM provider, memory service, planning memory service, Swiggy client) are injected at wire time.

Two separate agents sit outside this graph: the operator chat agent powering the `/chat` assistant, and the Guest Concierge agent powering the consumer-facing `/concierge` experience.

---

## Graph topology

```
ops_manager
    |
    +-- (error) --> final_assembler --> END
    |
    v
live_signals            (weather, holiday, industry trends, FSSAI alerts, fetched once)
    |
    v
demand_forecast          (reads weather/holiday back from state, applies a real multiplier)
    |
    v
qdrant_enrichment         (retrieves past approved-run insights)
    |
    +----------+----------+----------+----------+
    v          v          v          v          v
reservation  complaint_   inventory  market_    dineout_
             intelligence            intel      manager
    +----------+----------+----------+----------+
                          |
                          v
                 menu_intelligence   (sequential fan-in, fires once)
                          |
                          v
                      aggregator
                          |
                          v
                        critic
                          |
      +-------------------+--------------------+
 (approved, or                            (revision,
  replan_count >= 2)                       replan_count < 2)
      v                                          v
situation_summary                     replan_orchestrator
      |                                          |
      v                              menu_intelligence (loop)
final_assembler
      |
     END
```

The conditional edge after `ops_manager` short-circuits to `final_assembler` if `state["error"]` is set.

---

## Planning pipeline nodes

### `ops_manager`

**Role:** Pipeline entry point. Resolves the scenario (a fixed preset, or a `custom_profile` derived from natural language or from live signals), frames the operational context, and initializes shared state.

**Inputs:** Scenario id, target date, simulation mode, restaurant profile, org settings
**Outputs:** Populated `OrchestratorState` with scenario metadata and `org_id`, or `state["error"]` on invalid input
**Implementation:** `app/orchestration/nodes/ops_manager.py`
**Dependencies:** None (synchronous)

Validation is not a closed-set membership check against the four presets alone. If `scenario` matches one of the fixed preset ids, behavior is unchanged. If not, and `state["custom_profile"]` is present (built by `ScenarioProfileService` from free text, or by `LiveScenarioComposer` from live signals; see `docs/PRODUCT_MODES.md`), `scenario_profile` is built from that instead. Only an unrecognized scenario with no `custom_profile` still short-circuits to `state["error"]`.

---

### `live_signals`

**Role:** Fetches every non-Swiggy live-intelligence signal up front, in one place, so `demand_forecast` and every downstream node react to one consistent snapshot instead of each node fetching independently.

**Inputs:** `target_date`
**Outputs:** `state["weather_signal"]`, `state["trends_signal"]`, `state["compliance_alerts_signal"]`, `state["holiday_context"]`
**Implementation:** `app/orchestration/nodes/live_signals.py`
**Services:** `WeatherService` (Open-Meteo, free, keyless), `TrendsService` (curated RSS), `ComplianceAlertsService` (FSSAI public notices)
**Dependencies:** None beyond `target_date`, already set by `ops_manager`

This node is a straight extraction of logic `demand_forecast_node` previously did inline. None of its three sources touch the Swiggy MCP, so none needs consent or compliance gating. Swiggy-specific signals (competitor pricing, area occupancy, own-restaurant Dineout slot visibility) deliberately stay in the parallel fan-out below, not folded into this node, both to keep their latency off the critical path shared by every run and to keep Swiggy's contribution individually and clearly attributed rather than blended into a generic bucket.

Fails open on all three sources independently. In simulation mode, this node never touches a real external service.

---

### `demand_forecast`

**Role:** Produces the demand and service-pressure signal used by all downstream domain nodes.

**Inputs:** Scenario context from `ops_manager`, `weather_signal` and `holiday_context` from `live_signals`
**Outputs:** Forecast output block, predicted covers, peak hour, confidence band, day-of-week adjustment
**Implementation:** `app/orchestration/nodes/demand_forecast.py`
**Service:** `ForecastService`, querying historical orders from PostgreSQL and running a Prophet time-series model
**Dependencies:** `db`, `llm`

Prophet's prediction is purely historical and cannot, on its own, know about a forward-looking one-off signal its training data never saw, such as a holiday or a rain forecast. `ForecastService._apply_signal_adjustments()` applies a deterministic multiplier to the raw Prophet output using the weather and holiday context already fetched by `live_signals`, not just narrative prompt text an LLM may or may not act on. The adjustment is transparent by construction: the pre-adjustment prediction, the multiplier, and the reasons are all preserved in the forecast dict alongside the adjusted number. Industry trends and compliance alerts are read back from state as narrative context for this node's own recommendation text, without affecting the multiplier.

---

### `qdrant_enrichment`

**Role:** Retrieves similar past approved-run insights from Qdrant before the parallel fan-out, using recency-decayed scoring so recent runs rank higher than old ones.

**Inputs:** Scenario context and demand signal, `org_id`
**Outputs:** `shared_context["past_plans"]`, the top similar past plan snippets, an empty list on failure
**Implementation:** `app/orchestration/nodes/qdrant_enrichment.py`
**Service:** `PlanningMemoryService`
**Dependencies:** `memory`, `planning_memory`

---

### `reservation`

**Role:** Analyzes booking density, occupancy percentage, waitlist depth, and the busiest service window for the target date.

**Inputs:** Scenario context, demand signal
**Outputs:** Reservation output block: occupancy percentage, waitlist count, peak hour, priority level, risks, recommendations
**Assumptions written to state (`reservation_assumptions`):** assumed peak occupancy percentage; whether the waitlist is active
**Implementation:** `app/orchestration/nodes/reservation.py`
**Service:** `ReservationService`
**Dependencies:** `db`, `llm`

---

### `complaint_intelligence`

**Role:** Retrieves historically similar complaint patterns and matching SOPs from Qdrant, org-scoped, and converts them into operational risk signals and action items.

**Inputs:** Scenario context, demand signal
**Outputs:** Complaint output block and RAG context
**Assumptions written to state (`complaint_assumptions`):** recent complaint categories; whether complaint volume is high; the underlying negative-feedback percentage
**Implementation:** `app/orchestration/nodes/complaint_intelligence.py`
**Service:** `ComplaintService`, `MemoryService` (Qdrant retrieval with an org payload filter)
**Dependencies:** `db`, `llm`, `memory`

RAG context is retrieved before the LLM call, so retrieved complaints and SOPs feed directly into the prompt: the LLM reasons over real past data, not a summary.

---

### `inventory`

**Role:** Identifies shortage and overstock concerns for the selected scenario, flagging items at or below their reorder threshold and items at spoilage risk.

**Inputs:** Scenario context, demand signal
**Outputs:** Inventory output block: shortage alerts, overstock alerts, restock priority list
**Assumptions written to state (`inventory_assumptions`):** ingredients flagged low; ingredients flagged overstock
**Implementation:** `app/orchestration/nodes/inventory.py`
**Service:** `InventoryService`
**Dependencies:** `db`, `llm`, `swiggy_client` (Instamart ingredient price lookups)

---

### `market_intel`

**Role:** Reads live Swiggy-backed market data (area pricing, positioning, menu breadth, cuisine crowding, veg mix, competitor deal activity, area occupancy) and merges it with the weather, trends, and compliance signals already fetched by `live_signals` into one combined live-signals text block.

**Inputs:** Scenario context, `org_id`, `weather_signal`/`trends_signal`/`compliance_alerts_signal` from state
**Outputs:** `market_intel_output`, including `live_signals_text`, consumed by `menu_intelligence` and condensed into the critic's summary
**Implementation:** `app/orchestration/nodes/market_intel.py`
**Service:** `MarketIntelService`, running the competitor and occupancy Swiggy enrichers concurrently
**Dependencies:** `db_factory`, `swiggy_client`

All Swiggy-derived output here is reported as area-level aggregates only, never as a named competitor restaurant, price, or rating; see the compliance note in the root `README.md` and `CLAUDE.md` for why.

---

### `dineout_manager`

**Role:** Reads the operator's own restaurant's public Dineout slot visibility, and analyzes competitor slot availability as a public-data area-demand signal.

**Implementation:** `app/orchestration/nodes/dineout_manager.py`
**Dependencies:** `swiggy_client`

Confirmed live: `get_available_slots` against the operator's own restaurant id reads public slot visibility correctly, but neither opening nor closing the operator's own slots is possible through this tool. That requires the Swiggy Partner API, which this integration does not have access to.

---

### `menu_intelligence`

**Role:** Evaluates menu performance in the context of the scenario's demand and operational constraints, identifying what to push, ease back on, and avoid promoting tonight.

**Inputs:** Scenario context, demand signal, all five parallel node outputs
**Outputs:** Menu output block: top items, weak items, promotion strategy, watchouts
**Assumptions written to state (`menu_assumptions`):** items assumed available for promotion (top performers not on the shortage list); whether covers are assumed within capacity
**Implementation:** `app/orchestration/nodes/menu_intelligence.py`
**Service:** `MenuService`
**Dependencies:** `db`, `llm`

This node fires once LangGraph's fan-in from all five parallel nodes completes. `MenuService` does not directly consume `reservation_output` from state; it queries its own data sources. The cross-agent assumption diff described below is what catches a case such as reservation showing over 90 percent occupancy while menu's implicit capacity assumption does not account for it.

---

### `aggregator`

**Role:** Collects the domain node outputs and combines them into a single package for the critic to evaluate.

**Implementation:** `app/orchestration/nodes/aggregator.py`
**Dependencies:** None (synchronous)

---

### `critic`

**Role:** Validates the aggregated plan against operational rules and scores it across several quality dimensions. No plan reaches the operator without a verdict.

**Scoring dimensions:**

| Dimension | What it checks |
|-----------|----------------|
| Safety | Are all recommendations safe for staff and guests? |
| Feasibility | Is the plan realistic given current stock and staffing? |
| Evidence | Are recommendations backed by data from the domain nodes? |
| Actionability | Can staff act on this without further clarification? |
| Clarity | Is the plan clearly and unambiguously stated? |

**Verdicts:** approved, revision, rejected
**Implementation:** `app/orchestration/nodes/critic.py`
**Services:** `CriticService`, `CostAwareScoringService`, `EvaluationSanityChecker`
**Dependencies:** `db`, `llm`

`EvaluationSanityChecker` cross-diffs each domain node's own written assumptions after the fan-in, surfacing contradictions as `stale_assumptions` injected into the critic's prompt. One such diff checks `market_intel_assumptions` for a case where the area is flagged busy but two or more competitor Dineout deals are also live: real walk-in demand at the operator's own restaurant may be lower than the raw occupancy signal suggests, since some of that demand is being absorbed by competitor promotions.

---

### `replan_orchestrator`

**Role:** Manages the replan loop between `critic` and `menu_intelligence`. When the critic returns a revision verdict, this node injects the critic's feedback into `state["replan_context"]` so the next cycle receives concrete correction guidance. Enforces a maximum of two replan cycles.

**Implementation:** `app/orchestration/nodes/replan_orchestrator.py`
**Dependencies:** None (synchronous)

After two failed revision cycles, the run proceeds to `situation_summary` with whatever verdict the critic most recently gave; it never blocks indefinitely.

---

### `situation_summary`

**Role:** Builds a short narrative summary of the completed run for the final response, giving the operator a plain-language recap alongside the structured per-agent output.

**Inputs:** The aggregated recommendation bundle and critic verdict
**Outputs:** `state["situation_summary_output"]`, included in the final API response
**Implementation:** `app/orchestration/nodes/situation_summary.py`
**Dependencies:** `llm`

---

### `final_assembler`

**Role:** Formats the complete final response for the API client, handling both the normal path and the error short-circuit from `ops_manager`.

**Outputs:** `state["final_response"]`, the API-ready response
**Implementation:** `app/orchestration/nodes/final_assembler.py`
**Dependencies:** None (synchronous)

---

## Chat agent

The chat agent is a stateless, streaming agent outside the LangGraph graph. It powers the `/chat` page, the floating chat widget, and `POST /api/v1/chat`.

**Role:** Answers natural-language questions about a restaurant's planning history, inventory status, and guest feedback, grounded in the operator's own data.

**Implementation:** `app/domain/services/chat_service.py`

**How it works:**

1. Receives the user's message and conversation history.
2. Checks a semantic cache and returns a cached answer if a similar question was asked by the same organization recently.
3. Retrieves context from real Qdrant retrieval (past complaints and SOPs relevant to the question, not just the most recent rows) and from PostgreSQL run history.
4. Builds a system prompt grounding the LLM in the retrieved context.
5. When conversation history exceeds eight turns, older turns are compressed and injected as a single context message, with the last eight turns kept verbatim.
6. Streams tokens via a provider factory that dispatches on `LLM_PROVIDER`.
7. Persists the conversation as a `ChatSession`/`ChatMessage` pair, queryable via `GET /chat/sessions` and `GET /chat/sessions/{id}`.
8. Also has access to an internal MCP server exposing planning, market, and Action Queue tools directly to the model as function calls.

**Dependencies:** `db`, the LLM provider factory, the semantic chat cache, the internal MCP server

---

## Guest Concierge agent

A second stateless, streaming agent, entirely separate from both the LangGraph graph and the operator chat agent. It powers the no-auth `/concierge` page and `POST /api/v1/concierge/chat`.

**Role:** Plans a guest's dining or event experience end-to-end (venue, food, supplies) by calling Swiggy's Food, Instamart, and Dineout MCP servers directly, independently of any restaurant-operator data.

**Implementation:** `app/domain/services/concierge_service.py`

**How it works:**

1. Receives the guest's message and the current session (a `ConciergeSession` loaded from Redis, or a fresh one).
2. Extracts structured intent (occasion, headcount, budget, preferences, locality) from the message via a one-shot LLM call, merging only newly-mentioned fields into the session so multi-turn context accumulates.
3. Runs a ReAct tool-calling loop (Groq function calling) over 20 tools spanning Dineout (venue search, availability, booking), Food (restaurant search, menu, cart, ordering, tracking), Instamart (supply search, cart, ordering, tracking), and planning (budget summary, track everything).
4. Streams a tagged chunk for each step: a status update while a tool call is in flight, the tool's structured result once it completes, and the narrated answer word by word once the loop ends.
5. Persists the updated session back to Redis (2-hour TTL) regardless of outcome.

**Dependencies:** the LLM provider factory, `SwiggyMCPClient`, Redis (session state only, no PostgreSQL or Qdrant)

**Design constraints:** no `org_id`, no user account, no restaurant-operator data of any kind. A tool call that fails degrades to a fixed, friendly message; the guest never sees a raw exception, stack trace, or internal tool name. Table booking and Instamart checkout are staging-gated and shown honestly as pending rather than hidden or faked.

---

## State management

The shared state type is `OrchestratorState` (a `TypedDict`) in `app/orchestration/state.py`. It carries scenario metadata and runtime flags, `org_id`, the live-signal fields written by `live_signals`, per-node output fields, per-node assumption dicts used for cross-agent diffing, `shared_context["past_plans"]`, `replan_context`, the `error` field checked after `ops_manager`, an `execution_trace` populated when debugging, and `llm_registry`, a tier-keyed dict of providers populated when tiered routing is enabled.

Initial state is created by `make_initial_state()` in the same module.

---

## Scenario presets

| Id | Label | Default weekday | Service window |
|----|-------|-----------------|----------------|
| `friday_rush` | Friday Rush | Friday | 18:00 to 22:00 |
| `weekday_lunch` | Weekday Lunch | Wednesday | 12:00 to 15:00 |
| `holiday_spike` | Holiday Spike | Saturday | 17:00 to 22:00 |
| `low_stock_weekend` | Low-Stock Weekend | Sunday | 18:00 to 22:00 |

These four presets remain available as deliberate manual shortcuts for exploring a hypothetical scenario on a future date. For "run this right now," see `docs/PRODUCT_MODES.md` for how natural-language and live-signal-composed profiles bypass the fixed preset set entirely.

---

## Implementation note

Most pipeline nodes behave as deterministic service stages with an LLM-assisted reasoning step, rather than as fully autonomous agents. The node label is a deliberate choice from the original architecture design: each node owns a single domain, with its own data adapter, model configuration, and evaluation criteria.

"""
CareOps AI LangGraph orchestration graph.

Enhanced for P1-10:
- Supports simulation mode for deterministic testing
- Enables critic override for validation scenarios
- Adds debug observability for LangGraph state inspection
- Maintains backward compatibility with existing workflows
"""

import functools
import os
import time
import uuid

import sentry_sdk
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from app.orchestration.state import OrchestratorState, make_initial_state
from app.orchestration.nodes import (
    ops_manager_node,
    live_signals_node,
    demand_forecast_node,
    reservation_node,
    complaint_intelligence_node,
    menu_intelligence_node,
    inventory_node,
    market_intel_node,
    dineout_manager_node,
    aggregator_node,
    critic_node,
    situation_summary_node,
    final_assembler_node,
    qdrant_enrichment_node,
    replan_orchestrator_node,
)
from app.infrastructure.swiggy.client import SwiggyMCPClient
from app.infrastructure.llm.base import bind_llm_usage_node, reset_llm_usage_node


# ── Node name constants ──────────────────────────────────────────────────────

OPS_MANAGER = "ops_manager"
LIVE_SIGNALS = "live_signals"
DEMAND_FORECAST = "demand_forecast"
QDRANT_ENRICHMENT = "qdrant_enrichment"
RESERVATION = "reservation"
COMPLAINT_INTELLIGENCE = "complaint_intelligence"
INVENTORY = "inventory"
MARKET_INTEL = "market_intel"
DINEOUT_MANAGER = "dineout_manager"
MENU_INTELLIGENCE = "menu_intelligence"
AGGREGATOR = "aggregator"
CRITIC = "critic"
REPLAN_ORCHESTRATOR = "replan_orchestrator"
SITUATION_SUMMARY = "situation_summary"
FINAL_ASSEMBLER = "final_assembler"


def _llm_log_fields(llm: Any | None) -> dict:
    if llm is None:
        return {}

    fields = {}
    provider_used = getattr(llm, "last_provider_used", None)
    if provider_used:
        fields["llm_provider_used"] = provider_used
        fields["llm_fallback_used"] = bool(getattr(llm, "last_fallback_used", False))

    metadata = getattr(llm, "provider_metadata", None)
    if isinstance(metadata, dict):
        fields.update(metadata)

    return fields


# ── Dependency injection helper ──────────────────────────────────────────────

def _inject(node_fn, traces: list, **deps):
    """Wrap async node functions with dep injection, structlog tracing, and timing."""
    @functools.wraps(node_fn)
    async def _wrapped(state: OrchestratorState) -> OrchestratorState:
        log = structlog.get_logger()
        node = node_fn.__name__.replace("_node", "")
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        log.info("node_start", node=node)

        # All providers this node might write to (default llm + any tier providers)
        llm_dep = deps.get("llm")
        registry_providers = list((state.get("llm_registry") or {}).values())
        all_providers = [p for p in [llm_dep] + registry_providers if p is not None]

        # Tag this node's LLM calls on the current asyncio task so drain_usage(node=...)
        # below only picks up records this node made — not a concurrently running
        # fan-out node's records on a shared provider tier (e.g. reservation and
        # inventory both use the "fast" tier and can run at the same time).
        usage_token = bind_llm_usage_node(node)

        try:
            result = await node_fn(state, **deps)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)

            node_usage = []
            for p in all_providers:
                node_usage.extend(p.drain_usage(node=node))
            node_cost_usd = round(sum(u.get("cost_usd", 0) for u in node_usage), 6)

            log.info("node_end", node=node, duration_ms=duration_ms, **_llm_log_fields(deps.get("llm")))
            traces.append({
                "node": node,
                "started_at": started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "llm_usage": node_usage,
                "node_cost_usd": node_cost_usd,
            })
            return result
        except Exception as exc:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)

            node_usage = []
            for p in all_providers:
                node_usage.extend(p.drain_usage(node=node))
            node_cost_usd = round(sum(u.get("cost_usd", 0) for u in node_usage), 6)

            log.error(
                "node_error",
                node=node,
                duration_ms=duration_ms,
                error=str(exc),
                **_llm_log_fields(deps.get("llm")),
            )
            traces.append({
                "node": node,
                "started_at": started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "error": str(exc),
                "llm_usage": node_usage,
                "node_cost_usd": node_cost_usd,
            })
            with sentry_sdk.new_scope() as scope:
                scope.set_tag("langgraph.node", node)
                scope.set_extra("duration_ms", duration_ms)
                sentry_sdk.capture_exception(exc)
            raise
        finally:
            reset_llm_usage_node(usage_token)
    return _wrapped


def _inject_sync(node_fn, traces: list, **deps):
    """Wrap sync node functions with dep injection, structlog tracing, and timing."""
    @functools.wraps(node_fn)
    def _wrapped(state: OrchestratorState) -> OrchestratorState:
        log = structlog.get_logger()
        node = node_fn.__name__.replace("_node", "")
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        log.info("node_start", node=node)
        result = node_fn(state, **deps)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        log.info("node_end", node=node, duration_ms=duration_ms)
        traces.append({"node": node, "started_at": started_at,
                       "ended_at": datetime.now(timezone.utc).isoformat(),
                       "duration_ms": duration_ms})
        return result
    return _wrapped


def _log_node(node_fn, traces: list):
    """Wrap plain (no-dep) nodes with structlog tracing and timing."""
    @functools.wraps(node_fn)
    def _wrapped(state: OrchestratorState) -> OrchestratorState:
        log = structlog.get_logger()
        node = node_fn.__name__.replace("_node", "")
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        log.info("node_start", node=node)
        result = node_fn(state)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        log.info("node_end", node=node, duration_ms=duration_ms)
        traces.append({"node": node, "started_at": started_at,
                       "ended_at": datetime.now(timezone.utc).isoformat(),
                       "duration_ms": duration_ms})
        return result
    return _wrapped


# ── Conditional edges ────────────────────────────────────────────────────────

_REPLAY_METADATA_KEYS = (
    "is_replay",
    "kindred_replay_run_id",
    "kindred_original_session_id",
    "kindred_include_prior_context",
    "kindred_turn_trace_id",
)


def _langfuse_run_context(
    _org_id: int | None, run_id: str, replay_metadata: dict | None = None
) -> tuple[list, dict]:
    """Build the Langfuse callback + Kindred metadata for one planning-graph invocation.

    No-ops (empty callbacks/metadata) when Langfuse isn't configured — Kindred
    replay debugging is optional instrumentation, never a hard requirement to run
    a plan. session_id is scoped to this one run (not shared across every run
    from an org) — Kindred needs a clean 1:1 original-run <-> replay-run mapping
    to find the matching original for a replayed turn; a shared org-wide session
    pools every unrelated run's observations together and breaks that lookup
    (found live: a single "org-1" session had accumulated 199 observations
    across dozens of unrelated runs). org_id is accepted but no longer folded
    into session_id — kept as a parameter for callers/tests, not dead code to
    remove without checking call sites.

    replay_metadata (only passed by the /replay endpoint): when it carries
    kindred_original_session_id, the replay trace joins that exact same
    per-run session instead of getting its own, so Kindred can line up
    original vs. replay side by side. Only non-None replay keys are attached,
    so a normal (non-replay) run's trace is completely unaffected.
    """
    from app.core.settings import get_settings
    settings = get_settings()
    if not settings.langfuse_secret_key:
        return [], {}

    from langfuse.langchain import CallbackHandler
    replay_metadata = replay_metadata or {}
    session_id = replay_metadata.get("kindred_original_session_id") or run_id
    metadata = {
        "agent_id": settings.kindred_agent_id,
        "session_id": session_id,
        "langfuse_session_id": session_id,
    }
    for key in _REPLAY_METADATA_KEYS:
        if replay_metadata.get(key) is not None:
            metadata[key] = replay_metadata[key]
    return [CallbackHandler()], metadata


def _flush_langfuse(langfuse_callbacks: list) -> None:
    if not langfuse_callbacks:
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception:
        pass


def _route_after_ops_manager(state: OrchestratorState) -> str:
    if state.get("error"):
        return FINAL_ASSEMBLER
    return LIVE_SIGNALS


def _route_after_critic(state: OrchestratorState) -> str:
    """
    Replanning loop: if verdict is not 'approved' and we haven't exhausted
    retries (max 2), route back through replan_orchestrator → aggregator → critic.
    Otherwise proceed to final_assembler.
    """
    critic_out   = state.get("critic_output") or {}
    verdict      = critic_out.get("verdict", "revision")
    replan_count = state.get("replan_count") or 0

    if verdict == "approved" or replan_count >= 2:
        return FINAL_ASSEMBLER
    return REPLAN_ORCHESTRATOR


# ── Graph factory ────────────────────────────────────────────────────────────

def build_graph(deps: dict[str, Any], traces: list | None = None):
    """Build CareOps AI hospital operations LangGraph (7-agent pipeline)."""
    from app.orchestration.careops_graph import build_careops_graph
    return build_careops_graph(deps, traces)


def build_legacy_restaurant_graph(deps: dict[str, Any], traces: list | None = None):
    """
    Build and compile the CareOps AI LangGraph.

    Args:
        deps: Infrastructure dependencies:
            - db       : SQLAlchemy Session
            - llm      : BaseLLMProvider instance
            - memory   : MemoryService instance (optional)

    Returns:
        Compiled LangGraph runnable.
    """
    db              = deps["db"]
    llm             = deps["llm"]
    memory          = deps.get("memory")
    planning_memory = deps.get("planning_memory")
    db_factory      = deps.get("db_factory")
    if db_factory is None:
        from app.api.dependencies import get_db_factory
        db_factory = get_db_factory()
    swiggy_client   = deps.get("swiggy_client") or SwiggyMCPClient()
    checkpointer    = deps.get("checkpointer")
    tr              = traces if traces is not None else []

    graph = StateGraph(OrchestratorState)

    # ── Register nodes ───────────────────────────────────────────────────────

    graph.add_node(OPS_MANAGER, _log_node(ops_manager_node, tr))

    graph.add_node(LIVE_SIGNALS,           _inject(live_signals_node,           tr))
    graph.add_node(DEMAND_FORECAST,        _inject(demand_forecast_node,        tr, db=db, llm=llm))
    graph.add_node(QDRANT_ENRICHMENT,      _inject(qdrant_enrichment_node,      tr, memory=memory, planning_memory=planning_memory))
    # Parallel fan-out nodes use db_factory so each creates its own session.
    # This allows asyncio.to_thread() in service layer to run sync DB queries
    # without blocking the event loop or causing session thread-safety issues.
    graph.add_node(RESERVATION,            _inject(reservation_node,            tr, db_factory=db_factory, llm=llm))
    graph.add_node(COMPLAINT_INTELLIGENCE, _inject(complaint_intelligence_node, tr, db_factory=db_factory, llm=llm, memory=memory))
    graph.add_node(INVENTORY,              _inject(inventory_node,              tr, db_factory=db_factory, llm=llm, swiggy_client=swiggy_client))
    graph.add_node(MARKET_INTEL,    _inject(market_intel_node,    tr, db_factory=db_factory, swiggy_client=swiggy_client))
    graph.add_node(DINEOUT_MANAGER, _inject(dineout_manager_node, tr, swiggy_client=swiggy_client))
    graph.add_node(MENU_INTELLIGENCE, _inject(menu_intelligence_node, tr, db=db, llm=llm))

    graph.add_node(AGGREGATOR,          _log_node(aggregator_node,          tr))
    graph.add_node(CRITIC,              _inject(critic_node,                 tr, db=db, llm=llm))
    graph.add_node(REPLAN_ORCHESTRATOR, _log_node(replan_orchestrator_node, tr))
    graph.add_node(SITUATION_SUMMARY,   _inject(situation_summary_node,     tr, llm=llm))
    graph.add_node(FINAL_ASSEMBLER,     _log_node(final_assembler_node,     tr))

    # ── Wire edges ───────────────────────────────────────────────────────────

    graph.set_entry_point(OPS_MANAGER)

    graph.add_conditional_edges(
        OPS_MANAGER,
        _route_after_ops_manager,
        {
            LIVE_SIGNALS:    LIVE_SIGNALS,
            FINAL_ASSEMBLER: FINAL_ASSEMBLER,
        },
    )

    # Live signals (weather/holiday, trends, FSSAI) before demand_forecast,
    # which needs weather for its multiplier -- everything else downstream
    # reads these back from state rather than any node re-fetching.
    graph.add_edge(LIVE_SIGNALS, DEMAND_FORECAST)

    # Qdrant pre-enrichment before parallel fan-out
    graph.add_edge(DEMAND_FORECAST, QDRANT_ENRICHMENT)

    # Parallel fan-out: reservation, complaint, inventory, market_intel, dineout_manager
    graph.add_edge(QDRANT_ENRICHMENT, RESERVATION)
    graph.add_edge(QDRANT_ENRICHMENT, COMPLAINT_INTELLIGENCE)
    graph.add_edge(QDRANT_ENRICHMENT, INVENTORY)
    graph.add_edge(QDRANT_ENRICHMENT, MARKET_INTEL)
    graph.add_edge(QDRANT_ENRICHMENT, DINEOUT_MANAGER)

    # All five parallel nodes must complete before menu starts.
    # LangGraph fires menu_intelligence once all five fan-in edges resolve.
    graph.add_edge(RESERVATION,            MENU_INTELLIGENCE)
    graph.add_edge(COMPLAINT_INTELLIGENCE, MENU_INTELLIGENCE)
    graph.add_edge(INVENTORY,              MENU_INTELLIGENCE)
    graph.add_edge(MARKET_INTEL,           MENU_INTELLIGENCE)
    graph.add_edge(DINEOUT_MANAGER,        MENU_INTELLIGENCE)

    # Single fan-in: aggregator fires exactly once, after menu
    graph.add_edge(MENU_INTELLIGENCE, AGGREGATOR)

    # Aggregator → Critic → conditional replanning loop
    graph.add_edge(AGGREGATOR, CRITIC)
    graph.add_conditional_edges(
        CRITIC,
        _route_after_critic,
        {
            # Approved plans go through the situation-summary briefing first,
            # not straight to final_assembler -- this way the summary only
            # ever generates once, on the final approved version, never on an
            # in-progress revision-loop iteration.
            FINAL_ASSEMBLER:     SITUATION_SUMMARY,
            REPLAN_ORCHESTRATOR: REPLAN_ORCHESTRATOR,
        },
    )
    graph.add_edge(SITUATION_SUMMARY, FINAL_ASSEMBLER)

    # Replan loop: orchestrator injects feedback → re-run menu_intelligence with it
    # (not just re-aggregate the same unchanged output) → re-aggregate → re-evaluate.
    # Safe under LangGraph's join semantics: MENU_INTELLIGENCE already has 5 fan-in
    # edges from the initial parallel fan-out; this adds a 6th that's only ever
    # in-flight alone (on replan, none of the other 5 re-fire), mirroring the
    # already-proven pattern where AGGREGATOR has two edges (MENU_INTELLIGENCE and
    # REPLAN_ORCHESTRATOR) and already fires correctly off either one alone.
    graph.add_edge(REPLAN_ORCHESTRATOR, MENU_INTELLIGENCE)
    graph.add_edge(FINAL_ASSEMBLER, END)

    return graph.compile(checkpointer=checkpointer)


# ── Convenience runner ───────────────────────────────────────────────────────

async def run_friday_rush(
    deps: dict[str, Any],
    target_date: str | None = None,
    simulation_mode: bool = False,
    force_critic_decision: str | None = None,
    debug: bool = False,
) -> dict:
    return await run_planning_scenario(
        deps=deps,
        scenario="friday_rush",
        target_date=target_date,
        simulation_mode=simulation_mode,
        force_critic_decision=force_critic_decision,
        debug=debug,
    )


async def run_planning_scenario(
    deps: dict[str, Any],
    scenario: str,
    target_date: str | None = None,
    simulation_mode: bool = False,
    force_critic_decision: str | None = None,
    debug: bool = False,
    org_capacity: int = 70,
    org_peak_hours: str = "18:00-22:00",
    restaurant_profile: dict | None = None,
    critic_threshold: float = 0.7,
    org_id: int | None = None,
    custom_profile: dict | None = None,
    replay_metadata: dict | None = None,
) -> dict:
    """
    Top-level convenience function for a named planning scenario.

    Args:
        deps: Infrastructure dependencies.
        scenario: Scenario id from the scenario registry, or a custom id
            (e.g. "custom") when custom_profile is supplied (P6-A25).
        target_date: Optional ISO date string.
        simulation_mode: Enables deterministic simulation.
        force_critic_decision: Overrides critic verdict for testing.
        debug: Enables observability and state tracing.
        custom_profile: Ad-hoc natural-language-derived scenario profile
            (P6-A25) -- bypasses the semantic cache, since two different
            custom descriptions could otherwise share a cache key.
        replay_metadata: Kindred replay identifiers (P6-A27) attached to the
            Langfuse trace only -- bypasses the semantic cache, since a replay
            must always actually re-run, never return a stale cached plan.

    Returns:
        Final API-ready response from the LangGraph workflow.
    """
    # ── Semantic cache check (Qdrant, similarity >= 0.92) ───────────────────
    semantic_cache = deps.get("semantic_cache")
    if (
        semantic_cache and org_id
        and not simulation_mode and not force_critic_decision and not debug
        and not custom_profile and not replay_metadata
    ):
        try:
            cached = semantic_cache.get(org_id, scenario, target_date)
            if cached is not None:
                structlog.get_logger().info(
                    "semantic_cache_hit", scenario=scenario, org_id=org_id
                )
                return cached
        except Exception:
            pass

    # Shared list — every node wrapper appends its timing record here
    traces: list[dict] = []
    graph = build_graph(deps, traces=traces)

    # Bind run_id + scenario to structlog context — propagates into every node log
    run_id = uuid.uuid4().hex[:8]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(run_id=run_id, scenario=scenario)
    log = structlog.get_logger()

    # Restaurant profile overrides org-level capacity/peak_hours when supplied
    effective_capacity   = restaurant_profile["capacity"]   if restaurant_profile else org_capacity
    effective_peak_hours = restaurant_profile["peak_hours"] if restaurant_profile else org_peak_hours

    # Create initial state with P1-10 enhancements
    initial_state = make_initial_state(
        scenario=scenario,
        target_date=target_date,
        simulation_mode=simulation_mode,
        force_critic_decision=force_critic_decision,
        debug=debug,
        restaurant_profile=restaurant_profile,
        custom_profile=custom_profile,
    )

    # Inject P1-10 testing flags
    initial_state["simulation_mode"] = simulation_mode
    initial_state["force_critic_decision"] = force_critic_decision
    initial_state["debug"] = debug
    initial_state["org_id"] = org_id
    initial_state["org_capacity"] = effective_capacity
    initial_state["org_peak_hours"] = effective_peak_hours
    initial_state["critic_threshold"] = critic_threshold

    # Initialize debug trace container
    if debug:
        initial_state["execution_trace"] = []

    # Inject tier registry into state when tiered comet mode is active
    if deps.get("llm_registry"):
        initial_state["llm_registry"] = deps["llm_registry"]

    # Execute graph with LangSmith + Langfuse trace metadata
    run_label = f"{scenario}/{target_date or 'next'}"
    llm_metadata = _llm_log_fields(deps.get("llm"))
    langfuse_callbacks, langfuse_metadata = _langfuse_run_context(org_id, run_id, replay_metadata)
    config = RunnableConfig(
        run_name=f"careops/{run_label}",
        tags=[scenario, "planning_run"],
        metadata={"scenario": scenario, "target_date": target_date or "", "run_id": run_id, **llm_metadata, **langfuse_metadata},
        callbacks=langfuse_callbacks,
        configurable={"thread_id": run_id},
    )
    t0 = time.perf_counter()
    log.info("graph_start", target_date=target_date or "next", **llm_metadata)
    final_state = await graph.ainvoke(initial_state, config=config)
    _flush_langfuse(langfuse_callbacks)
    total_duration_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Collect usage captured per-node by _inject, then drain any remainder
    llm_usage = []
    for trace in traces:
        llm_usage.extend(trace.get("llm_usage") or [])
    llm_usage.extend(deps["llm"].drain_usage())
    for tier_llm in deps.get("llm_registry", {}).values():
        llm_usage.extend(tier_llm.drain_usage())
    total_cost_usd  = round(sum(u.get("cost_usd", 0)  for u in llm_usage), 6)
    total_tokens    = sum(u.get("prompt_tokens", 0) + u.get("completion_tokens", 0) for u in llm_usage)

    llm_metadata = _llm_log_fields(deps.get("llm"))
    log.info("graph_end", duration_ms=total_duration_ms,
             total_tokens=total_tokens, total_cost_usd=total_cost_usd, **llm_metadata)

    # Attach observability data to the final response meta so RunService persists it
    final_response = final_state.get("final_response", {})
    obs = {
        "run_id": run_id,
        "session_id": langfuse_metadata.get("session_id"),
        "node_traces": traces,
        "llm_usage": llm_usage,
        "total_duration_ms": total_duration_ms,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "llm_call_count": len(llm_usage),
        "replan_count": final_state.get("replan_count", 0),
        **llm_metadata,
    }
    final_response.setdefault("meta", {}).update(obs)
    final_state = {**final_state, "final_response": final_response}

    # Append debug metadata
    final_response = final_state.get("final_response", {})

    if debug:
        meta = final_response.setdefault("meta", {})
        meta.update(
            {
                "debug": True,
                "simulation_mode": simulation_mode,
                "forced_critic_decision": force_critic_decision,
                "execution_trace": final_state.get("execution_trace", []),
            }
        )

    # ── Persist results ───────────────────────────────────────────────────────
    verdict = (final_response.get("critic") or {}).get("verdict", "")

    # Semantic cache — approved runs only (prevents returning rejected plans on future hits)
    if semantic_cache and org_id and verdict == "approved" and not simulation_mode and not force_critic_decision:
        try:
            recs = final_response.get("recommendations", {})
            conditions = {
                "demand_ratio": ((recs.get("demand_forecast") or {}).get("data") or {}).get("demand_ratio"),
                "occupancy":    ((recs.get("reservation") or {}).get("data") or {}).get("occupancy_pct"),
                "shortages":    [
                    s.get("item", s) if isinstance(s, dict) else s
                    for s in (((recs.get("inventory") or {}).get("data") or {}).get("shortage_alerts") or [])[:4]
                ],
                "verdict": verdict,
            }
            semantic_cache.set(org_id, scenario, target_date, final_response, conditions=conditions)
        except Exception:
            pass

    # Planning memory — store only approved runs so insights represent validated patterns
    planning_memory = deps.get("planning_memory")
    if planning_memory and org_id and verdict == "approved" and not simulation_mode:
        try:
            run_id = final_response.get("meta", {}).get("planning_run_id")
            planning_memory.store(org_id, scenario, run_id, final_response)
        except Exception:
            pass

    return final_response


# ── SSE node names → state field mapping ─────────────────────────────────────
# ops_manager/situation_summary/final_assembler were never in this map before
# -- they ran for real but emitted zero SSE events, so the frontend loading
# pipeline had no signal at all for "understanding the scenario" or "writing
# the briefing". Added so those stages can show real start/complete events
# instead of nothing.
_NODE_SSE_MAP: dict[str, str] = {
    # CareOps hospital pipeline
    "supervisor_router":      "supervisor_router",
    "capacity_forecast":      "capacity_forecast",
    "fhir_operations":        "fhir_operations",
    "policy_rag":               "policy_rag",
    "resource_allocation":    "resource_allocation",
    "aggregator":             "aggregator",
    "safety_critic":          "safety_critic",
    "human_approval_queue":   "human_approval_queue",
    # Legacy restaurant pipeline
    "ops_manager":            "ops_manager",
    "live_signals":           "live_signals",
    "demand_forecast":        "forecast",
    "qdrant_enrichment":      "enrichment",
    "reservation":            "reservation",
    "complaint_intelligence": "complaint",
    "menu_intelligence":      "menu",
    "inventory":              "inventory",
    "market_intel":           "market_intel",
    "dineout_manager":        "dineout_manager",
    "aggregator":             "aggregator",
    "critic":                 "critic",
    "replan_orchestrator":    "replan",
    "situation_summary":      "situation_summary",
    "final_assembler":        "final_assembler",
}

_NODE_OUTPUT_FIELD: dict[str, str] = {
    "forecast":    "forecast_output",
    "reservation": "reservation_output",
    "complaint":   "complaint_output",
    "menu":        "menu_output",
    "inventory":   "inventory_output",
    "aggregator":  "aggregated_recommendation",
    "critic":      "critic_output",
}

# Human-readable hints emitted when a node STARTS — shown in the loading pipeline
_NODE_START_HINTS: dict[str, str] = {
    "supervisor_router":      "Resolving hospital scenario and target date…",
    "capacity_forecast":      "Forecasting admission volume and bed pressure…",
    "fhir_operations":        "Querying FHIR encounters, appointments, and observations…",
    "policy_rag":             "Retrieving hospital SOPs and policy citations…",
    "resource_allocation":    "Allocating beds, staff shifts, and supplies…",
    "aggregator":             "Synthesising all agent outputs into one operations plan…",
    "safety_critic":          "Scoring the plan — safety · feasibility · evidence · actionability · clarity…",
    "human_approval_queue":   "Packaging actions for human approval…",
    "ops_manager":            "Resolving the scenario, restaurant profile, and target date…",
    "live_signals":           "Checking weather, industry trends, and FSSAI notices…",
    "demand_forecast":        "Running Prophet model on 90 days of order history…",
    "qdrant_enrichment":      "Searching Qdrant memory for relevant SOPs and past incidents…",
    "reservation":            "Querying confirmed bookings and mapping peak-hour pressure…",
    "complaint_intelligence": "Analysing 28 days of guest feedback with RAG retrieval…",
    "inventory":              "Cross-referencing all ingredients against the demand forecast…",
    "menu_intelligence":      "Applying inventory constraints to build menu guidance…",
    "market_intel":           "Pulling live competitor prices and area occupancy from Swiggy…",
    "dineout_manager":        "Checking area Dineout slot availability for tonight…",
    "aggregator":             "Synthesising all agent outputs into one consolidated brief…",
    "critic":                 "Scoring the plan — safety · feasibility · evidence · actionability · clarity…",
    "replan_orchestrator":    "Critic flagged issues — injecting corrective context for retry…",
    "situation_summary":      "Writing the executive briefing…",
}


def _completion_hint(node_name: str, state_update: dict) -> str:
    """Extract a brief human-readable hint from a node's completed state update."""
    try:
        if node_name == "ops_manager":
            profile = state_update.get("scenario_profile") or {}
            label = profile.get("label")
            window = profile.get("service_window")
            target = state_update.get("target_date")
            parts = [p for p in [label, f"target {target}" if target else None, window] if p]
            return " · ".join(parts) if parts else "Scenario resolved"

        if node_name == "situation_summary":
            out = state_update.get("situation_summary_output") or {}
            if out.get("error"):
                return "Briefing skipped — falling back to a standard summary"
            return "Executive briefing written" if out.get("summary") else "Briefing complete"

        if node_name == "final_assembler":
            return "Response packaged"

        if node_name == "live_signals":
            weather    = state_update.get("weather_signal") or {}
            trends     = state_update.get("trends_signal") or {}
            compliance = state_update.get("compliance_alerts_signal") or {}
            holiday    = state_update.get("holiday_context") or {}
            parts = []
            if weather.get("condition"):
                parts.append(weather["condition"].replace("_", " "))
            if holiday.get("is_holiday"):
                parts.append(holiday.get("holiday_name") or "holiday")
            n_trends = trends.get("headline_count") or 0
            if n_trends:
                parts.append(f"{n_trends} trend headline{'s' if n_trends != 1 else ''}")
            n_notices = compliance.get("notice_count") or 0
            if n_notices:
                parts.append(f"{n_notices} FSSAI notice{'s' if n_notices != 1 else ''}")
            return " · ".join(parts) if parts else "No unusual signals today"

        if node_name == "demand_forecast":
            data = (state_update.get("forecast_output") or {}).get("data") or {}
            pred = data.get("predicted_orders") or data.get("predicted_covers")
            method = data.get("method", "")
            return f"{method} model: {round(float(pred))} predicted orders" if pred else "Forecast complete"

        if node_name == "qdrant_enrichment":
            ctx   = state_update.get("shared_context") or {}
            n_c   = len(ctx.get("complaints", []))
            n_s   = len(ctx.get("sops", []))
            n_p   = len(ctx.get("past_plans", []))
            parts = []
            if n_c:  parts.append(f"{n_c} complaint{'s' if n_c != 1 else ''}")
            if n_s:  parts.append(f"{n_s} SOP{'s' if n_s != 1 else ''}")
            if n_p:  parts.append(f"{n_p} past plan{'s' if n_p != 1 else ''}")
            return f"Memory loaded: {', '.join(parts)}" if parts else "Context loaded from memory"

        if node_name == "reservation":
            data = (state_update.get("reservation_output") or {}).get("data") or {}
            pct  = data.get("occupancy_pct")
            total = data.get("total_guests")
            cap   = data.get("capacity")
            return f"{pct}% occupancy · {total} advance bookings vs {cap} seats" if pct is not None else "Reservation analysis complete"

        if node_name == "complaint_intelligence":
            data    = (state_update.get("complaint_output") or {}).get("data") or {}
            total   = data.get("total_feedback", 0)
            neg_pct = (data.get("sentiment_breakdown") or {}).get("negative_pct", "?")
            return f"{total} feedback items · {neg_pct}% negative sentiment"

        if node_name == "inventory":
            data     = (state_update.get("inventory_output") or {}).get("data") or {}
            alerts   = data.get("shortage_alerts") or []
            n_crit   = sum(1 for a in alerts if isinstance(a, dict) and a.get("severity") == "critical")
            n_warn   = sum(1 for a in alerts if isinstance(a, dict) and a.get("severity") == "warning")
            n_items  = data.get("total_items_checked", 0)
            return f"{n_items} ingredients checked · {n_crit} critical · {n_warn} warning shortages"

        if node_name == "menu_intelligence":
            out = state_update.get("menu_output") or {}
            if out.get("error"):
                return f"Skipped — {str(out['error'])[:60]}"
            rec  = out.get("recommendation") or {}
            n_hi = len(rec.get("highlight_items") or [])
            n_bl = len(rec.get("inventory_blockers") or [])
            return f"{n_hi} items to feature · {n_bl} blocked by stock"

        if node_name == "market_intel":
            intel = state_update.get("market_intel_output") or {}
            if intel is None:
                return "Swiggy unavailable — market context skipped"
            signal   = intel.get("area_occupancy") or "?"
            n_alerts = len(intel.get("pricing_alerts") or [])
            n_opts   = len(intel.get("procurement_options") or [])
            parts = [f"Area occupancy: {signal}"]
            if n_alerts:
                parts.append(f"{n_alerts} pricing alert(s)")
            if n_opts:
                parts.append(f"{n_opts} procurement option(s)")
            return " · ".join(parts)

        if node_name == "dineout_manager":
            out = state_update.get("dineout_manager_output") or {}
            if out is None:
                return "Dineout manager skipped (no restaurant ID or Swiggy unavailable)"
            total  = out.get("total_slots_tonight", 0)
            low    = out.get("low_availability_slots", 0)
            flag   = out.get("open_more_recommended", False)
            suffix = " · open more slots recommended" if flag else ""
            return f"Your Dineout tonight: {total} slots, {low} low availability{suffix}"

        if node_name == "aggregator":
            bundle   = state_update.get("aggregated_recommendation") or {}
            agents   = bundle.get("agents") or {}
            n_ran    = sum(1 for v in agents.values() if isinstance(v, dict) and v.get("data") is not None)
            return f"Brief assembled from {n_ran} agent output(s)"

        if node_name == "critic":
            out     = state_update.get("critic_output") or {}
            verdict = out.get("verdict", "?")
            score   = out.get("score")
            sanity  = out.get("sanity_report") or {}
            n_err   = sum(1 for i in (sanity.get("issues") or []) if i.get("severity") == "error")
            score_s = f" · score {round(float(score), 2)}" if score is not None else ""
            sane_s  = f" · {n_err} sanity error(s)" if n_err else " · sanity ✓"
            return f"{verdict.capitalize()}{score_s}{sane_s}"

        if node_name == "replan_orchestrator":
            return f"Replan #{state_update.get('replan_count', 1)} context injected"

    except Exception:
        pass
    return ""


async def stream_planning_scenario(
    deps: dict[str, Any],
    scenario: str,
    target_date: str | None = None,
    simulation_mode: bool = False,
    force_critic_decision: str | None = None,
    debug: bool = False,
    org_capacity: int = 70,
    org_peak_hours: str = "18:00-22:00",
    restaurant_profile: dict | None = None,
    critic_threshold: float = 0.7,
    org_id: int | None = None,
    custom_profile: dict | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Streams planning results node-by-node for SSE delivery.

    Yields dicts:
      {"event": "node_complete", "node": str}        — as each agent finishes
      {"event": "complete",      "response": dict}   — full final response
      {"event": "error",         "message": str}     — on failure

    custom_profile: Ad-hoc natural-language-derived scenario profile (P6-A25).
    """
    traces: list[dict] = []
    graph_instance = build_graph(deps, traces=traces)

    run_id = uuid.uuid4().hex[:8]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(run_id=run_id, scenario=scenario)
    log = structlog.get_logger()

    effective_capacity   = restaurant_profile["capacity"]   if restaurant_profile else org_capacity
    effective_peak_hours = restaurant_profile["peak_hours"] if restaurant_profile else org_peak_hours

    initial_state = make_initial_state(
        scenario=scenario, target_date=target_date,
        simulation_mode=simulation_mode, force_critic_decision=force_critic_decision,
        debug=debug, restaurant_profile=restaurant_profile,
        custom_profile=custom_profile,
    )
    initial_state.update({
        "simulation_mode":        simulation_mode,
        "force_critic_decision":  force_critic_decision,
        "debug":                  debug,
        "org_id":                 org_id,
        "org_capacity":           effective_capacity,
        "org_peak_hours":         effective_peak_hours,
        "critic_threshold":       critic_threshold,
    })
    if debug:
        initial_state["execution_trace"] = []

    # Inject tier registry into state when tiered comet mode is active
    if deps.get("llm_registry"):
        initial_state["llm_registry"] = deps["llm_registry"]

    run_label = f"{scenario}/{target_date or 'next'}"
    llm_metadata = _llm_log_fields(deps.get("llm"))
    langfuse_callbacks, langfuse_metadata = _langfuse_run_context(org_id, run_id)
    config = RunnableConfig(
        run_name=f"careops/stream/{run_label}",
        tags=[scenario, "planning_run", "stream"],
        metadata={"scenario": scenario, "target_date": target_date or "", "run_id": run_id, **llm_metadata, **langfuse_metadata},
        callbacks=langfuse_callbacks,
        configurable={"thread_id": run_id},
    )

    t0 = time.perf_counter()
    log.info("stream_start", target_date=target_date or "next", **llm_metadata)

    final_response: dict | None = None
    final_replan_count = 0

    async for event in graph_instance.astream_events(initial_state, config=config, version="v2"):
        etype = event.get("event", "")
        ename = event.get("name", "")
        sse_name = _NODE_SSE_MAP.get(ename)

        if sse_name:
            if etype == "on_chain_start":
                yield {
                    "event": "node_start",
                    "node": sse_name,
                    "hint": _NODE_START_HINTS.get(ename, ""),
                }
            elif etype == "on_chain_end":
                state_update = (event.get("data") or {}).get("output") or {}
                yield {
                    "event": "node_complete",
                    "node": sse_name,
                    "hint": _completion_hint(ename, state_update if isinstance(state_update, dict) else {}),
                }

        # Independent of the sse_name branch above (not elif) -- final_assembler
        # is now also in _NODE_SSE_MAP so its node_complete event fires through
        # that branch too, but final_response still needs to be captured here
        # every time regardless.
        if ename in (FINAL_ASSEMBLER, "human_approval_queue") and etype == "on_chain_end":
            state_update = (event.get("data") or {}).get("output") or {}
            if isinstance(state_update, dict):
                final_response = state_update.get("final_response")
                final_replan_count = state_update.get("replan_count", 0)

    _flush_langfuse(langfuse_callbacks)
    total_duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    llm_usage = []
    for trace in traces:
        llm_usage.extend(trace.get("llm_usage") or [])
    llm_usage.extend(deps["llm"].drain_usage())
    for tier_llm in deps.get("llm_registry", {}).values():
        llm_usage.extend(tier_llm.drain_usage())
    total_cost_usd = round(sum(u.get("cost_usd", 0) for u in llm_usage), 6)
    total_tokens   = sum(u.get("prompt_tokens", 0) + u.get("completion_tokens", 0) for u in llm_usage)

    log.info("stream_end", duration_ms=total_duration_ms,
             total_tokens=total_tokens, total_cost_usd=total_cost_usd)

    if final_response:
        obs = {
            "run_id": run_id, "node_traces": traces,
            "llm_usage": llm_usage, "total_duration_ms": total_duration_ms,
            "total_tokens": total_tokens, "total_cost_usd": total_cost_usd,
            "llm_call_count": len(llm_usage), "replan_count": final_replan_count,
            **llm_metadata,
        }
        final_response.setdefault("meta", {}).update(obs)

        # Store approved runs in planning memory for future enrichment
        planning_memory = deps.get("planning_memory")
        stream_verdict  = (final_response.get("critic") or {}).get("verdict", "")
        if planning_memory and org_id and stream_verdict == "approved" and not simulation_mode:
            try:
                s_run_id = final_response.get("meta", {}).get("planning_run_id")
                planning_memory.store(org_id, scenario, s_run_id, final_response)
            except Exception:
                pass

        yield {"event": "complete", "response": final_response}
    else:
        yield {"event": "error", "message": "Graph completed without a final response"}

"""
Shared orchestration state for CareOps AI LangGraph workflow.

Every key uses the keep_last reducer — LangGraph requires this for ALL keys
when the graph has parallel fan-out nodes, even keys that are only written once.

Enhanced for P1-10:
- Supports simulation mode for deterministic testing
- Enables critic override for validation scenarios
- Adds debug observability and execution tracing
- Maintains backward compatibility with existing workflows
"""

from typing import TypedDict, Optional, Annotated, List, Dict, Any
from datetime import datetime, timezone


# ── Reducer ──────────────────────────────────────────────────────────────────

def keep_last(current, new):
    """Reducer: always keep the newest non-None value."""
    if new is None:
        return current
    return new


# ── Orchestration State ──────────────────────────────────────────────────────

class OrchestratorState(TypedDict):
    # Core request metadata
    scenario:     Annotated[Optional[str], keep_last]
    scenario_profile: Annotated[Optional[Dict[str, Any]], keep_last]
    # Ad-hoc natural-language-derived scenario profile (P6-A25) -- input to
    # ops_manager_node when `scenario` isn't one of the 4 presets; distinct
    # from scenario_profile, which is ops_manager_node's *resolved* output
    # (built from either a preset or this field).
    custom_profile: Annotated[Optional[Dict[str, Any]], keep_last]
    target_date:  Annotated[Optional[str], keep_last]
    requested_at: Annotated[Optional[str], keep_last]

    # Tenant identity — scopes Qdrant queries to the requesting org
    org_id: Annotated[Optional[int], keep_last]

    # Tenant settings — passed in from org config, used by agents
    org_capacity:  Annotated[Optional[int], keep_last]
    org_peak_hours: Annotated[Optional[str], keep_last]

    # Restaurant profile — overrides org defaults when restaurant_id is supplied in the request
    restaurant_profile: Annotated[Optional[Dict[str, Any]], keep_last]

    # P1-10 Testing & Simulation Controls
    simulation_mode: Annotated[Optional[bool], keep_last]
    force_critic_decision: Annotated[Optional[str], keep_last]
    debug: Annotated[Optional[bool], keep_last]

    # Domain agent outputs
    forecast_output:    Annotated[Optional[Dict[str, Any]], keep_last]
    reservation_output: Annotated[Optional[Dict[str, Any]], keep_last]
    complaint_output:   Annotated[Optional[Dict[str, Any]], keep_last]
    menu_output:        Annotated[Optional[Dict[str, Any]], keep_last]
    inventory_output:   Annotated[Optional[Dict[str, Any]], keep_last]

    # Live-intelligence signals — not Swiggy MCP, no consent/compliance
    # gating. All three populated by live_signals_node, the first node in
    # the graph (runs before demand_forecast), which demand_forecast then
    # reads back from state rather than fetching itself. market_intel_node
    # also reads them back from state (never re-fetches) and merges their
    # prompt_text alongside its own Swiggy signals into live_signals_text.
    weather_signal:            Annotated[Optional[Dict[str, Any]], keep_last]
    trends_signal:             Annotated[Optional[Dict[str, Any]], keep_last]
    compliance_alerts_signal:  Annotated[Optional[Dict[str, Any]], keep_last]
    # {"is_holiday": bool, "holiday_name": str | None} -- computed alongside
    # weather_signal by live_signals_node (same calendar lookup weather's
    # own multiplier needs), read back by demand_forecast_node.
    holiday_context:           Annotated[Optional[Dict[str, Any]], keep_last]

    # Per-node assumption dicts — populated by each domain node after its service call.
    # Used by EvaluationSanityChecker to diff cross-agent assumptions against actual state.
    menu_assumptions:        Annotated[Optional[Dict[str, Any]], keep_last]
    inventory_assumptions:   Annotated[Optional[Dict[str, Any]], keep_last]
    reservation_assumptions: Annotated[Optional[Dict[str, Any]], keep_last]
    complaint_assumptions:   Annotated[Optional[Dict[str, Any]], keep_last]

    # Aggregated intelligence
    aggregated_recommendation: Annotated[Optional[Dict[str, Any]], keep_last]

    # Critic evaluation
    critic_output: Annotated[Optional[Dict[str, Any]], keep_last]

    # Natural-language "situation + tailored key takeaways" briefing --
    # generated once, post-critic-approval, from all the other agents'
    # already-computed outputs. {"summary": "<markdown text>"} on success,
    # {"error": "..."} on failure (never raises -- frontend falls back to a
    # deterministic rendering when this is absent).
    situation_summary_output: Annotated[Optional[Dict[str, Any]], keep_last]

    # Final response returned to the API layer
    final_response: Annotated[Optional[Dict[str, Any]], keep_last]

    # Observability — always-on node timing records
    execution_trace: Annotated[Optional[List[Dict[str, Any]]], keep_last]

    # Per-node model tier routing — populated when COMET_TIERED=True
    llm_registry: Annotated[Optional[Dict[str, Any]], keep_last]

    # Replanning loop (P6-S04)
    replan_count:   Annotated[Optional[int], keep_last]
    replan_context: Annotated[Optional[str], keep_last]

    # Shared pre-enrichment context from Qdrant, populated before parallel fan-out (P6-S04)
    shared_context: Annotated[Optional[Dict[str, Any]], keep_last]

    # Swiggy enricher outputs — populated by enrichers before/during parallel fan-out (P6-S10)
    # These use consumer-facing Swiggy MCP tools (public market data) — valid for market intelligence.
    swiggy_competitor_context:  Annotated[Optional[Dict[str, Any]], keep_last]
    swiggy_occupancy_context:   Annotated[Optional[Dict[str, Any]], keep_last]
    swiggy_procurement_options: Annotated[Optional[Dict[str, Any]], keep_last]
    # FUTURE USE (needs Swiggy Partner API): intended to hold restaurant's own delivery performance
    # signal from track_food_order. Consumer MCP only returns personal delivery tracking, not
    # a restaurant's outgoing delivery metrics. Will be populated once Partner API is available.
    swiggy_delivery_signal:     Annotated[Optional[Dict[str, Any]], keep_last]

    # Swiggy node outputs — written by market_intel_node (P6-S11) and dineout_manager_node (P6-S12)
    market_intel_output:    Annotated[Optional[Dict[str, Any]], keep_last]
    dineout_manager_output: Annotated[Optional[Dict[str, Any]], keep_last]

    # Per-node assumption dicts for new nodes — used by assumption diffs 5+6 (P6-S13)
    market_intel_assumptions:    Annotated[Optional[Dict[str, Any]], keep_last]
    dineout_manager_assumptions: Annotated[Optional[Dict[str, Any]], keep_last]

    # Error handling
    error: Annotated[Optional[str], keep_last]


# ── Initial State Factory ────────────────────────────────────────────────────

def make_initial_state(
    scenario: str,
    target_date: Optional[str] = None,
    simulation_mode: bool = False,
    force_critic_decision: Optional[str] = None,
    debug: bool = False,
    restaurant_profile: Optional[Dict[str, Any]] = None,
    custom_profile: Optional[Dict[str, Any]] = None,
) -> OrchestratorState:
    """
    Build a clean initial state for a new orchestration run.

    Args:
        scenario: Name of the orchestration scenario.
        target_date: Optional ISO date string.
        simulation_mode: Enables deterministic outputs using mock data.
        force_critic_decision: Overrides critic verdict for testing.
        debug: Enables execution tracing and observability.

    Returns:
        A fully initialized OrchestratorState.
    """
    return OrchestratorState(
        # Core metadata
        scenario=scenario,
        scenario_profile=None,
        custom_profile=custom_profile,
        target_date=target_date,
        requested_at=datetime.now(timezone.utc).isoformat(),

        # P1-10 controls
        simulation_mode=simulation_mode,
        force_critic_decision=force_critic_decision,
        debug=debug,

        # Domain outputs
        forecast_output=None,
        reservation_output=None,
        complaint_output=None,
        menu_output=None,
        inventory_output=None,
        weather_signal=None,
        trends_signal=None,
        compliance_alerts_signal=None,
        holiday_context=None,

        # Per-node assumptions (populated after each domain node completes)
        menu_assumptions=None,
        inventory_assumptions=None,
        reservation_assumptions=None,
        complaint_assumptions=None,

        # Aggregated results
        aggregated_recommendation=None,
        critic_output=None,
        situation_summary_output=None,
        final_response=None,

        # Tenant identity + settings
        org_id=None,
        org_capacity=None,
        org_peak_hours=None,
        restaurant_profile=restaurant_profile,

        # Observability — always-on
        execution_trace=[],

        # Per-node model tier routing
        llm_registry=None,

        # Replanning loop
        replan_count=0,
        replan_context=None,

        # Qdrant early enrichment
        shared_context=None,

        # Swiggy enricher outputs (P6-S10)
        swiggy_competitor_context=None,
        swiggy_occupancy_context=None,
        swiggy_procurement_options=None,
        swiggy_delivery_signal=None,

        # Swiggy node outputs (P6-S11/S12)
        market_intel_output=None,
        dineout_manager_output=None,

        # Swiggy node assumption dicts (P6-S13)
        market_intel_assumptions=None,
        dineout_manager_assumptions=None,

        # Error handling
        error=None,
    )

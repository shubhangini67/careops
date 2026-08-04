"""
Final Assembler node.

Takes the critic-validated bundle and shapes it into the clean,
structured response that the Friday Rush API endpoint will return.
Writes to `final_response`.

Enhanced for P1-10:
- Adds debug metadata and execution trace
"""

from datetime import datetime, timezone

from app.orchestration.state import OrchestratorState


def final_assembler_node(state: OrchestratorState) -> OrchestratorState:
    """
    Assembles the final API response from all collected state.
    Always produces a valid final_response even if some agents errored.
    Writes to state['final_response'].
    """
    # ── Debug tracing ───────────────────────────────────────────────────────
    if state.get("debug") and state.get("execution_trace") is not None:
        state["execution_trace"].append("final_assembler")

    critic = state.get("critic_output") or {}
    bundle = state.get("aggregated_recommendation") or {}


    def _safe_rec(output: dict | None) -> dict | None:
        if not output or output.get("error"):
            return None

        recommendation = output.get("recommendation")
        if not isinstance(recommendation, dict):
            return recommendation

        # Include both data and recommendation for multi-agent outputs
        service = output.get("service")
        if output.get("data") is not None:
            return {**recommendation, "data": output["data"]}

        return recommendation

    critic_threshold = float(state.get("critic_threshold") or 0.7)

    final_response = {
        "scenario": state.get("scenario"),
        "target_date": state.get("target_date"),
        "generated_at": datetime.now(timezone.utc).isoformat(),

        # Per-agent recommendations
        "recommendations": {
            "forecast": _safe_rec(state.get("forecast_output")),
            "reservation": _safe_rec(state.get("reservation_output")),
            "complaint": _safe_rec(state.get("complaint_output")),
            "menu": _safe_rec(state.get("menu_output")),
            "inventory": _safe_rec(state.get("inventory_output")),
        },

        # Swiggy market intelligence (P6-S11/S12) — None when token not set
        "market_intel": state.get("market_intel_output"),
        "swiggy_competitor_context": state.get("swiggy_competitor_context"),
        "swiggy_occupancy_context": state.get("swiggy_occupancy_context"),
        "swiggy_procurement_options": state.get("swiggy_procurement_options"),
        "dineout_manager": state.get("dineout_manager_output"),

        # Natural-language "situation + tailored key takeaways" briefing (hero
        # content on the frontend). None when the LLM call failed open --
        # frontend falls back to its own deterministic rendering.
        "situation_summary": (state.get("situation_summary_output") or {}).get("summary"),

        # RAG evidence
        "rag_context": (
            state.get("complaint_output", {}).get("rag_context")
            if state.get("complaint_output")
            else None
        ),

        # Critic verdict
        "critic": {
            "verdict": critic.get("verdict", "unknown"),
            "score": critic.get("score", 0.0),
            "notes": critic.get("notes", ""),
            "cost_analysis": critic.get("cost_analysis"),
            "dimension_scores": critic.get("dimension_scores"),
            "revision_reasons": critic.get("revision_reasons", []),
            "actionable_feedback": critic.get("actionable_feedback", []),
            "decision_log_id": critic.get("decision_log_id"),
            "sanity_checks": critic.get("sanity_checks"),
            "stale_assumptions": critic.get("stale_assumptions", []),
        },

        # Frontend status
        "status": _derive_status(critic, critic_threshold),

        # Metadata for observability
        "meta": {
            "requested_at": state.get("requested_at"),
            "simulation_mode": state.get("simulation_mode", False),
            "debug": state.get("debug", False),
            "execution_trace": state.get("execution_trace", []),
            "scenario_profile": state.get("scenario_profile"),
        },
    }

    return {**state, "final_response": final_response}


def _derive_status(critic: dict, threshold: float = 0.7) -> str:
    """Map critic verdict + score to a simple frontend status string."""
    verdict = critic.get("verdict", "unknown")
    score = float(critic.get("score", 0.0))

    if verdict == "unknown":
        return "unknown"
    if verdict == "approved" and score >= threshold:
        return "ready"
    if verdict == "rejected":
        return "blocked"
    if verdict == "revision" or score < threshold:
        return "needs_review"
    return "unknown"

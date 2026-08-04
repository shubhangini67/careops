"""
Critic Agent node.

Validates the aggregated recommendation bundle against operational rules
using CriticService. Logs the decision to the database.
Writes to `critic_output`.

Enhanced for P1-10:
- Supports critic override for testing
- Adds debug execution tracing
"""

from sqlalchemy.orm import Session

from app.orchestration.state import OrchestratorState
from app.domain.services.critic_service import CriticService
from app.infrastructure.llm.base import BaseLLMProvider


def _safe_critic_error_message(exc: Exception) -> str:
    raw = str(exc).lower()
    if any(term in raw for term in ("rate limit", "ratelimit", "429", "quota", "too many requests")):
        return "Oops - the LLM provider is rate limited right now. Please try again in a few minutes."
    if any(term in raw for term in ("api_key", "api key", "credential", "unauthorized", "401", "403")):
        return "Oops - the LLM provider is unavailable because its credentials are not configured correctly."
    if any(term in raw for term in ("timeout", "connection", "unreachable", "temporarily unavailable", "503", "502")):
        return "Oops - the LLM provider is temporarily unavailable. Please try again shortly."
    return "Oops - the critic could not reach the LLM provider. Please try again shortly."


async def critic_node(
    state: OrchestratorState,
    db: Session,
    llm: BaseLLMProvider,
) -> OrchestratorState:
    """
    Evaluates the aggregated recommendation and logs the decision.
    Writes to state['critic_output'].
    """
    if state.get("error"):
        return state

    llm = (state.get("llm_registry") or {}).get("strong") or llm

    # ── Debug tracing ───────────────────────────────────────────────────────
    if state.get("debug") and state.get("execution_trace") is not None:
        state["execution_trace"].append("critic")

    bundle = state.get("aggregated_recommendation")
    override = state.get("force_critic_decision")

    if bundle is None:
        return {
            **state,
            "critic_output": {
                "verdict": "rejected",
                "score": 0.0,
                "notes": "No aggregated recommendation was produced — nothing to evaluate.",
            },
        }

    # ── P1-10: Critic Override for Testing ───────────────────────────────────
    if override:
        return {
            **state,
            "critic_output": {
                "verdict": override,
                "score": 1.0 if override == "approved" else 0.0,
                "notes": f"Critic decision overridden for testing: {override}.",
                "decision_log_id": None,
            },
        }

    try:
        service = CriticService(db=db, llm=llm, capacity=state.get("org_capacity") or 70)
        result = await service.evaluate_and_log(
            agent="ops_manager",
            recommendation=bundle,
            input_summary=bundle.get("summary_for_critic", ""),
            retrieved_context=str(
                bundle.get("agents", {})
                .get("complaint", {})
                .get("rag_context")
            ),
            reasoning_summary=(
                f"Multi-agent Friday rush evaluation for "
                f"{bundle.get('target_date', 'next Friday')}"
            ),
        )
        return {**state, "critic_output": result}

    except Exception as exc:
        safe_message = _safe_critic_error_message(exc)
        return {
            **state,
            "critic_output": {
                "verdict": "revision",
                "score": 0.0,
                "notes": safe_message,
                "error": "llm_unavailable",
            },
        }

"""Safety and Grounding Critic — blocks clinical advice paths, scores plan quality."""

from sqlalchemy.orm import Session

from app.domain.services.critic_service import CriticService
from app.infrastructure.llm.base import BaseLLMProvider
from app.orchestration.nodes.critic import _safe_critic_error_message
from app.orchestration.state import OrchestratorState

_CLINICAL_BLOCKLIST = (
    "diagnose", "diagnosis", "prescribe", "medication", "dosage", "treatment plan",
)


async def safety_critic_node(
    state: OrchestratorState,
    db: Session,
    llm: BaseLLMProvider,
) -> OrchestratorState:
    override = state.get("force_critic_decision")
    if override:
        verdict_map = {
            "approved": ("approved", 0.92),
            "rejected": ("rejected", 0.2),
            "revision": ("revision", 0.55),
        }
        verdict, score = verdict_map.get(override, ("revision", 0.5))
        return {
            **state,
            "critic_output": {
                "verdict": verdict,
                "score": score,
                "notes": f"Simulation override: {override}.",
            },
        }

    bundle = state.get("aggregated_recommendation") or {}
    summary = bundle.get("summary_for_critic") or str(bundle)
    lowered = summary.lower()
    if any(term in lowered for term in _CLINICAL_BLOCKLIST):
        return {
            **state,
            "critic_output": {
                "verdict": "revision",
                "score": 0.2,
                "notes": "Plan contained clinical-advice language. CareOps provides operational guidance only.",
                "grounding": "blocked_clinical_terms",
            },
        }

    if bundle is None:
        return {
            **state,
            "critic_output": {
                "verdict": "rejected",
                "score": 0.0,
                "notes": "No aggregated recommendation to evaluate.",
            },
        }

    try:
        service = CriticService(db=db, llm=llm, capacity=state.get("org_capacity") or 120)
        result = await service.evaluate_and_log(
            agent="careops_supervisor",
            recommendation=bundle,
            input_summary=summary,
            retrieved_context=str((state.get("complaint_output") or {}).get("citations", [])),
            reasoning_summary=f"Hospital operations plan for {state.get('scenario')}",
        )
        citations = (state.get("complaint_output") or {}).get("citations") or []
        if not citations:
            result = {
                **result,
                "notes": (result.get("notes") or "") + " Policy citations missing — lower confidence.",
                "score": min(float(result.get("score") or 0.5), 0.65),
            }
        return {**state, "critic_output": result}
    except Exception as exc:
        return {
            **state,
            "critic_output": {
                "verdict": "revision",
                "score": 0.0,
                "notes": _safe_critic_error_message(exc),
                "error": "llm_unavailable",
            },
        }

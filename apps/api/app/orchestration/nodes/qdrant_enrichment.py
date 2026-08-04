"""
Qdrant Early Enrichment node (P6-S04).

Runs once after demand_forecast and before the parallel domain fan-out.
Pre-fetches complaint history, SOP context, and past planning insights from Qdrant
into shared_context so all downstream agents have access without individual queries.
"""

import structlog

from app.orchestration.state import OrchestratorState

log = structlog.get_logger()


async def qdrant_enrichment_node(
    state: OrchestratorState,
    memory,
    planning_memory=None,
) -> OrchestratorState:
    """
    Pre-enrichment step: retrieves shared Qdrant context before parallel nodes run.
    Writes to state['shared_context']. Degrades gracefully — errors return empty dict.

    shared_context keys:
      complaints      : list of similar past complaints (text, score)
      sops            : list of relevant SOPs (text, score)
      past_plans      : list of recent approved planning insights with recency decay
    """
    if state.get("error"):
        return {**state, "shared_context": {}}

    if memory is None:
        return {**state, "shared_context": {}}

    org_id   = state.get("org_id") or 0
    scenario = state.get("scenario") or ""
    query    = f"{scenario} restaurant operations planning"

    try:
        complaints = memory.retrieve_similar_complaints(query, org_id, top_k=5)
        sops       = memory.retrieve_relevant_sops(query, org_id, top_k=3)
        shared: dict = {
            "complaints": complaints,
            "sops":       sops,
        }

        # Past planning insights — recency-decayed, only approved runs
        if planning_memory:
            try:
                past_plans = planning_memory.retrieve(
                    org_id=org_id,
                    scenario=scenario,
                    query=query,
                    top_k=3,
                )
                shared["past_plans"] = past_plans
            except Exception as exc:
                log.warning("planning_memory_retrieve_failed", error=str(exc))
                shared["past_plans"] = []
        else:
            shared["past_plans"] = []

        log.info(
            "qdrant_enrichment_complete",
            complaints_retrieved=len(complaints),
            sops_retrieved=len(sops),
            past_plans_retrieved=len(shared["past_plans"]),
            org_id=org_id,
        )
    except Exception as exc:
        log.warning("qdrant_enrichment_failed", error=str(exc))
        shared = {}

    return {**state, "shared_context": shared}

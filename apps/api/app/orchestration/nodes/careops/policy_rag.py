"""Policy RAG Agent — hospital SOP retrieval with citations."""

from sqlalchemy.orm import Session

from app.infrastructure.healthcare.mcp_tools import HealthcareMCPTools
from app.infrastructure.vector.memory_service import MemoryService
from app.orchestration.state import OrchestratorState


async def policy_rag_node(
    state: OrchestratorState,
    db_factory,
    memory: MemoryService | None = None,
) -> OrchestratorState:
    if state.get("simulation_mode"):
        citations = [{"id": "POLICY-SIM-1", "source": "simulation", "excerpt": "Escalate bed pressure above 85% occupancy."}]
        return {
            **state,
            "complaint_output": {
                "data": {"results": citations},
                "recommendation": "Simulation: apply bed-capacity escalation policy.",
                "rag_context": citations,
                "citations": citations,
            },
            "complaint_assumptions": {"retrieval_top_k": 1, "collection": "simulation"},
        }

    db = db_factory()
    try:
        org_id = state.get("org_id") or 1
        scenario = state.get("scenario") or "ed_surge"
        query = f"{scenario} operational policy staffing capacity escalation"
        tools = HealthcareMCPTools(db, memory=memory)
        policy_hits = tools.search_hospital_policy(query, org_id=org_id, top_k=3)
        citations = policy_hits.get("citations", [])
        excerpt = "; ".join(c["excerpt"] for c in citations[:2]) if citations else "No policy excerpts retrieved."
        recommendation = f"Apply cited hospital policies for {scenario}. Key excerpts: {excerpt}"
        return {
            **state,
            "complaint_output": {
                "data": policy_hits,
                "recommendation": recommendation,
                "rag_context": citations,
                "citations": citations,
            },
            "complaint_assumptions": {"retrieval_top_k": 3, "collection": "sop_memory"},
        }
    finally:
        db.close()

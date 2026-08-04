"""Human Approval Queue — routes low-confidence or sensitive actions for review."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.infrastructure.healthcare.mcp_tools import HealthcareMCPTools
from app.orchestration.state import OrchestratorState


async def human_approval_queue_node(state: OrchestratorState, db_session: Session) -> OrchestratorState:
    org_id = state.get("org_id") or 1
    critic = state.get("critic_output") or {}
    score = float(critic.get("score") or 0.5)
    simulation = state.get("simulation_mode", False)

    pending_actions = []
    if not simulation:
        tools = HealthcareMCPTools(db_session)
        shortages = (state.get("inventory_output") or {}).get("data", {}).get("supply_shortages", {})
        if shortages.get("count", 0) > 0:
            pending_actions.append(tools.create_review_action(
                org_id=org_id,
                title="Review critical supply reorder",
                description="Supply levels below threshold — human approval required before procurement.",
                category="supply_reorder",
                confidence=score,
            ))

        if score < 0.75 or critic.get("verdict") != "approved":
            pending_actions.append(tools.create_review_action(
                org_id=org_id,
                title="Review hospital operations plan",
                description="Critic flagged plan for human review before execution.",
                category="operations_plan_review",
                confidence=score,
            ))

    citations = (state.get("complaint_output") or {}).get("citations") or []
    verdict = critic.get("verdict")
    if verdict == "rejected":
        status = "blocked"
    elif verdict == "revision" or score < 0.75:
        status = "needs_review"
    else:
        status = "ready"

    bundle = state.get("aggregated_recommendation") or {}
    response = {
        "scenario": state.get("scenario"),
        "target_date": state.get("target_date"),
        "status": status,
        "critic": critic,
        "recommendations": bundle.get("agents") or bundle,
        "policy_citations": citations,
        "pending_actions": pending_actions,
        "rag_context": {"policy_citations": citations},
        "disclaimer": "Operational guidance only. Not medical diagnosis or treatment advice.",
        "generated_at": state.get("requested_at") or datetime.now(timezone.utc).isoformat(),
    }
    return {**state, "final_response": response, "situation_summary_output": {
        "summary": f"Hospital operations plan for {state.get('scenario')} — status {response['status']}.",
    }}

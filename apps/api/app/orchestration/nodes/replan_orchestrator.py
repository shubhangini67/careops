"""
Replan Orchestrator node (P6-S04).

Triggered when the Critic returns 'rejected' or 'revision' and replan_count < 2.
Accumulates the critic's feedback into replan_context, which menu_intelligence_node
then threads into its prompt as prior_feedback on the next pass — so retries
actually regenerate the plan instead of resubmitting the same one.
"""

from app.orchestration.state import OrchestratorState


def replan_orchestrator_node(state: OrchestratorState) -> OrchestratorState:
    """
    Handles critic-driven replanning. Increments retry count, accumulates critic
    feedback into replan_context for menu_intelligence_node to act on next pass.
    Max 2 retries — enforced by the graph's conditional routing, not here.
    """
    critic_out = state.get("critic_output") or {}
    revision_reasons  = critic_out.get("revision_reasons") or []
    actionable_feedback = critic_out.get("actionable_feedback") or ""
    verdict           = critic_out.get("verdict", "revision")
    score             = critic_out.get("score", 0.0)

    prev_count   = state.get("replan_count") or 0
    prev_context = state.get("replan_context") or ""

    attempt_lines = [
        f"[Replan attempt {prev_count + 1}] Critic verdict: {verdict} (score={score})",
    ]
    if revision_reasons:
        attempt_lines.append(f"  Revision reasons: {'; '.join(revision_reasons)}")
    if actionable_feedback:
        attempt_lines.append(f"  Actionable feedback: {actionable_feedback}")

    new_context = "\n".join(
        filter(None, [prev_context, "\n".join(attempt_lines)])
    )

    # Note: no "critic_output": None here — every OrchestratorState field uses the
    # keep_last reducer (if new is None: return current), so that would be a no-op
    # anyway. critic_node overwrites critic_output unconditionally on its next run.
    return {
        **state,
        "replan_count":  prev_count + 1,
        "replan_context": new_context,
    }

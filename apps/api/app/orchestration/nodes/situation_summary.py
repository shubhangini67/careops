"""Situation Summary Agent node.

Writes the natural-language "situation + tailored key takeaways" briefing shown as the hero
on the frontend results page, ahead of any individual specialist's own output. Runs exactly
once, after the critic has approved the plan (never mid-revision-loop -- wired in graph.py to
fire only on the critic's FINAL_ASSEMBLER branch), reading every other agent's already-computed
output straight from state -- no new data fetching, no re-running anything upstream.

Never raises: on any failure this writes {"error": ...} to situation_summary_output and the
frontend falls back to its own deterministic rendering, matching every other node's fail-open
convention in this codebase.
"""

from app.orchestration.state import OrchestratorState
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.prompt_utils import PromptUtils


def _forecast_summary(state: OrchestratorState) -> str:
    fc = (state.get("forecast_output") or {}).get("data") or {}
    predicted = fc.get("predicted_orders")
    if predicted is None:
        return "No forecast available."
    avg = fc.get("avg_friday_orders") or fc.get("avg_same_day_orders")
    if avg:
        diff_pct = round(((predicted - avg) / avg) * 100)
        return f"{predicted} orders predicted ({diff_pct:+d}% vs the usual average of {avg})."
    return f"{predicted} orders predicted."


def _reservation_summary(state: OrchestratorState) -> str:
    r = (state.get("reservation_output") or {}).get("data") or {}
    occupancy = r.get("occupancy_pct")
    if occupancy is None:
        return "No reservation data available."
    guests = r.get("total_guests")
    waitlist = r.get("waitlist_count") or 0
    parts = [f"{round(occupancy)}% of capacity booked"]
    if guests:
        parts.append(f"{guests} guests")
    if waitlist:
        parts.append(f"{waitlist} on the waitlist")
    return ", ".join(parts) + "."


def _inventory_summary(state: OrchestratorState) -> str:
    inv = (state.get("inventory_output") or {}).get("data") or {}
    alerts = inv.get("shortage_alerts") or []
    critical = [a.get("ingredient") for a in alerts if a.get("severity") == "critical" and a.get("ingredient")]
    if not critical:
        return "No critical ingredient shortages right now."
    return f"Critically low on: {', '.join(critical)}."


def _complaint_summary(state: OrchestratorState) -> str:
    c = state.get("complaint_output") or {}
    data = c.get("data") or {}
    sentiment = data.get("sentiment_breakdown") or {}
    negative_pct = sentiment.get("negative_pct")
    issues = c.get("issues") or []
    top_issue = issues[0].get("issue") if issues and isinstance(issues[0], dict) else None
    if negative_pct is None:
        return "No recent guest feedback data available."
    parts = [f"{round(negative_pct)}% of recent feedback is negative"]
    if top_issue:
        parts.append(f"top recurring issue: {top_issue}")
    return ", ".join(parts) + "."


def _menu_summary(state: OrchestratorState) -> str:
    m = state.get("menu_output") or {}
    highlights = m.get("highlight_items") or []
    blockers = m.get("inventory_blockers") or []
    if not highlights:
        return "No menu recommendation available."
    parts = [f"Recommending: {', '.join(highlights)}"]
    if blockers:
        parts.append(f"blocked by stock: {'; '.join(blockers)}")
    return ". ".join(parts) + "."


async def situation_summary_node(
    state: OrchestratorState,
    llm: BaseLLMProvider,
) -> OrchestratorState:
    """Writes state['situation_summary_output']."""
    if state.get("error"):
        return state

    llm = (state.get("llm_registry") or {}).get("strong") or llm

    scenario_profile = state.get("scenario_profile") or {}
    market_intel = state.get("market_intel_output") or {}

    try:
        prompt = PromptUtils.format_situation_summary_prompt(
            scenario_label=scenario_profile.get("label") or state.get("scenario") or "Service",
            operational_focus=scenario_profile.get("operational_focus") or "",
            target_date=state.get("target_date") or "next service",
            service_window=scenario_profile.get("service_window") or "18:00-22:00",
            forecast_summary=_forecast_summary(state),
            reservation_summary=_reservation_summary(state),
            inventory_summary=_inventory_summary(state),
            complaint_summary=_complaint_summary(state),
            menu_summary=_menu_summary(state),
            live_signals_text=market_intel.get("live_signals_text") or "",
        )
        summary = await llm.complete(
            prompt=prompt,
            system_prompt=PromptUtils.SYSTEM_SITUATION_SUMMARY_AGENT,
        )
        return {**state, "situation_summary_output": {"summary": summary.strip()}}
    except Exception as exc:
        return {**state, "situation_summary_output": {"error": str(exc)}}

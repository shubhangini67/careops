"""True node re-execution support for Kindred replay (P6-A27 follow-up).

Kindred sends back the exact [system, user] messages captured for one node's
LLM generation, with no node name attached. Every node's system prompt is a
fixed constant in PromptUtils, so the incoming system prompt is matched
against those constants to identify which node this replay refers to.

Once identified, the node's pre-execution state is reconstructed from the
LangGraph checkpoint saved right before that node ran, and the node's
CURRENT code is called directly against that state -- this is what lets a
replay catch a real prompt/logic regression, not just LLM sampling variance
(the gap docs/PRODUCT_MODES.md's P6-A27 note flagged as deliberately
unbuilt). Falls back to None at every step (unmatched prompt, missing
checkpoint, no checkpointer) so callers can fall back to the older
raw-LLM-call replay rather than erroring.

Checkpoint reconstruction relies on the `branch:to:<node>` channel key
LangGraph writes into channel_values for the checkpoint immediately
preceding that node's execution -- verified live against the installed
langgraph-checkpoint-postgres version in this repo's venv, not documented
public API. Re-verify this against a real checkpoint dump if langgraph is
ever upgraded.
"""

from typing import Any

from app.infrastructure.llm.prompt_utils import PromptUtils
from app.orchestration.nodes.critic import critic_node
from app.orchestration.nodes.complaint_intelligence import complaint_intelligence_node
from app.orchestration.nodes.demand_forecast import demand_forecast_node
from app.orchestration.nodes.inventory import inventory_node
from app.orchestration.nodes.menu_intelligence import menu_intelligence_node
from app.orchestration.nodes.reservation import reservation_node

# Only nodes that call the LLM directly with a fixed system prompt are
# replayable this way -- market_intel/dineout_manager/ops_manager/aggregator/
# live_signals/qdrant_enrichment/replan_orchestrator/final_assembler don't
# (narrative-only or pure orchestration), so they're not in this map.
NODE_SYSTEM_PROMPTS: dict[str, str] = {
    "reservation":            PromptUtils.SYSTEM_RESERVATION_AGENT,
    "demand_forecast":        PromptUtils.SYSTEM_DEMAND_FORECAST_AGENT,
    "complaint_intelligence": PromptUtils.SYSTEM_COMPLAINT_AGENT,
    "menu_intelligence":      PromptUtils.SYSTEM_MENU_AGENT,
    "inventory":              PromptUtils.SYSTEM_INVENTORY_AGENT,
    "critic":                 PromptUtils.SYSTEM_CRITIC_AGENT,
}

NODE_OUTPUT_KEY: dict[str, str] = {
    "reservation":            "reservation_output",
    "demand_forecast":        "forecast_output",
    "complaint_intelligence": "complaint_output",
    "menu_intelligence":      "menu_output",
    "inventory":              "inventory_output",
    "critic":                 "critic_output",
}


def identify_node(system_content: str | None) -> str | None:
    """Match an incoming system prompt against known node prompts.

    Containment, not equality: every node calls llm.complete_json(), and
    every provider's complete_json() prepends a fixed
    "You must respond with valid JSON only..." instruction ahead of the
    real system_prompt (see groq.py/gemini.py/comet.py's identical
    `combined_system = f"{json_system}\n{system_prompt}"`) before it ever
    reaches the LLM -- so what Kindred captures and replays back is always
    that prefix + the raw node prompt, never the raw prompt alone. An
    exact-equality check here would silently never match any node."""
    if not system_content:
        return None
    normalized = system_content.strip()
    for node_name, prompt in NODE_SYSTEM_PROMPTS.items():
        if prompt.strip() in normalized:
            return node_name
    return None


async def fetch_pre_node_state(checkpointer, thread_id: str, node_name: str) -> dict[str, Any] | None:
    """Return the OrchestratorState snapshot captured immediately before
    node_name ran in the given thread, or None if no such checkpoint exists
    (unknown thread, node never ran, or checkpointer unavailable)."""
    if checkpointer is None:
        return None

    branch_key = f"branch:to:{node_name}"
    config = {"configurable": {"thread_id": thread_id}}
    async for tup in checkpointer.alist(config):
        channel_values = (tup.checkpoint or {}).get("channel_values") or {}
        if branch_key in channel_values:
            return {
                k: v for k, v in channel_values.items()
                if k != "__start__" and not k.startswith("branch:to:")
            }
    return None


async def reexecute_node(node_name: str, state: dict[str, Any], deps: dict[str, Any]) -> Any:
    """Call node_name's current code directly against a reconstructed state,
    bypassing the graph runner entirely -- re-runs exactly one node, never
    its downstream neighbours, so this never re-triggers the rest of the
    pipeline or its LLM cost."""
    if node_name == "reservation":
        result = await reservation_node(state, db_factory=deps["db_factory"], llm=deps["llm"])
    elif node_name == "demand_forecast":
        result = await demand_forecast_node(state, db=deps["db"], llm=deps["llm"])
    elif node_name == "complaint_intelligence":
        result = await complaint_intelligence_node(
            state, db_factory=deps["db_factory"], llm=deps["llm"], memory=deps.get("memory"),
        )
    elif node_name == "menu_intelligence":
        result = await menu_intelligence_node(state, db=deps["db"], llm=deps["llm"])
    elif node_name == "inventory":
        result = await inventory_node(
            state, db_factory=deps["db_factory"], llm=deps["llm"], swiggy_client=deps.get("swiggy_client"),
        )
    elif node_name == "critic":
        result = await critic_node(state, db=deps["db"], llm=deps["llm"])
    else:
        return None

    return result.get(NODE_OUTPUT_KEY[node_name])

"""CareOps AI LangGraph — 7-agent hospital operations pipeline."""

from typing import Any

from langgraph.graph import END, StateGraph

from app.orchestration.graph import _inject, _log_node
from app.orchestration.nodes.aggregator import aggregator_node
from app.orchestration.nodes.careops.capacity_forecast import capacity_forecast_node
from app.orchestration.nodes.careops.fhir_operations import fhir_operations_node
from app.orchestration.nodes.careops.human_approval_queue import human_approval_queue_node
from app.orchestration.nodes.careops.policy_rag import policy_rag_node
from app.orchestration.nodes.careops.resource_allocation import resource_allocation_node
from app.orchestration.nodes.careops.safety_critic import safety_critic_node
from app.orchestration.nodes.careops.supervisor_router import supervisor_router_node
from app.orchestration.state import OrchestratorState

SUPERVISOR = "supervisor_router"
CAPACITY_FORECAST = "capacity_forecast"
FHIR_OPERATIONS = "fhir_operations"
POLICY_RAG = "policy_rag"
RESOURCE_ALLOCATION = "resource_allocation"
AGGREGATOR = "aggregator"
SAFETY_CRITIC = "safety_critic"
HUMAN_APPROVAL = "human_approval_queue"


def _route_after_supervisor(state: OrchestratorState) -> str:
    return CAPACITY_FORECAST if not state.get("error") else HUMAN_APPROVAL


def build_careops_graph(deps: dict[str, Any], traces: list | None = None):
    db = deps["db"]
    llm = deps["llm"]
    memory = deps.get("memory")
    db_factory = deps.get("db_factory")
    if db_factory is None:
        from app.api.dependencies import get_db_factory
        db_factory = get_db_factory()
    tr = traces if traces is not None else []

    graph = StateGraph(OrchestratorState)

    graph.add_node(SUPERVISOR, _inject(supervisor_router_node, tr))
    graph.add_node(CAPACITY_FORECAST, _inject(capacity_forecast_node, tr, db_session=db))
    graph.add_node(FHIR_OPERATIONS, _inject(fhir_operations_node, tr, db_factory=db_factory))
    graph.add_node(POLICY_RAG, _inject(policy_rag_node, tr, db_factory=db_factory, memory=memory))
    graph.add_node(RESOURCE_ALLOCATION, _inject(resource_allocation_node, tr, db_factory=db_factory))
    graph.add_node(AGGREGATOR, _log_node(aggregator_node, tr))
    graph.add_node(SAFETY_CRITIC, _inject(safety_critic_node, tr, db=db, llm=llm))
    graph.add_node(HUMAN_APPROVAL, _inject(human_approval_queue_node, tr, db_session=db))

    graph.set_entry_point(SUPERVISOR)
    graph.add_conditional_edges(SUPERVISOR, _route_after_supervisor, {
        CAPACITY_FORECAST: CAPACITY_FORECAST,
        HUMAN_APPROVAL: HUMAN_APPROVAL,
    })
    graph.add_edge(CAPACITY_FORECAST, FHIR_OPERATIONS)
    graph.add_edge(CAPACITY_FORECAST, POLICY_RAG)
    graph.add_edge(CAPACITY_FORECAST, RESOURCE_ALLOCATION)
    graph.add_edge(FHIR_OPERATIONS, AGGREGATOR)
    graph.add_edge(POLICY_RAG, AGGREGATOR)
    graph.add_edge(RESOURCE_ALLOCATION, AGGREGATOR)
    graph.add_edge(AGGREGATOR, SAFETY_CRITIC)
    graph.add_edge(SAFETY_CRITIC, HUMAN_APPROVAL)
    graph.add_edge(HUMAN_APPROVAL, END)

    checkpointer = deps.get("checkpointer")
    return graph.compile(checkpointer=checkpointer)

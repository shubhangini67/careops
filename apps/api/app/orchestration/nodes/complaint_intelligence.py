"""
Complaint Intelligence Agent node.

Uses ComplaintService for DB-backed analysis AND MemoryService for
RAG retrieval of similar past complaints and relevant SOPs.
Writes to `complaint_output`.
"""

import asyncio
from datetime import datetime
from typing import Callable

from app.orchestration.state import OrchestratorState
from app.domain.services.complaint_service import ComplaintService
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.vector.memory_service import MemoryService


async def complaint_intelligence_node(
    state: OrchestratorState,
    db_factory: Callable,
    llm: BaseLLMProvider,
    memory: MemoryService | None = None,
) -> OrchestratorState:
    """
    Summarises complaints, retrieves similar past issues via RAG,
    and surfaces relevant SOPs. Writes to state['complaint_output'].

    Uses db_factory (not a shared Session) so the sync DB query inside
    ComplaintService runs in asyncio.to_thread() without blocking other
    parallel fan-out nodes.
    """
    if state.get("error"):
        return state

    llm = (state.get("llm_registry") or {}).get("balanced") or llm

    session = db_factory()
    try:
        service = ComplaintService(db=session, llm=llm)
        target_date = (
            datetime.fromisoformat(state["target_date"])
            if state.get("target_date")
            else None
        )

        # RAG retrieval happens BEFORE the LLM call so context feeds the prompt.
        # get_complaint_summary() is sync DB — run it in a thread for the RAG query.
        rag_context: dict = {"similar_complaints": [], "relevant_sops": []}
        if memory is not None:
            org_id = state.get("org_id")
            summary = await asyncio.to_thread(service.get_complaint_summary, 28)
            top_complaint = (summary.get("unique_complaints") or ["slow service"])[0]
            if org_id is not None:
                rag_context["similar_complaints"] = memory.retrieve_similar_complaints(
                    query=top_complaint, org_id=org_id, top_k=3
                )
                rag_context["relevant_sops"] = memory.retrieve_relevant_sops(
                    query=top_complaint, org_id=org_id, top_k=2
                )

        result = await service.analyse_and_recommend(
            days=28,
            scenario_profile=state.get("scenario_profile"),
            target_date=target_date,
            rag_context=rag_context,
        )

        result["rag_context"] = rag_context
        data = result.get("data") or {}
        sentiment = data.get("sentiment_breakdown") or {}
        negative_pct = float(sentiment.get("negative_pct") or 0)
        return {
            **state,
            "complaint_output": result,
            "complaint_assumptions": {
                "assumed_complaint_categories": (data.get("unique_complaints") or [])[:5],
                "assumed_high_complaint_volume": negative_pct > 30.0,
                "assumed_negative_pct": negative_pct,
            },
        }

    except Exception as exc:
        return {
            **state,
            "complaint_output": {
                "service": "complaint",
                "error": str(exc),
                "data": None,
                "recommendation": None,
                "rag_context": {},
            },
            "complaint_assumptions": None,
        }
    finally:
        session.close()

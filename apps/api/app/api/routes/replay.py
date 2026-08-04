"""Kindred replay endpoint (P6-A27, true re-execution added as a follow-up).

Not versioned under /api/v1 — Kindred's Configure Replay URL convention
expects a bare /replay path, so this router is mounted directly on the app
in main.py rather than through get_api_router().

Kindred replays at the level of a SINGLE agent step (one LLM generation),
not a whole planning run — confirmed from real request logs: it sends back
exactly the `messages` array ([system, user]) captured for one observation
inside a trace (e.g. just the critic node's call), not the graph's root
input. An earlier version of this endpoint mistakenly ran the full pipeline
(6+ LLM calls) per replay when it didn't recognize the input shape — do not
reintroduce that: it silently burns real LLM quota per Kindred click.

Two replay paths now exist:
1. True node re-execution (preferred): identify which node the incoming
   system prompt belongs to (app.orchestration.replay_support), fetch that
   node's pre-execution state from the checkpoint saved right before it ran
   in the original run's thread, and call the node's CURRENT code directly.
   This is what actually catches a real prompt/logic regression, not just
   LLM sampling variance. Requires a checkpointer, an identifiable node
   prompt, and a matching checkpoint — any of which can be absent.
2. Raw LLM-call replay (fallback): reuses BaseLLMProvider.complete() with
   the same [system, user] messages, exactly as before this follow-up.
   Always available, always the safety net when (1) can't apply.
"""

import json
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.dependencies import get_checkpointer, get_db_factory, get_llm, get_memory

router = APIRouter(tags=["replay"])


def _coerce_bool(value) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    return str(value).strip().lower() == "true"


def _extract_system_and_user(messages: list) -> tuple[str | None, str | None]:
    """Mirror BaseLLMProvider.complete()'s own message shape: one system
    message (if any) + the last user message. This is the same [system, user]
    pairing every node's complete()/complete_json() call already builds, so
    replaying it this way reproduces the original call faithfully."""
    system_content = None
    user_content = None
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role == "system" and content and system_content is None:
            system_content = str(content)
        elif role == "user" and content:
            user_content = str(content)
    return system_content, user_content


@router.post(
    "/replay",
    summary="Kindred replay endpoint — reruns one agent step through the real LLM call path",
)
async def replay_turn(
    request: Request,
    llm=Depends(get_llm),
    checkpointer=Depends(get_checkpointer),
    x_kindred_replay: str | None = Header(default=None, alias="X-Kindred-Replay"),
    x_kindred_replay_run_id: str | None = Header(default=None, alias="X-Kindred-Replay-Run-Id"),
    x_kindred_original_session_id: str | None = Header(default=None, alias="X-Kindred-Original-Session-Id"),
    x_kindred_turn_trace_id: str | None = Header(default=None, alias="X-Kindred-Turn-Trace-Id"),
    x_kindred_include_prior_context: str | None = Header(default=None, alias="X-Kindred-Include-Prior-Context"),
) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be a JSON object.",
        )
    structlog.get_logger().info("kindred_replay_request_received", body_keys=list(body.keys()))

    # Replay metadata: body fields take precedence, headers fill in the rest.
    kindred_replay_run_id = body.get("kindred_replay_run_id") or x_kindred_replay_run_id
    kindred_original_session_id = (
        body.get("kindred_original_session_id") or x_kindred_original_session_id
    )
    kindred_turn_trace_id = body.get("kindred_turn_trace_id") or x_kindred_turn_trace_id
    kindred_include_prior_context = body.get("kindred_include_prior_context")
    if kindred_include_prior_context is None:
        kindred_include_prior_context = _coerce_bool(x_kindred_include_prior_context)
    is_replay = body.get("is_replay")
    if is_replay is None:
        is_replay = bool(_coerce_bool(x_kindred_replay)) or bool(kindred_replay_run_id)

    # Prefer `messages` (the observed real contract) over a plain string `input`.
    messages = body.get("messages")
    system_content = user_content = None
    if isinstance(messages, list) and messages:
        system_content, user_content = _extract_system_and_user(messages)
    if user_content is None:
        raw_input = body.get("input")
        if isinstance(raw_input, str) and raw_input.strip():
            user_content = raw_input

    if user_content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must include a 'messages' array with a user message, or a string 'input'.",
        )

    run_id = uuid.uuid4().hex[:8]
    session_id = kindred_original_session_id or body.get("session_id") or run_id

    from app.core.settings import get_settings
    settings = get_settings()

    replay_metadata = {
        "agent_id": settings.kindred_agent_id,
        "is_replay": bool(is_replay),
        "kindred_replay_run_id": kindred_replay_run_id,
        "kindred_original_session_id": kindred_original_session_id,
        "kindred_include_prior_context": kindred_include_prior_context,
        "kindred_turn_trace_id": kindred_turn_trace_id,
    }

    # ── Attempt true node re-execution first -- falls through to the raw LLM
    # replay below on any failure or miss (unmatched prompt, no checkpoint,
    # no checkpointer). Never lets this path 500 the request. ──
    node_reexecuted = None
    reexecuted_output = None
    if checkpointer is not None and kindred_original_session_id:
        try:
            from app.orchestration.replay_support import (
                fetch_pre_node_state, identify_node, reexecute_node,
            )
            node_name = identify_node(system_content)
            if node_name:
                pre_state = await fetch_pre_node_state(checkpointer, kindred_original_session_id, node_name)
                if pre_state is not None:
                    from app.infrastructure.swiggy.client import SwiggyMCPClient

                    db_factory = get_db_factory()
                    db_session = db_factory()
                    try:
                        node_deps = {
                            "db": db_session,
                            "db_factory": db_factory,
                            "llm": llm,
                            "memory": get_memory(),
                            "swiggy_client": SwiggyMCPClient(),
                        }
                        reexecuted_output = await reexecute_node(node_name, pre_state, node_deps)
                    finally:
                        db_session.close()
                    if reexecuted_output is not None:
                        node_reexecuted = node_name
        except Exception as exc:
            # str(exc) only, no exc_info -- see dependencies.py's get_checkpointer()
            # for why: a raw traceback can crash structlog's Windows console
            # print (cp1252 encoding), masking the real error entirely.
            try:
                structlog.get_logger().warning("kindred_true_reexecution_failed", error=str(exc)[:300])
            except Exception:
                pass

    if node_reexecuted:
        return {
            "session_id": session_id,
            "run_id": run_id,
            "kindred_replay_run_id": kindred_replay_run_id,
            "node_reexecuted": node_reexecuted,
            "output": json.dumps(reexecuted_output, default=str),
        }

    try:
        if settings.langfuse_secret_key:
            from langfuse import get_client, propagate_attributes

            with propagate_attributes(
                session_id=session_id,
                metadata={k: v for k, v in replay_metadata.items() if v is not None},
            ):
                output_text = await llm.complete(prompt=user_content, system_prompt=system_content)
            try:
                get_client().flush()
            except Exception:
                pass
        else:
            output_text = await llm.complete(prompt=user_content, system_prompt=system_content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Replay LLM call failed: {exc}",
        )

    return {
        "session_id": session_id,
        "run_id": run_id,
        "kindred_replay_run_id": kindred_replay_run_id,
        "output": output_text,
    }

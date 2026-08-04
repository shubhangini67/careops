"""P5-12 RAG chatbot endpoint — P6-S04: agentic tool use, cross-session memory,
proactive patterns, semantic cache. P6-A1: real conversation persistence
(ChatSession/ChatMessage) — history was previously frontend-only, sent up fresh
on every request and never stored server-side beyond a compressed Qdrant summary."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_db,
    get_db_factory,
    get_memory,
    get_chat_cache,
    get_session_memory,
)
from app.api.schemas.chat import ChatRequest, ChatSessionSummary, ChatSessionDetail, ChatMessage as ChatMessageSchema
from app.domain.services.chat_service import build_context, stream_reply
from app.infrastructure.db.models import Organization, ChatSession, ChatMessage
from app.infrastructure.vector.session_memory import SessionMemoryService

router = APIRouter(prefix="/chat", tags=["chat"])


def _make_title(question: str) -> str:
    question = question.strip()
    return question[:60] + ("…" if len(question) > 60 else "")


@router.post("", summary="Agentic RAG chatbot over run history")
async def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    db_factory=Depends(get_db_factory),
    current_user: dict = Depends(get_current_user),
    memory=Depends(get_memory),
    chat_cache=Depends(get_chat_cache),
    session_memory=Depends(get_session_memory),
) -> StreamingResponse:
    org_id  = current_user["org_id"]
    user_id = current_user["user_id"]

    org = db.query(Organization).filter(Organization.id == org_id).first()
    org_name = org.name if org else "your restaurant"

    history = [{"role": m.role, "content": m.content} for m in body.history]

    # P6-A1: resume an existing persisted session, or start a new one
    if body.session_id is not None:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == body.session_id, ChatSession.org_id == org_id, ChatSession.user_id == user_id)
            .first()
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found.")
    else:
        session = ChatSession(org_id=org_id, user_id=user_id, title=_make_title(body.question))
        db.add(session)
        db.commit()
        db.refresh(session)

    db.add(ChatMessage(session_id=session.id, role="user", content=body.question))
    db.commit()

    # Captured as a plain int now, while `db` is still open -- the generator
    # below runs AFTER this endpoint function returns (StreamingResponse
    # iterates it lazily), by which point FastAPI has already closed `db` via
    # get_db()'s dependency teardown. Touching the `session` ORM object
    # itself inside the generator throws "Instance is not bound to a
    # Session" (confirmed live) since db.commit() above expires its
    # attributes, forcing a lazy DB refresh against an already-closed
    # session. The generator opens its own independent session via
    # db_factory() instead, alive for exactly its own lifetime.
    session_id = session.id

    system_prompt = build_context(
        org_id=org_id,
        org_name=org_name,
        question=body.question,
        db=db,
        memory=memory,
        session_memory=session_memory,
        user_id=user_id,
    )

    async def event_generator():
        full_tokens: list[str] = []
        gen_db = db_factory()
        try:
            yield f"data: {json.dumps({'session_id': session_id})}\n\n"
            async for token in stream_reply(
                question=body.question,
                history=history,
                system_prompt=system_prompt,
                db=gen_db,
                org_id=org_id,
                chat_cache=chat_cache,
                user_id=user_id,
            ):
                full_tokens.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:
            # Chat bypasses the app's usual Groq->Gemini FallbackLLMProvider
            # (streaming + ReAct tool calls aren't wired into that abstraction),
            # so a Groq rate limit surfaces as a raw provider exception here --
            # confirmed live: "Error code: 413 ... 'code': 'rate_limit_exceeded'"
            # leaking straight to the chat bubble as an ugly JSON/Python string.
            # Detect it by content (varies by exact SDK exception class/status
            # code) and give a clean, actionable message instead; anything else
            # still surfaces its real message for debugging.
            msg = str(exc)
            if "rate_limit" in msg.lower() or "tokens per minute" in msg.lower():
                friendly = "I'm being rate-limited by the AI provider right now (too many requests/tokens per minute on the free tier). Please wait a moment and try again, or ask a shorter question."
            else:
                friendly = msg
            yield f"data: {json.dumps({'error': friendly})}\n\n"
        finally:
            yield f"data: {json.dumps({'done': True})}\n\n"

            # P6-A1: persist the assistant's reply and bump the session's updated_at
            if full_tokens:
                try:
                    gen_db.add(ChatMessage(session_id=session_id, role="assistant", content="".join(full_tokens)))
                    gen_session = gen_db.query(ChatSession).filter(ChatSession.id == session_id).first()
                    if gen_session is not None:
                        gen_session.updated_at = datetime.utcnow()
                    gen_db.commit()
                except Exception:
                    gen_db.rollback()
            gen_db.close()

            # Store session summary after the conversation turn completes
            if session_memory and full_tokens:
                try:
                    summary = SessionMemoryService.build_summary_from_messages(
                        messages=history + [
                            {"role": "user",      "content": body.question},
                            {"role": "assistant", "content": "".join(full_tokens)},
                        ],
                        question=body.question,
                    )
                    session_memory.store_session(
                        org_id=org_id,
                        user_id=user_id,
                        summary=summary,
                        message_count=len(history) + 2,
                    )
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions", response_model=list[ChatSessionSummary], summary="List past chat conversation threads")
async def list_chat_sessions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[ChatSessionSummary]:
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.org_id == current_user["org_id"], ChatSession.user_id == current_user["user_id"])
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
        .all()
    )
    return [
        ChatSessionSummary(
            id=s.id,
            title=s.title,
            message_count=len(s.messages),
            updated_at=s.updated_at.isoformat() if s.updated_at else s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail, summary="Fetch one conversation thread's full history")
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ChatSessionDetail:
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.org_id == current_user["org_id"],
            ChatSession.user_id == current_user["user_id"],
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")

    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        messages=[ChatMessageSchema(role=m.role, content=m.content) for m in session.messages],
    )


@router.delete("/sessions/{session_id}", status_code=204, summary="Delete one conversation thread")
async def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.org_id == current_user["org_id"],
            ChatSession.user_id == current_user["user_id"],
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")

    # ORM delete (not a bulk .delete() query) so ChatSession's
    # cascade="all, delete-orphan" relationship actually removes the
    # session's ChatMessage rows too, not just the session itself.
    db.delete(session)
    db.commit()

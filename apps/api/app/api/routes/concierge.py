"""Phase 6A-34 (originally scoped as Phase 6B): Guest Concierge API routes.

Consumer-facing, no auth -- deliberately does not depend on get_current_user
or any restaurant-operator data. Session state lives entirely in Redis
(ConciergeService), not the DB -- there's no user account to own it.
"""

import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.settings import get_settings
from app.domain.services.concierge_service import ConciergeService
from app.infrastructure.llm.audio_transcription import transcribe as transcribe_audio

router = APIRouter(prefix="/concierge", tags=["concierge"])

_service = ConciergeService()


class ConciergeChatRequest(BaseModel):
    session_id: str | None = None
    message: str


@router.post("/chat", summary="Send a message to the Guest Concierge (streaming)")
async def concierge_chat(body: ConciergeChatRequest) -> StreamingResponse:
    if body.session_id:
        session = await _service.load_session(body.session_id)
        if session is None:
            session = _service.new_session()
    else:
        session = _service.new_session()

    async def event_generator():
        yield f"data: {json.dumps({'session_id': session.session_id})}\n\n"
        try:
            async for chunk in _service.handle_message(body.message, session):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
        finally:
            yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/session/{session_id}", summary="Get current concierge session state")
async def get_concierge_session(session_id: str) -> dict:
    session = await _service.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    return {
        "session_id": session.session_id,
        "occasion": session.occasion,
        "headcount": session.headcount,
        "budget_inr": session.budget_inr,
        "budget_spent": session.budget_spent,
        "budget_remaining": session.budget_remaining,
        "preferences": session.preferences,
        "active_bookings": session.active_bookings,
        "active_food_orders": session.active_food_orders,
        "active_instamart_orders": session.active_instamart_orders,
        "suggested_venues": session.suggested_venues,
        "instamart_cart": session.instamart_cart,
    }


@router.delete("/session/{session_id}", status_code=204, summary="Clear a concierge session")
async def delete_concierge_session(session_id: str) -> None:
    await _service.delete_session(session_id)


@router.post("/transcribe", summary="Transcribe recorded voice input to text (no auth)")
async def concierge_transcribe(file: UploadFile = File(...)) -> dict:
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    try:
        text = await transcribe_audio(audio_bytes, file.filename or "recording.webm")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc
    return {"text": text}


@router.get("/health", summary="Concierge tool availability")
async def concierge_health() -> dict:
    settings = get_settings()
    swiggy_connected = bool(settings.swiggy_access_token)
    staging_enabled = bool(settings.swiggy_staging_base_url)

    always_available = [
        "find_venues", "get_venue_details", "check_table_availability", "check_my_bookings",
        "find_food", "browse_menu", "add_food_to_cart", "view_food_cart", "apply_best_coupon",
        "place_food_order", "track_food_order", "view_past_orders",
        "find_supplies", "add_supplies_to_cart", "view_supplies_cart", "track_supplies_delivery",
        "get_budget_summary", "track_everything",
    ]
    staging_gated = ["book_table", "order_supplies"]

    return {
        "swiggy_connected": swiggy_connected,
        "staging_enabled": staging_enabled,
        "tools_available": always_available + (staging_gated if staging_enabled else []),
        "tools_pending_staging": [] if staging_enabled else staging_gated,
    }

"""Unit tests for the Guest Concierge API routes (Phase 6A-34).

_service is a module-level singleton in app.api.routes.concierge (no auth
dependency to override), so these tests patch its methods directly rather
than using app.dependency_overrides.
"""

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.domain.services.concierge_service import ConciergeSession
from app.main import app


def _drain_sse(response) -> list[dict]:
    events = []
    for line in response.text.split("\n"):
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


def test_chat_creates_new_session_when_none_provided():
    async def fake_stream(message, session):
        yield {"type": "text", "content": "Hello"}
        yield {"type": "text", "content": " there"}

    with patch("app.api.routes.concierge._service.new_session", return_value=ConciergeSession(session_id="new-session-1")), \
         patch("app.api.routes.concierge._service.handle_message", side_effect=lambda m, s: fake_stream(m, s)):
        response = TestClient(app).post("/api/v1/concierge/chat", json={"session_id": None, "message": "hi"})

    assert response.status_code == 200
    events = _drain_sse(response)
    assert events[0]["session_id"] == "new-session-1"
    text_events = [e for e in events if e.get("type") == "text"]
    assert "".join(e["content"] for e in text_events) == "Hello there"
    assert events[-1]["done"] is True


def test_chat_streams_tool_result_chunk():
    async def fake_stream(message, session):
        yield {"type": "tool_result", "tool": "find_venues", "data": {"venues": [{"name": "The Fatty Bao"}]}}
        yield {"type": "text", "content": "Found a great venue!"}

    with patch("app.api.routes.concierge._service.new_session", return_value=ConciergeSession(session_id="s1")), \
         patch("app.api.routes.concierge._service.handle_message", side_effect=lambda m, s: fake_stream(m, s)):
        response = TestClient(app).post("/api/v1/concierge/chat", json={"session_id": None, "message": "find a venue"})

    events = _drain_sse(response)
    tool_events = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_events) == 1
    assert tool_events[0]["tool"] == "find_venues"
    assert tool_events[0]["data"]["venues"][0]["name"] == "The Fatty Bao"


def test_chat_loads_existing_session_when_id_provided():
    existing = ConciergeSession(session_id="existing-1", occasion="birthday")

    async def fake_stream(message, session):
        assert session.occasion == "birthday"  # proves the loaded session was passed through
        yield {"type": "text", "content": "ok"}

    with patch("app.api.routes.concierge._service.load_session", new=AsyncMock(return_value=existing)), \
         patch("app.api.routes.concierge._service.handle_message", side_effect=lambda m, s: fake_stream(m, s)):
        response = TestClient(app).post("/api/v1/concierge/chat", json={"session_id": "existing-1", "message": "hi"})

    assert response.status_code == 200
    events = _drain_sse(response)
    assert events[0]["session_id"] == "existing-1"


def test_chat_falls_back_to_new_session_when_id_not_found():
    async def fake_stream(message, session):
        yield {"type": "text", "content": "ok"}

    with patch("app.api.routes.concierge._service.load_session", new=AsyncMock(return_value=None)), \
         patch("app.api.routes.concierge._service.new_session", return_value=ConciergeSession(session_id="fresh-1")), \
         patch("app.api.routes.concierge._service.handle_message", side_effect=lambda m, s: fake_stream(m, s)):
        response = TestClient(app).post("/api/v1/concierge/chat", json={"session_id": "expired-id", "message": "hi"})

    events = _drain_sse(response)
    assert events[0]["session_id"] == "fresh-1"


def test_get_session_returns_correct_state():
    session = ConciergeSession(
        session_id="s1", occasion="birthday", headcount=14, budget_inr=10000, budget_spent=2000,
    )
    with patch("app.api.routes.concierge._service.load_session", new=AsyncMock(return_value=session)):
        response = TestClient(app).get("/api/v1/concierge/session/s1")

    assert response.status_code == 200
    body = response.json()
    assert body["occasion"] == "birthday"
    assert body["headcount"] == 14
    assert body["budget_remaining"] == 8000


def test_get_session_404_when_not_found():
    with patch("app.api.routes.concierge._service.load_session", new=AsyncMock(return_value=None)):
        response = TestClient(app).get("/api/v1/concierge/session/nope")
    assert response.status_code == 404


def test_delete_session_clears_it():
    delete_mock = AsyncMock()
    with patch("app.api.routes.concierge._service.delete_session", new=delete_mock):
        response = TestClient(app).delete("/api/v1/concierge/session/s1")

    assert response.status_code == 204
    delete_mock.assert_awaited_once_with("s1")


def test_health_reflects_staging_disabled():
    with patch("app.api.routes.concierge.get_settings") as mock_settings:
        mock_settings.return_value.swiggy_access_token = "token123"
        mock_settings.return_value.swiggy_staging_base_url = ""
        response = TestClient(app).get("/api/v1/concierge/health")

    assert response.status_code == 200
    body = response.json()
    assert body["swiggy_connected"] is True
    assert body["staging_enabled"] is False
    assert "book_table" in body["tools_pending_staging"]
    assert "order_supplies" in body["tools_pending_staging"]
    assert "book_table" not in body["tools_available"]


def test_health_reflects_staging_enabled():
    with patch("app.api.routes.concierge.get_settings") as mock_settings:
        mock_settings.return_value.swiggy_access_token = "token123"
        mock_settings.return_value.swiggy_staging_base_url = "https://mcp-staging.swiggy.com"
        response = TestClient(app).get("/api/v1/concierge/health")

    body = response.json()
    assert body["staging_enabled"] is True
    assert "book_table" in body["tools_available"]
    assert body["tools_pending_staging"] == []


def test_concierge_routes_require_no_auth():
    """No Authorization header, no dependency_overrides for get_current_user --
    if concierge routes had that dependency wired in, this would 401/403."""
    response = TestClient(app).get("/api/v1/concierge/health")
    assert response.status_code == 200

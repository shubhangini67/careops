"""P6-A1: chat conversation history endpoints -- GET /chat/sessions (list) and
GET /chat/sessions/{id} (full thread). Chat history previously lived only in
the frontend's React state per page load; nothing was queryable server-side."""

from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.dependencies import get_db, get_current_user
from app.main import app

MOCK_USER = {"user_id": 1, "org_id": 1, "role": "owner"}


def _mock_session(id_, title, messages):
    s = MagicMock()
    s.id = id_
    s.title = title
    s.updated_at = datetime(2026, 7, 6, 10, 0, 0)
    s.created_at = datetime(2026, 7, 6, 9, 0, 0)
    s.messages = messages
    return s


def _mock_message(role, content):
    m = MagicMock()
    m.role = role
    m.content = content
    return m


def test_list_sessions_returns_summaries_scoped_to_user():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    sessions = [_mock_session(1, "What's my food cost trend?", [_mock_message("user", "hi"), _mock_message("assistant", "hello")])]
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = sessions

    response = TestClient(app).get("/api/v1/chat/sessions")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == 1
    assert body[0]["title"] == "What's my food cost trend?"
    assert body[0]["message_count"] == 2


def test_get_session_returns_full_message_history():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    session = _mock_session(5, "Naan complaints?", [
        _mock_message("user", "Have we had naan complaints?"),
        _mock_message("assistant", "Yes, twice last week."),
    ])
    mock_db.query.return_value.filter.return_value.first.return_value = session

    response = TestClient(app).get("/api/v1/chat/sessions/5")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 5
    assert len(body["messages"]) == 2
    assert body["messages"][1]["content"] == "Yes, twice last week."


def test_get_session_returns_404_when_not_found_or_not_owned():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = TestClient(app).get("/api/v1/chat/sessions/999")
    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_delete_session_removes_it_and_returns_204():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    session = _mock_session(5, "Naan complaints?", [])
    mock_db.query.return_value.filter.return_value.first.return_value = session

    response = TestClient(app).delete("/api/v1/chat/sessions/5")
    app.dependency_overrides.clear()

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(session)
    mock_db.commit.assert_called_once()


def test_delete_session_returns_404_when_not_found_or_not_owned():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = TestClient(app).delete("/api/v1/chat/sessions/999")
    app.dependency_overrides.clear()

    assert response.status_code == 404
    mock_db.delete.assert_not_called()

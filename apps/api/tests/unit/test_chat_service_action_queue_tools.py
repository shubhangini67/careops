"""Unit tests for the P6-A13 chatbot tools: get_market_brief, get_action_queue,
approve_action. These are the same 3 capabilities exposed to Claude Desktop via
mcp_server.py, wired here for the in-app chatbot too.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain.services.action_queue_service import ActionQueueService
from app.domain.services.chat_service import _run_market_brief, _run_tool
from app.infrastructure.db.models import ActionQueue, ActionStatus, ActionTier, Vendor


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    ActionQueue.__table__.create(bind=eng)
    Vendor.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(ActionQueue).delete()
        session.query(Vendor).delete()
        session.commit()


ORG_ID = 1


# ── get_market_brief ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_market_brief_returns_serialized_pulse(db):
    class FakePulse:
        def model_dump(self):
            return {"swiggy_connected": True, "area_occupancy": {"signal": "HIGH"}}

    with patch("app.api.routes.market.get_market_pulse", new=AsyncMock(return_value=FakePulse())):
        result = json.loads(await _run_market_brief(ORG_ID, db))

    assert result["swiggy_connected"] is True
    assert result["area_occupancy"]["signal"] == "HIGH"


@pytest.mark.asyncio
async def test_get_market_brief_handles_failure_gracefully(db):
    with patch("app.api.routes.market.get_market_pulse", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = json.loads(await _run_market_brief(ORG_ID, db))

    assert "error" in result


# ── get_action_queue ──────────────────────────────────────────────────────────

def test_get_action_queue_returns_pending_by_default(db):
    service = ActionQueueService(db)
    service.create_action(org_id=ORG_ID, category="restock_alert", tier=ActionTier.recommendation,
                           title="Low basil", payload={})

    result = json.loads(_run_tool("get_action_queue", {}, db, ORG_ID))

    assert len(result["actions"]) == 1
    assert result["actions"][0]["category"] == "restock_alert"
    assert result["actions"][0]["approval_streak"] == 0


def test_get_action_queue_filters_by_status(db):
    service = ActionQueueService(db)
    a = service.create_action(org_id=ORG_ID, category="restock_alert", tier=ActionTier.recommendation,
                               title="Low basil", payload={})
    service.approve(a.id, user_id=1)

    pending = json.loads(_run_tool("get_action_queue", {"status": "pending"}, db, ORG_ID))
    approved = json.loads(_run_tool("get_action_queue", {"status": "approved"}, db, ORG_ID))

    assert pending["actions"] == []
    assert len(approved["actions"]) == 1


def test_get_action_queue_rejects_invalid_status(db):
    result = json.loads(_run_tool("get_action_queue", {"status": "not_a_real_status"}, db, ORG_ID))
    assert "error" in result


def test_get_action_queue_scoped_to_org(db):
    service = ActionQueueService(db)
    service.create_action(org_id=2, category="restock_alert", tier=ActionTier.recommendation,
                           title="Other org's item", payload={})

    result = json.loads(_run_tool("get_action_queue", {}, db, ORG_ID))
    assert result["actions"] == []


# ── approve_action ────────────────────────────────────────────────────────────

def test_approve_action_approves_non_whatsapp_action(db):
    service = ActionQueueService(db)
    a = service.create_action(org_id=ORG_ID, category="restock_alert", tier=ActionTier.recommendation,
                               title="Low basil", payload={})

    result = json.loads(_run_tool("approve_action", {"action_id": a.id}, db, ORG_ID, user_id=1))

    assert result["status"] == "approved"
    assert result["error"] is None


def test_approve_action_triggers_whatsapp_send(db):
    vendor = Vendor(org_id=ORG_ID, name="Ramesh Traders", is_online=False, whatsapp_number="+919876543210")
    db.add(vendor)
    db.commit()
    db.refresh(vendor)

    service = ActionQueueService(db)
    a = service.create_action(
        org_id=ORG_ID, category="whatsapp_vendor_order", tier=ActionTier.approve_required,
        title="Order mozzarella", payload={"vendor_id": vendor.id, "message_draft": "Send 6kg please"},
    )

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        mock_cls.return_value.send_message.return_value = "SM123"
        result = json.loads(_run_tool("approve_action", {"action_id": a.id}, db, ORG_ID, user_id=1))

    assert result["status"] == "executed"


def test_approve_action_rejects_unknown_id(db):
    result = json.loads(_run_tool("approve_action", {"action_id": 9999}, db, ORG_ID, user_id=1))
    assert "error" in result


def test_approve_action_scoped_to_org(db):
    service = ActionQueueService(db)
    a = service.create_action(org_id=2, category="restock_alert", tier=ActionTier.recommendation,
                               title="Other org's item", payload={})

    result = json.loads(_run_tool("approve_action", {"action_id": a.id}, db, ORG_ID, user_id=1))
    assert "error" in result


def test_approve_action_requires_authenticated_user(db):
    service = ActionQueueService(db)
    a = service.create_action(org_id=ORG_ID, category="restock_alert", tier=ActionTier.recommendation,
                               title="Low basil", payload={})

    result = json.loads(_run_tool("approve_action", {"action_id": a.id}, db, ORG_ID, user_id=None))
    assert "error" in result

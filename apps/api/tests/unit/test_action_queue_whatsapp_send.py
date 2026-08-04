"""Unit tests for the WhatsApp-send orchestration triggered by approving a
whatsapp_vendor_order action (app/domain/services/action_execution_service.py).

Twilio itself is mocked -- these tests verify the orchestration logic (mark_executed
on success, mark_error on failure or missing data), not the real Twilio API call.
This is the same function the HTTP route, the in-app chatbot, and the MCP server's
approve_action tool all call, so it's tested once here rather than per-surface.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain.services.action_execution_service import approve_and_execute
from app.domain.services.action_queue_service import ActionQueueService
from app.infrastructure.db.models import ActionQueue, ActionStatus, ActionTier, Vendor
from app.infrastructure.whatsapp.whatsapp_service import WhatsAppSendError


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


def _vendor(db, whatsapp_number="+919876543210"):
    v = Vendor(org_id=ORG_ID, name="Ramesh Traders", is_online=False, whatsapp_number=whatsapp_number)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _pending_whatsapp_action(db, vendor_id, message_draft="Order more mozzarella please"):
    aq_service = ActionQueueService(db)
    return aq_service.create_action(
        org_id=ORG_ID, category="whatsapp_vendor_order", tier=ActionTier.approve_required,
        title="Order Mozzarella from Ramesh Traders",
        payload={"vendor_id": vendor_id, "ingredient": "Mozzarella Cheese", "message_draft": message_draft},
    )


def test_successful_send_marks_action_executed(db):
    vendor = _vendor(db)
    action = _pending_whatsapp_action(db, vendor.id)

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        mock_cls.return_value.send_message.return_value = "SM123"
        result = approve_and_execute(db, action.id, user_id=1)

    assert result.status == ActionStatus.executed
    assert result.executed_at is not None
    assert result.error is None
    assert result.approved_by == 1


def test_twilio_failure_marks_action_error_not_executed(db):
    vendor = _vendor(db)
    action = _pending_whatsapp_action(db, vendor.id)

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        mock_cls.return_value.send_message.side_effect = WhatsAppSendError("Twilio sandbox not joined")
        result = approve_and_execute(db, action.id, user_id=1)

    assert result.status == ActionStatus.approved  # unchanged -- not executed
    assert result.error == "Twilio sandbox not joined"


def test_missing_vendor_marks_error_without_calling_twilio(db):
    action = _pending_whatsapp_action(db, vendor_id=9999)  # nonexistent vendor

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        result = approve_and_execute(db, action.id, user_id=1)
        mock_cls.assert_not_called()

    assert result.status == ActionStatus.approved
    assert "vendor" in result.error.lower() or "message" in result.error.lower()


def test_vendor_without_whatsapp_number_marks_error(db):
    vendor = _vendor(db, whatsapp_number=None)
    action = _pending_whatsapp_action(db, vendor.id)

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        result = approve_and_execute(db, action.id, user_id=1)
        mock_cls.assert_not_called()

    assert result.status == ActionStatus.approved
    assert result.error is not None


def test_missing_message_draft_marks_error(db):
    vendor = _vendor(db)
    action = _pending_whatsapp_action(db, vendor.id, message_draft="")

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        result = approve_and_execute(db, action.id, user_id=1)
        mock_cls.assert_not_called()

    assert result.status == ActionStatus.approved
    assert result.error is not None


def test_non_whatsapp_category_just_approves_without_touching_twilio(db):
    aq_service = ActionQueueService(db)
    action = aq_service.create_action(
        org_id=ORG_ID, category="restock_alert", tier=ActionTier.recommendation,
        title="Low basil", payload={"ingredient": "Fresh Basil"},
    )

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        result = approve_and_execute(db, action.id, user_id=1)
        mock_cls.assert_not_called()

    assert result.status == ActionStatus.approved


def test_returns_none_for_missing_action(db):
    assert approve_and_execute(db, 9999, user_id=1) is None


def test_message_override_is_sent_instead_of_the_original_draft(db):
    """The owner can edit a drafted (LLM or template) message before it
    actually sends -- the draft is a starting point, not final."""
    vendor = _vendor(db)
    action = _pending_whatsapp_action(db, vendor.id, message_draft="original draft")

    with patch("app.domain.services.action_execution_service.WhatsAppService") as mock_cls:
        mock_cls.return_value.send_message.return_value = "SM123"
        result = approve_and_execute(db, action.id, user_id=1, message_override="owner-edited text")

    mock_cls.return_value.send_message.assert_called_once_with("owner-edited text")
    assert result.status == ActionStatus.executed
    assert result.payload["message_draft"] == "owner-edited text"


def test_message_override_ignored_for_non_whatsapp_category(db):
    aq_service = ActionQueueService(db)
    action = aq_service.create_action(
        org_id=ORG_ID, category="restock_alert", tier=ActionTier.recommendation,
        title="Low basil", payload={"ingredient": "Fresh Basil"},
    )
    result = approve_and_execute(db, action.id, user_id=1, message_override="should not apply")
    assert "message_draft" not in result.payload

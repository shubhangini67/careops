"""Unit tests for ActionQueueService -- the approval-lifecycle infrastructure
every agentic recommendation (WhatsApp vendor orders, restock alerts, price
changes) writes into instead of inventing its own approval mechanism.

Uses SQLite in-memory DB. Every JSONB column in this schema (including
Connector's, which used to exclude its tests from CI) was converted to plain
JSON in P6-A18, so this and every other model's tests run against SQLite
without needing a per-table workaround.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import ActionQueue, ActionStatus, ActionTier
from app.domain.services.action_queue_service import ActionQueueService


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    ActionQueue.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(ActionQueue).delete()
        session.commit()


ORG_ID = 1


def test_create_action_defaults_to_pending_approve_required(db):
    service = ActionQueueService(db)
    action = service.create_action(
        org_id=ORG_ID, category="whatsapp_vendor_order", title="Reorder mozzarella",
        payload={"vendor": "Ramesh Traders", "ingredient": "Mozzarella Cheese"},
    )
    assert action.status == ActionStatus.pending
    assert action.tier == ActionTier.approve_required
    assert action.id is not None


def test_create_action_with_explicit_tier(db):
    service = ActionQueueService(db)
    action = service.create_action(
        org_id=ORG_ID, category="restock_alert", title="Low basil",
        payload={"ingredient": "Fresh Basil"}, tier=ActionTier.recommendation,
    )
    assert action.tier == ActionTier.recommendation


def test_list_actions_filters_by_org_and_status(db):
    service = ActionQueueService(db)
    a1 = service.create_action(org_id=1, category="x", title="a", payload={})
    service.create_action(org_id=2, category="x", title="b", payload={})  # different org
    service.approve(a1.id, user_id=99)

    pending = service.list_actions(org_id=1, status=ActionStatus.pending)
    approved = service.list_actions(org_id=1, status=ActionStatus.approved)
    all_org1 = service.list_actions(org_id=1)

    assert pending == []
    assert len(approved) == 1 and approved[0].id == a1.id
    assert len(all_org1) == 1


def test_approve_sets_status_and_approved_by(db):
    service = ActionQueueService(db)
    action = service.create_action(org_id=ORG_ID, category="x", title="a", payload={})
    approved = service.approve(action.id, user_id=42)
    assert approved.status == ActionStatus.approved
    assert approved.approved_by == 42


def test_reject_sets_status_and_approved_by(db):
    service = ActionQueueService(db)
    action = service.create_action(org_id=ORG_ID, category="x", title="a", payload={})
    rejected = service.reject(action.id, user_id=42)
    assert rejected.status == ActionStatus.rejected
    assert rejected.approved_by == 42


def test_mark_executed_sets_status_and_timestamp(db):
    service = ActionQueueService(db)
    action = service.create_action(org_id=ORG_ID, category="x", title="a", payload={})
    executed = service.mark_executed(action.id)
    assert executed.status == ActionStatus.executed
    assert executed.executed_at is not None


def test_mark_error_records_message_without_changing_status(db):
    service = ActionQueueService(db)
    action = service.create_action(org_id=ORG_ID, category="x", title="a", payload={})
    errored = service.mark_error(action.id, "Twilio timeout")
    assert errored.error == "Twilio timeout"
    assert errored.status == ActionStatus.pending


def test_operations_on_missing_action_raise(db):
    service = ActionQueueService(db)
    with pytest.raises(ValueError):
        service.approve(9999, user_id=1)


def test_update_payload_merges_without_dropping_other_keys(db):
    service = ActionQueueService(db)
    action = service.create_action(
        org_id=ORG_ID, category="whatsapp_vendor_order", title="a",
        payload={"vendor": "Ramesh Traders", "message_draft": "original draft"},
    )
    updated = service.update_payload(action.id, {"message_draft": "owner-edited text"})
    assert updated.payload["message_draft"] == "owner-edited text"
    assert updated.payload["vendor"] == "Ramesh Traders"  # untouched keys survive

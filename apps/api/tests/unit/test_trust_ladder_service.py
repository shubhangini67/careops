"""Unit tests for TrustLadderService -- the informational approval-streak count.
Never auto-promotes anything; purely a badge."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import ActionQueue, ActionStatus, ActionTier
from app.domain.services.trust_ladder_service import TrustLadderService


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


def _action(db, category, status, hours_ago):
    a = ActionQueue(
        org_id=ORG_ID, category=category, tier=ActionTier.approve_required, status=status,
        title="test", payload={}, created_at=datetime.utcnow() - timedelta(hours=hours_ago),
    )
    db.add(a)
    db.commit()
    return a


def test_no_history_returns_zero(db):
    service = TrustLadderService(db)
    assert service.count_consecutive_approvals(ORG_ID, "whatsapp_vendor_order") == 0


def test_three_consecutive_approvals_counts_three(db):
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=3)
    _action(db, "whatsapp_vendor_order", ActionStatus.executed, hours_ago=2)
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=1)

    service = TrustLadderService(db)
    assert service.count_consecutive_approvals(ORG_ID, "whatsapp_vendor_order") == 3


def test_rejection_breaks_the_streak(db):
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=4)
    _action(db, "whatsapp_vendor_order", ActionStatus.rejected, hours_ago=3)
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=2)
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=1)

    service = TrustLadderService(db)
    # only the 2 most recent count -- the streak stops at the rejection
    assert service.count_consecutive_approvals(ORG_ID, "whatsapp_vendor_order") == 2


def test_pending_actions_are_excluded_not_counted(db):
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=2)
    _action(db, "whatsapp_vendor_order", ActionStatus.pending, hours_ago=1)

    service = TrustLadderService(db)
    assert service.count_consecutive_approvals(ORG_ID, "whatsapp_vendor_order") == 1


def test_streak_is_scoped_to_category(db):
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=2)
    _action(db, "restock_alert", ActionStatus.approved, hours_ago=1)

    service = TrustLadderService(db)
    assert service.count_consecutive_approvals(ORG_ID, "whatsapp_vendor_order") == 1
    assert service.count_consecutive_approvals(ORG_ID, "restock_alert") == 1


def test_streak_is_scoped_to_org(db):
    _action(db, "whatsapp_vendor_order", ActionStatus.approved, hours_ago=1)
    other_org_action = ActionQueue(
        org_id=2, category="whatsapp_vendor_order", tier=ActionTier.approve_required,
        status=ActionStatus.approved, title="test", payload={},
    )
    db.add(other_org_action)
    db.commit()

    service = TrustLadderService(db)
    assert service.count_consecutive_approvals(ORG_ID, "whatsapp_vendor_order") == 1

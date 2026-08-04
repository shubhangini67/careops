"""Unit tests for SwiggyFeedbackSyncService (P6-S06).

Uses SQLite in-memory DB. Only creates the tables directly needed by the tests
(Feedback, Order, MenuItem) — avoids JSONB columns on other tables.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Feedback, FeedbackSource, MenuItem, Order, SentimentType
from app.infrastructure.swiggy.sync.feedback_sync import SwiggyFeedbackSyncService


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    MenuItem.__table__.create(bind=eng)
    Order.__table__.create(bind=eng)
    Feedback.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(Feedback).delete()
        session.query(Order).delete()
        session.query(MenuItem).delete()
        session.commit()


def _client(orders_return, track_return=None):
    c = MagicMock()

    async def _call_tool(endpoint, tool_name, arguments):
        if tool_name == "get_food_orders":
            return orders_return
        if tool_name == "track_food_order":
            return track_return
        return None

    c.call_tool = _call_tool
    return c


DELIVERED_ORDERS = {
    "orders": [
        {
            "orderId": "SW-001",
            "status": "delivered",
            "restaurantName": "Pizza Palace",
        }
    ]
}

TRACK_LATE = {
    "orderId": "SW-001",
    "deliveryTime": 45,
    "promisedTime": 30,
    "isLate": True,
}

TRACK_ONTIME = {
    "orderId": "SW-001",
    "deliveryTime": 25,
    "promisedTime": 30,
    "isLate": False,
}


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_maps_late_to_negative_sentiment(db):
    with patch("asyncio.sleep", new_callable=AsyncMock):
        svc = SwiggyFeedbackSyncService(_client(DELIVERED_ORDERS, TRACK_LATE), db)
        result = await svc.sync("addr-1")

    assert result["synced"] == 1
    fb = db.query(Feedback).first()
    assert fb is not None
    assert fb.sentiment == SentimentType.negative
    assert fb.was_late is True
    assert fb.delivery_time_actual_mins == 45
    assert fb.delivery_time_promised_mins == 30


@pytest.mark.asyncio
async def test_sync_maps_ontime_to_positive_sentiment(db):
    with patch("asyncio.sleep", new_callable=AsyncMock):
        svc = SwiggyFeedbackSyncService(_client(DELIVERED_ORDERS, TRACK_ONTIME), db)
        result = await svc.sync("addr-1")

    assert result["synced"] == 1
    fb = db.query(Feedback).first()
    assert fb.sentiment == SentimentType.positive
    assert fb.was_late is False


@pytest.mark.asyncio
async def test_sync_deduplicates_by_external_order_id(db):
    with patch("asyncio.sleep", new_callable=AsyncMock):
        svc = SwiggyFeedbackSyncService(_client(DELIVERED_ORDERS, TRACK_LATE), db)
        await svc.sync("addr-1")
        result2 = await svc.sync("addr-1")

    assert result2["synced"] == 0
    assert result2["skipped"] == 1
    assert db.query(Feedback).count() == 1


@pytest.mark.asyncio
async def test_sync_only_processes_delivered_orders(db):
    orders = {
        "orders": [
            {"orderId": "SW-010", "status": "pending"},
            {"orderId": "SW-011", "status": "out_for_delivery"},
            {"orderId": "SW-012", "status": "delivered"},
        ]
    }
    with patch("asyncio.sleep", new_callable=AsyncMock):
        svc = SwiggyFeedbackSyncService(_client(orders, TRACK_ONTIME), db)
        result = await svc.sync("addr-1")

    assert result["synced"] == 1
    assert result["skipped"] == 2
    assert db.query(Feedback).count() == 1


@pytest.mark.asyncio
async def test_sync_returns_zeros_when_client_returns_none(db):
    svc = SwiggyFeedbackSyncService(_client(None), db)
    result = await svc.sync("addr-1")

    assert result == {"synced": 0, "skipped": 0, "errors": 0}
    assert db.query(Feedback).count() == 0


@pytest.mark.asyncio
async def test_sync_sets_source_to_swiggy_delivery(db):
    with patch("asyncio.sleep", new_callable=AsyncMock):
        svc = SwiggyFeedbackSyncService(_client(DELIVERED_ORDERS, TRACK_ONTIME), db)
        await svc.sync("addr-1")

    fb = db.query(Feedback).first()
    assert fb.source == FeedbackSource.swiggy_delivery


@pytest.mark.asyncio
async def test_sync_stores_external_order_id(db):
    with patch("asyncio.sleep", new_callable=AsyncMock):
        svc = SwiggyFeedbackSyncService(_client(DELIVERED_ORDERS, TRACK_LATE), db)
        await svc.sync("addr-1")

    fb = db.query(Feedback).first()
    assert fb.external_order_id == "SW-001"

"""Unit tests for SwiggyOrderSyncService (P6-S03).

Uses SQLite in-memory DB. Creates only MenuItem and Order tables so the
JSONB columns on Organization don't break SQLiteTypeCompiler.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import MenuItem, Order
from app.infrastructure.swiggy.sync.order_sync import SwiggyOrderSyncService


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    MenuItem.__table__.create(bind=eng)
    Order.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(Order).delete()
        session.query(MenuItem).delete()
        session.commit()


def _client(return_value):
    c = MagicMock()
    c.call_tool = AsyncMock(return_value=return_value)
    return c


ONE_ORDER_TWO_ITEMS = {
    "orders": [
        {
            "orderId": "SW-001",
            "restaurantName": "Pizza Palace",
            "status": "delivered",
            "totalAmount": 360.0,
            "orderedAt": "2026-06-26T19:30:00+05:30",
            "items": [
                {"name": "Margherita Pizza", "quantity": 2, "price": 150.0},
                {"name": "Garlic Bread", "quantity": 1, "price": 60.0},
            ],
        }
    ]
}


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_returns_correct_count(db):
    svc = SwiggyOrderSyncService(_client(ONE_ORDER_TWO_ITEMS), db)
    result = await svc.sync("addr-1")
    assert result == {"synced": 2, "skipped": 0, "errors": 0}


@pytest.mark.asyncio
async def test_sync_creates_order_rows_with_correct_fields(db):
    svc = SwiggyOrderSyncService(_client(ONE_ORDER_TWO_ITEMS), db)
    await svc.sync("addr-1")
    orders = db.query(Order).order_by(Order.id).all()
    assert len(orders) == 2
    for o in orders:
        assert o.source == "swiggy"
        assert o.channel == "delivery"
        assert o.is_delivery is True


@pytest.mark.asyncio
async def test_sync_creates_placeholder_menu_items(db):
    svc = SwiggyOrderSyncService(_client(ONE_ORDER_TWO_ITEMS), db)
    await svc.sync("addr-1")
    items = db.query(MenuItem).order_by(MenuItem.id).all()
    assert len(items) == 2
    assert all(i.is_available is False for i in items)
    assert all(i.category == "swiggy_import" for i in items)
    names = {i.name for i in items}
    assert names == {"Margherita Pizza", "Garlic Bread"}


@pytest.mark.asyncio
async def test_sync_reuses_existing_menu_item(db):
    existing = MenuItem(name="Margherita Pizza", category="pizza", price=199.0, is_available=True)
    db.add(existing)
    db.commit()

    data = {
        "orders": [{
            "orderId": "SW-002",
            "orderedAt": None,
            "totalAmount": 199.0,
            "items": [{"name": "Margherita Pizza", "quantity": 1, "price": 199.0}],
        }]
    }
    svc = SwiggyOrderSyncService(_client(data), db)
    await svc.sync("addr-1")

    assert db.query(MenuItem).count() == 1
    order = db.query(Order).first()
    assert order.menu_item_id == existing.id
    assert order.is_delivery is True


@pytest.mark.asyncio
async def test_sync_idempotent_on_duplicate(db):
    svc = SwiggyOrderSyncService(_client(ONE_ORDER_TWO_ITEMS), db)
    await svc.sync("addr-1")
    result2 = await svc.sync("addr-1")
    assert result2 == {"synced": 0, "skipped": 2, "errors": 0}
    assert db.query(Order).count() == 2


@pytest.mark.asyncio
async def test_sync_returns_zero_when_call_tool_returns_none(db):
    svc = SwiggyOrderSyncService(_client(None), db)
    result = await svc.sync("addr-1")
    assert result == {"synced": 0, "skipped": 0, "errors": 0}
    assert db.query(Order).count() == 0


@pytest.mark.asyncio
async def test_sync_handles_empty_orders_list(db):
    svc = SwiggyOrderSyncService(_client({"orders": []}), db)
    result = await svc.sync("addr-1")
    assert result == {"synced": 0, "skipped": 0, "errors": 0}


@pytest.mark.asyncio
async def test_sync_sets_external_order_id_per_item(db):
    svc = SwiggyOrderSyncService(_client(ONE_ORDER_TWO_ITEMS), db)
    await svc.sync("addr-1")
    orders = db.query(Order).order_by(Order.id).all()
    assert orders[0].external_order_id == "SW-001_0"
    assert orders[1].external_order_id == "SW-001_1"

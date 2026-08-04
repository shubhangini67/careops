"""Unit tests for GET /business/performance's route-level logic (not the
shared BusinessAnalyticsService, already covered by
test_business_analytics_service.py) -- specifically the day-window fix for
channel_split/complaints_by_category (both used to ignore the `days` query
param), the new unsliced `all_dishes` field (Menu Engineering Matrix needs
every dish, not just the top/bottom 5), and the new
GET /business/inventory-snapshot endpoint.

Calls the route functions directly (not via TestClient/HTTP) against a real
SQLite in-memory session -- same pattern as test_business_analytics_service.py,
extended with the extra tables (Organization, Inventory, PlanningRun) the
route touches that the service-level tests don't need.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    Expense, Feedback, Inventory, MenuItem, Order, Organization, PlanningRun, Reservation, SentimentType,
)
from app.api.routes.business import get_business_performance, get_inventory_snapshot

ORG_ID = 1
CURRENT = {"org_id": ORG_ID, "id": 1, "role": "owner"}


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    for model in (Organization, MenuItem, Order, Feedback, Expense, Inventory, PlanningRun, Reservation):
        model.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        if not session.query(Organization).filter(Organization.id == ORG_ID).first():
            session.add(Organization(id=ORG_ID, name="Test Org", slug="test-org"))
            session.commit()
        yield session
        session.rollback()
        for model in (Expense, Feedback, Order, MenuItem, Inventory):
            session.query(model).delete()
        session.commit()


def _menu_item(db, name, category, price, cost_price):
    item = MenuItem(name=name, category=category, price=price, cost_price=cost_price)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _order(db, item, quantity, total_price, days_ago, is_delivery=False):
    db.add(Order(
        menu_item_id=item.id, quantity=quantity, total_price=total_price,
        is_delivery=is_delivery, ordered_at=datetime.utcnow() - timedelta(days=days_ago),
    ))
    db.commit()


def _complaint(db, text, days_ago):
    db.add(Feedback(
        raw_text=text, sentiment=SentimentType.negative,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
    ))
    db.commit()


# ── channel_split now respects `days`, not hardcoded to "yesterday" ─────────

def test_channel_split_widens_with_days_window(db):
    item = _menu_item(db, "Pizza", "pizza", 300.0, 100.0)
    _order(db, item, 1, 300.0, days_ago=1, is_delivery=False)   # inside a 7-day window
    _order(db, item, 1, 300.0, days_ago=10, is_delivery=True)   # only inside a 14-day window

    narrow = get_business_performance(days=7, current=CURRENT, db=db)
    wide = get_business_performance(days=14, current=CURRENT, db=db)

    assert narrow.channel_split.dine_in_orders == 1
    assert narrow.channel_split.delivery_orders == 0
    assert wide.channel_split.dine_in_orders == 1
    assert wide.channel_split.delivery_orders == 1


# ── complaints_by_category now respects `days`, not a hardcoded 28 ─────────

def test_complaints_by_category_widens_with_days_window(db):
    _complaint(db, "the wait was way too long", days_ago=5)
    _complaint(db, "food arrived cold", days_ago=20)  # outside a 7-day window, inside 28

    narrow = get_business_performance(days=7, current=CURRENT, db=db)
    wide = get_business_performance(days=28, current=CURRENT, db=db)

    assert sum(c.count for c in narrow.complaints_by_category) == 1
    assert sum(c.count for c in wide.complaints_by_category) == 2


# ── all_dishes: full unsliced list, not just top/bottom 5 ──────────────────

def test_all_dishes_unsliced(db):
    for i in range(8):
        item = _menu_item(db, f"Dish {i}", "sides", 100.0, 40.0)
        _order(db, item, 1, 100.0 + i, days_ago=1)

    result = get_business_performance(days=7, current=CURRENT, db=db)

    assert len(result.all_dishes) == 8
    assert len(result.top_dishes) == 5
    assert len(result.bottom_dishes) <= 5
    names_all = {d.name for d in result.all_dishes}
    assert names_all == {f"Dish {i}" for i in range(8)}


# ── GET /business/inventory-snapshot ────────────────────────────────────────

def test_inventory_snapshot_returns_shortage_and_overstock_alerts(db):
    db.add_all([
        Inventory(ingredient_name="Garlic", unit="kg", quantity_in_stock=1.0,
                  reorder_threshold=5.0, spoilage_risk=True),
        Inventory(ingredient_name="Rice", unit="kg", quantity_in_stock=50.0,
                  reorder_threshold=5.0, spoilage_risk=False),
        Inventory(ingredient_name="Tomatoes", unit="kg", quantity_in_stock=8.0,
                  reorder_threshold=6.0, spoilage_risk=False),
    ])
    db.commit()

    snapshot = get_inventory_snapshot(current=CURRENT, db=db)

    assert snapshot.total_items_checked == 3
    assert len(snapshot.shortage_alerts) == 1
    assert snapshot.shortage_alerts[0].ingredient == "Garlic"
    assert len(snapshot.overstock_alerts) == 1
    assert snapshot.overstock_alerts[0].ingredient == "Rice"


def test_inventory_snapshot_empty_when_nothing_out_of_range(db):
    db.add(Inventory(ingredient_name="Onions", unit="kg", quantity_in_stock=10.0,
                      reorder_threshold=5.0, spoilage_risk=False))
    db.commit()

    snapshot = get_inventory_snapshot(current=CURRENT, db=db)

    assert snapshot.shortage_alerts == []
    assert snapshot.overstock_alerts == []

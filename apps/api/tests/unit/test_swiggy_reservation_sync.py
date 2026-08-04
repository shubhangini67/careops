"""Unit tests for SwiggyReservationSyncService (P6-S05).

Uses SQLite in-memory DB with just the Reservation and Connector tables.
connector_metadata is stored as plain JSON (no JSONB dialect needed for SQLite).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Connector, Reservation
from app.infrastructure.swiggy.connector_repository import ConnectorRepository
from app.infrastructure.swiggy.sync.reservation_sync import SwiggyReservationSyncService


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    Reservation.__table__.create(bind=eng)
    Connector.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(Reservation).delete()
        session.query(Connector).delete()
        session.commit()


def _client(booking_return=None):
    c = MagicMock()
    c.call_tool = AsyncMock(return_value=booking_return)
    return c


def _make_connector(db, org_id, metadata=None):
    conn = Connector(
        org_id=org_id,
        connector_type="swiggy",
        sync_status="success",
        connector_metadata=metadata,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


BOOKING_STATUS = {
    "orderId": "DO-001",
    "restaurantName": "The Fatty Bao",
    "date": "2026-06-30",
    "time": "07:00 PM",
    "guestCount": 4,
    "dealTitle": "Free Table Booking",
    "status": "confirmed",
}


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_returns_note_when_no_order_ids(db):
    repo = ConnectorRepository(db)
    _make_connector(db, org_id=1, metadata=None)

    svc = SwiggyReservationSyncService(_client(), db, repo)
    result = await svc.sync(org_id=1)

    assert result["synced"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == 0
    assert "No Dineout bookings registered yet" in result["note"]


@pytest.mark.asyncio
async def test_sync_returns_note_when_connector_missing(db):
    repo = ConnectorRepository(db)
    svc = SwiggyReservationSyncService(_client(), db, repo)
    result = await svc.sync(org_id=999)

    assert result["note"] is not None
    assert "No Dineout bookings" in result["note"]


@pytest.mark.asyncio
async def test_register_booking_stores_order_id(db):
    _make_connector(db, org_id=2, metadata=None)
    repo = ConnectorRepository(db)
    svc = SwiggyReservationSyncService(_client(), db, repo)

    await svc.register_booking_order_id(org_id=2, order_id="DO-100")

    conn = repo.get(2, "swiggy")
    assert conn.connector_metadata is not None
    assert "DO-100" in conn.connector_metadata["dineout_order_ids"]


@pytest.mark.asyncio
async def test_register_booking_is_idempotent(db):
    _make_connector(db, org_id=3, metadata=None)
    repo = ConnectorRepository(db)
    svc = SwiggyReservationSyncService(_client(), db, repo)

    await svc.register_booking_order_id(org_id=3, order_id="DO-200")
    await svc.register_booking_order_id(org_id=3, order_id="DO-200")

    conn = repo.get(3, "swiggy")
    assert conn.connector_metadata["dineout_order_ids"].count("DO-200") == 1


@pytest.mark.asyncio
async def test_sync_with_known_order_id_creates_reservation(db):
    _make_connector(
        db, org_id=4,
        metadata={"dineout_order_ids": ["DO-001"]},
    )
    repo = ConnectorRepository(db)
    svc = SwiggyReservationSyncService(_client(BOOKING_STATUS), db, repo)

    result = await svc.sync(org_id=4)

    assert result["synced"] == 1
    res = db.query(Reservation).first()
    assert res is not None
    assert res.external_booking_id == "DO-001"
    assert res.source == "dineout"
    assert res.guest_count == 4


@pytest.mark.asyncio
async def test_sync_deduplicates_reservations(db):
    _make_connector(
        db, org_id=5,
        metadata={"dineout_order_ids": ["DO-002"]},
    )
    repo = ConnectorRepository(db)
    svc = SwiggyReservationSyncService(_client(BOOKING_STATUS), db, repo)

    await svc.sync(org_id=5)
    result2 = await svc.sync(org_id=5)

    assert result2["synced"] == 0
    assert result2["skipped"] == 1
    assert db.query(Reservation).filter_by(external_booking_id="DO-002").count() == 1

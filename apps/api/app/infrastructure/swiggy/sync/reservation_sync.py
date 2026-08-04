"""SwiggyReservationSyncService — sync Dineout booking statuses into the reservations table.

IMPORTANT — CONSUMER DATA ONLY:
Swiggy MCP is consumer-facing. get_booking_status returns status of bookings made
BY the authenticated consumer (tables they booked at restaurants), not bookings
made at your own restaurant by your guests.

FUTURE USE (needs Swiggy Partner API): when Partner API is available, this sync
will pull actual incoming Dineout reservations at your restaurant (guest name, party
size, time, special requests). The DB schema, dedup logic, and upsert pattern are
ready — only the data source changes.

Current state: this sync is a graceful no-op (no dineout_order_ids registered yet
because book_table is not called in the consumer-side flow). The reservations table
is populated by internal/POS data only.

Booking order IDs (returned by book_table) are stored in the connector's connector_metadata
JSON column under "dineout_order_ids". DineoutExecutor (P6-S16) calls
register_booking_order_id() after each successful book_table call.
"""

from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Reservation, ReservationStatus
from app.infrastructure.swiggy.client import DINEOUT_ENDPOINT, SwiggyMCPClient
from app.infrastructure.swiggy.connector_repository import ConnectorRepository

log = structlog.get_logger()


def _parse_reservation_dt(date_str: str | None, time_str: str | None) -> datetime | None:
    if not date_str or not time_str:
        return None
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            continue
    return None


class SwiggyReservationSyncService:
    """Syncs Dineout booking statuses for all registered booking order IDs."""

    def __init__(
        self,
        client: SwiggyMCPClient,
        db: Session,
        repo: ConnectorRepository,
    ) -> None:
        self._client = client
        self._db = db
        self._repo = repo

    async def sync(self, org_id: int) -> dict:
        """Fetch booking statuses for all known Dineout order IDs and persist them.

        Returns {"synced": N, "skipped": N, "errors": N, "note": str | None}.
        """
        order_ids = self._get_known_order_ids(org_id)

        if not order_ids:
            return {
                "synced": 0,
                "skipped": 0,
                "errors": 0,
                "note": (
                    "No Dineout bookings registered yet. "
                    "Booking IDs are captured when book_table is called (P6-S16)."
                ),
            }

        synced = skipped = errors = 0

        for order_id in order_ids:
            if self._reservation_exists(order_id):
                skipped += 1
                continue

            try:
                raw = await self._client.call_tool(
                    DINEOUT_ENDPOINT,
                    "get_booking_status",
                    {"orderId": order_id},
                )

                data = raw or {}

                status_str = (data.get("status") or "confirmed").lower()
                try:
                    status = ReservationStatus(status_str)
                except ValueError:
                    status = ReservationStatus.confirmed

                reserved_at = _parse_reservation_dt(data.get("date"), data.get("time"))

                self._db.add(Reservation(
                    guest_name=data.get("restaurantName", "Dineout Guest"),
                    guest_count=int(data.get("guestCount") or 1),
                    reserved_at=reserved_at or datetime.utcnow(),
                    status=status,
                    source="dineout",
                    external_booking_id=order_id,
                    notes=data.get("dealTitle"),
                ))
                self._db.commit()
                synced += 1

            except Exception as exc:
                self._db.rollback()
                log.error(
                    "swiggy_reservation_row_error",
                    order_id=order_id, error=str(exc),
                )
                errors += 1

        log.info(
            "swiggy_reservation_sync_done",
            org_id=org_id, synced=synced, skipped=skipped, errors=errors,
        )
        return {"synced": synced, "skipped": skipped, "errors": errors, "note": None}

    async def register_booking_order_id(self, org_id: int, order_id: str) -> None:
        """Store a Dineout booking order ID so the next sync will fetch its status.

        Called by DineoutExecutor (P6-S16) after a successful book_table call.
        Idempotent — safe to call multiple times with the same order_id.
        """
        connector = self._repo.get(org_id, "swiggy")
        if connector is None:
            log.warning(
                "swiggy_connector_not_found_for_booking_register",
                org_id=org_id, order_id=order_id,
            )
            return

        meta = connector.connector_metadata or {}
        ids: list[str] = list(meta.get("dineout_order_ids", []))
        if order_id not in ids:
            ids.append(order_id)
            meta["dineout_order_ids"] = ids
            connector.connector_metadata = meta
            connector.updated_at = datetime.utcnow()
            self._db.commit()
            log.info("dineout_booking_id_registered", org_id=org_id, order_id=order_id)

    def _get_known_order_ids(self, org_id: int) -> list[str]:
        connector = self._repo.get(org_id, "swiggy")
        if connector is None or not connector.connector_metadata:
            return []
        return connector.connector_metadata.get("dineout_order_ids", [])

    def _reservation_exists(self, external_booking_id: str) -> bool:
        return (
            self._db.query(Reservation)
            .filter_by(external_booking_id=external_booking_id)
            .first()
        ) is not None

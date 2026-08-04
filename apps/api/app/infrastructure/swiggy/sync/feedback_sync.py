"""SwiggyFeedbackSyncService — sync delivery timing data from track_food_order into feedback table.

IMPORTANT — CONSUMER DATA ONLY:
Swiggy MCP is consumer-facing. track_food_order tracks deliveries made TO the
authenticated consumer, not deliveries sent FROM a restaurant. This syncs YOUR
personal food delivery experiences (lateness, ETA accuracy), not your restaurant's
outgoing delivery performance.

FUTURE USE (needs Swiggy Partner API): when Partner API is available, the same
sync pattern will pull real restaurant delivery performance metrics (avg delivery
time, late rate, customer-reported issues). The DB schema and dedup logic are ready.

Current state: data synced here is NOT read by complaint_intelligence or any
planning node. Pipeline uses internal feedback data only.

Pulls recent delivered orders via get_food_orders, then calls track_food_order per
order to get actual vs promised delivery times. Deduplicates on external_order_id.
Only processes orders with status == "delivered".

Idempotency: external_order_id = Swiggy orderId (e.g. "SW-001"). Duplicate syncs skip
already-present rows.
"""

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Feedback, FeedbackSource, Order, SentimentType
from app.infrastructure.swiggy.client import FOOD_ENDPOINT, SwiggyMCPClient

log = structlog.get_logger()


class SwiggyFeedbackSyncService:
    """Pulls Swiggy delivered-order tracking data and writes to the feedback table."""

    def __init__(self, client: SwiggyMCPClient, db: Session) -> None:
        self._client = client
        self._db = db

    async def sync(self, address_id: str) -> dict:
        """Fetch delivered orders, track each one, and persist delivery feedback.

        Returns {"synced": N, "skipped": N, "errors": N}.
        """
        raw = await self._client.call_tool(
            FOOD_ENDPOINT,
            "get_food_orders",
            {"addressId": address_id, "orderCount": 20},
        )
        if raw is None:
            log.warning("swiggy_feedback_sync_no_orders", address_id=address_id)
            return {"synced": 0, "skipped": 0, "errors": 0}

        orders = (
            raw.get("orders")
            or raw.get("data", {}).get("orders")
            or []
        )
        synced = skipped = errors = 0

        for order in orders:
            if order.get("status") != "delivered":
                skipped += 1
                continue

            order_id = str(order.get("orderId") or "")
            if not order_id:
                skipped += 1
                continue

            if self._feedback_exists(order_id):
                skipped += 1
                continue

            await asyncio.sleep(0.5)

            try:
                track_raw = await self._client.call_tool(
                    FOOD_ENDPOINT,
                    "track_food_order",
                    {"orderId": order_id},
                )

                track = track_raw or {}

                delivery_time = track.get("deliveryTime") or track.get("delivery_time_actual")
                promised_time = track.get("promisedTime") or track.get("promised_time")
                is_late = bool(track.get("isLate") or track.get("is_late") or False)

                delivery_time = int(delivery_time) if delivery_time is not None else None
                promised_time = int(promised_time) if promised_time is not None else None

                sentiment = SentimentType.negative if is_late else SentimentType.positive

                if delivery_time is not None and promised_time is not None:
                    raw_text = (
                        f"Swiggy delivery for order {order_id}: "
                        f"{delivery_time} min actual vs {promised_time} min promised. "
                        f"{'Late.' if is_late else 'On time.'}"
                    )
                else:
                    raw_text = (
                        f"Swiggy delivery for order {order_id} "
                        f"({'late' if is_late else 'on time'})."
                    )

                linked_order = self._find_order(order_id)

                self._db.add(Feedback(
                    order_id=linked_order.id if linked_order else None,
                    raw_text=raw_text,
                    sentiment=sentiment,
                    source=FeedbackSource.swiggy_delivery,
                    delivery_time_actual_mins=delivery_time,
                    delivery_time_promised_mins=promised_time,
                    was_late=is_late,
                    external_order_id=order_id,
                ))
                self._db.commit()
                synced += 1

            except Exception as exc:
                self._db.rollback()
                log.error("swiggy_feedback_row_error", order_id=order_id, error=str(exc))
                errors += 1

        log.info(
            "swiggy_feedback_sync_done",
            synced=synced,
            skipped=skipped,
            errors=errors,
            address_id=address_id,
        )
        return {"synced": synced, "skipped": skipped, "errors": errors}

    def _feedback_exists(self, external_order_id: str) -> bool:
        return (
            self._db.query(Feedback)
            .filter_by(external_order_id=external_order_id)
            .first()
        ) is not None

    def _find_order(self, swiggy_order_id: str) -> Order | None:
        """Find the first Order row for a given Swiggy order ID (by external_order_id prefix)."""
        return (
            self._db.query(Order)
            .filter(Order.external_order_id.like(f"{swiggy_order_id}_%"))
            .first()
        )

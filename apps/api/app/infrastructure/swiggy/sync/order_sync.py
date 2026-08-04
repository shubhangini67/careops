"""SwiggyOrderSyncService — nightly sync of Swiggy food orders into the orders table.

IMPORTANT — CONSUMER DATA ONLY:
Swiggy MCP is consumer-facing (confirmed from Swiggy Builders Club docs). get_food_orders
returns orders placed BY the authenticated Swiggy consumer account (personal food
deliveries), NOT a restaurant's incoming orders from customers.

This sync is kept as infrastructure because:
1. The sync pattern, dedup logic, and DB upsert code are correct and reusable.
2. FUTURE USE: when Swiggy Partner/Merchant API becomes available, the same pattern
   will sync actual restaurant-received Swiggy orders. Only the API endpoint changes.

Current state: syncs personal consumer order history. This data is NOT used by the
demand_forecast node or any planning node — pipeline ops nodes rely on internal/POS data.

Calls get_food_orders via SwiggyMCPClient and upserts results into the orders table.
One Order row is created per item per order (matching the existing data model).
Items are matched to MenuItems by name (case-insensitive); unmatched items get a
placeholder MenuItem (is_available=False, category='swiggy_import') so the FK is
satisfied without polluting the live menu.

Idempotency: external_order_id = "{swiggy_order_id}_{item_index}". Duplicate syncs
skip already-present rows.
"""

from datetime import datetime, timezone

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.db.models import MenuItem, Order
from app.infrastructure.swiggy.client import FOOD_ENDPOINT, SwiggyMCPClient

log = structlog.get_logger()


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO-8601 string (with or without tz) to naive UTC datetime."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


class SwiggyOrderSyncService:
    """Pulls recent Swiggy delivery orders and writes them to the orders table."""

    def __init__(self, client: SwiggyMCPClient, db: Session) -> None:
        self._client = client
        self._db = db

    async def sync(self, address_id: str) -> dict:
        """Fetch and persist up to 20 recent Swiggy orders.

        Returns {"synced": N, "skipped": N, "errors": N}.
        """
        data = await self._client.call_tool(
            FOOD_ENDPOINT,
            "get_food_orders",
            {"addressId": address_id, "orderCount": 20},
        )
        if data is None:
            log.warning("swiggy_order_sync_no_data", address_id=address_id)
            return {"synced": 0, "skipped": 0, "errors": 0}

        orders = data.get("orders") or []
        synced = skipped = errors = 0

        for order in orders:
            order_id = str(order.get("orderId") or "")
            ordered_at = _parse_dt(order.get("orderedAt"))
            items = order.get("items") or []
            total = float(order.get("totalAmount") or 0.0)
            fallback_price = total / len(items) if items else 0.0

            for idx, item in enumerate(items):
                ext_id = f"{order_id}_{idx}"

                if self._order_exists(ext_id):
                    skipped += 1
                    continue

                try:
                    name = str(item.get("name") or "Swiggy Item")
                    price = float(item.get("price") or fallback_price)
                    qty = int(item.get("quantity") or 1)
                    menu_item = self._get_or_create_menu_item(name, price)

                    self._db.add(Order(
                        menu_item_id=menu_item.id,
                        quantity=qty,
                        total_price=price * qty,
                        ordered_at=ordered_at or datetime.utcnow(),
                        is_delivery=True,
                        source="swiggy",
                        channel="delivery",
                        external_order_id=ext_id,
                    ))
                    self._db.commit()
                    synced += 1

                except Exception as exc:
                    self._db.rollback()
                    log.error("swiggy_order_row_error", ext_id=ext_id, error=str(exc))
                    errors += 1

        log.info(
            "swiggy_order_sync_done",
            synced=synced,
            skipped=skipped,
            errors=errors,
            address_id=address_id,
        )
        return {"synced": synced, "skipped": skipped, "errors": errors}

    def _order_exists(self, external_order_id: str) -> bool:
        return (
            self._db.query(Order)
            .filter_by(external_order_id=external_order_id)
            .first()
        ) is not None

    def _get_or_create_menu_item(self, name: str, price: float) -> MenuItem:
        """Find existing MenuItem by name (case-insensitive) or create a placeholder."""
        item = (
            self._db.query(MenuItem)
            .filter(func.lower(MenuItem.name) == name.lower())
            .first()
        )
        if item is None:
            item = MenuItem(
                name=name,
                category="swiggy_import",
                price=price,
                is_available=False,
            )
            self._db.add(item)
            self._db.flush()
        return item

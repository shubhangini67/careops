"""SwiggyConnector — BaseConnector implementation for Swiggy MCP.

IMPORTANT — two distinct modes with different data validity:

sync()   → CONSUMER DATA ONLY (FUTURE USE for restaurant data).
           Swiggy MCP is consumer-facing — sync pulls personal consumer account data
           (your own food orders, Dineout bookings), not restaurant business data.
           Code and infrastructure are correct and reusable. When Swiggy Partner API
           becomes available, only the endpoint + auth changes; everything else stays.

enrich() → VALID NOW — primary value of Swiggy integration.
           Uses public consumer-facing tools for market intelligence:
           CompetitorEnricher (P6-S07), OccupancyEnricher (P6-S08),
           ProcurementEnricher (P6-S09).
"""

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.infrastructure.base_connector import BaseConnector
from app.infrastructure.swiggy.client import SwiggyMCPClient
from app.infrastructure.swiggy.connector_repository import ConnectorRepository
from app.infrastructure.swiggy.sync.feedback_sync import SwiggyFeedbackSyncService
from app.infrastructure.swiggy.sync.order_sync import SwiggyOrderSyncService
from app.infrastructure.swiggy.sync.reservation_sync import SwiggyReservationSyncService


class SwiggyConnector(BaseConnector):
    """Swiggy MCP connector — orchestrates order, feedback, and reservation sync."""

    def __init__(
        self,
        client: SwiggyMCPClient,
        db: Session,
        org_id: int,
        repo: ConnectorRepository | None = None,
    ) -> None:
        super().__init__(client, db, org_id)
        self._repo = repo or ConnectorRepository(db)

    async def sync(self, address_id: str | None = None) -> dict:
        """Nightly sync: orders + delivery feedback + Dineout reservation status.

        address_id takes precedence over SWIGGY_ADDRESS_ID from settings.
        Updates connector sync_status in the connectors table.
        Returns aggregated result dict with per-service counts.
        """
        addr = address_id or get_settings().swiggy_address_id
        if not addr:
            self._log("swiggy_sync_skipped", reason="SWIGGY_ADDRESS_ID not configured")
            return {
                "orders":       {"synced": 0, "skipped": 0, "errors": 0},
                "feedback":     {"synced": 0, "skipped": 0, "errors": 0},
                "reservations": {"synced": 0, "skipped": 0, "errors": 0},
            }

        self._repo.update_sync_status(self.org_id, "swiggy", "syncing")

        try:
            order_result = await SwiggyOrderSyncService(
                self._client, self._db
            ).sync(addr)

            feedback_result = await SwiggyFeedbackSyncService(
                self._client, self._db
            ).sync(addr)

            reservation_result = await SwiggyReservationSyncService(
                self._client, self._db, self._repo
            ).sync(self.org_id)

            self._repo.update_sync_status(self.org_id, "swiggy", "success")
            self._log(
                "swiggy_sync_complete",
                orders=order_result,
                feedback=feedback_result,
                reservations=reservation_result,
            )
            return {
                "orders":       order_result,
                "feedback":     feedback_result,
                "reservations": reservation_result,
            }

        except Exception as exc:
            self._repo.update_sync_status(self.org_id, "swiggy", "error", error=str(exc))
            self._log("swiggy_sync_error", error=str(exc))
            return {
                "orders":       {"synced": 0, "skipped": 0, "errors": 1},
                "feedback":     {"synced": 0, "skipped": 0, "errors": 0},
                "reservations": {"synced": 0, "skipped": 0, "errors": 0},
            }

    async def enrich(self, context: dict) -> dict | None:
        raise NotImplementedError(
            "SwiggyConnector.enrich() will be implemented in P6-S06 through P6-S08 "
            "(CompetitorEnricher via Food MCP, OccupancyEnricher via Dineout MCP, "
            "ProcurementEnricher via Instamart MCP)."
        )

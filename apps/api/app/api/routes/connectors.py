"""Connectors routes — Swiggy sync trigger and connector status."""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.settings import get_settings
from app.infrastructure.db.models import Feedback, FeedbackSource, Order
from app.infrastructure.swiggy.client import SwiggyMCPClient
from app.infrastructure.swiggy.connector_repository import ConnectorRepository
from app.infrastructure.swiggy.swiggy_connector import SwiggyConnector

log = structlog.get_logger()
router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.post("/swiggy/sync")
async def sync_swiggy(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger a live Swiggy MCP sync.

    Calls get_food_orders, track_food_order, and get_booking_status on the
    real Swiggy API. Returns sync results with counts per service.
    """
    settings = get_settings()

    if not settings.swiggy_access_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "SWIGGY_ACCESS_TOKEN not configured. "
                "Run: python scripts/get_swiggy_token.py"
            ),
        )

    if not settings.swiggy_address_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "SWIGGY_ADDRESS_ID not configured. "
                "Run: python scripts/get_swiggy_token.py"
            ),
        )

    org_id = current_user["org_id"]
    client = SwiggyMCPClient()
    repo = ConnectorRepository(db)
    connector = SwiggyConnector(client, db, org_id, repo)

    results = await connector.sync(settings.swiggy_address_id)

    return {
        "status": "success",
        "message": "Live Swiggy data synced. Check orders and feedback tables.",
        "results": results,
    }


@router.get("/status")
async def get_connector_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return connection status for all connectors for this org.

    Used by the /connectors frontend page (P6-F04).
    """
    org_id = current_user["org_id"]
    settings = get_settings()
    repo = ConnectorRepository(db)

    connector = repo.get(org_id, "swiggy")

    swiggy_orders = (
        db.query(Order)
        .filter(Order.source == "swiggy")
        .count()
    )

    swiggy_feedback = (
        db.query(Feedback)
        .filter(Feedback.source == FeedbackSource.swiggy_delivery)
        .count()
    )

    return {
        "connectors": [
            {
                "type": "swiggy",
                "name": "Swiggy",
                "logo": "/swiggy-logo.png",
                "connected": bool(settings.swiggy_access_token),
                "last_sync_at": (
                    connector.last_sync_at.isoformat()
                    if connector and connector.last_sync_at
                    else None
                ),
                "sync_status": connector.sync_status if connector else "never_synced",
                "orders_synced": swiggy_orders,
                "feedback_synced": swiggy_feedback,
                "address_configured": bool(settings.swiggy_address_id),
            }
        ]
    }

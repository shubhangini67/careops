"""ConnectorRepository — DB access layer for the connectors table.

Handles upsert, token rotation, sync-status tracking, and listing active
connectors. All methods are synchronous (SQLAlchemy Session) to match the
existing DB layer pattern in this codebase.
"""

from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Connector

log = structlog.get_logger()


class ConnectorRepository:
    """CRUD interface for the connectors table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, org_id: int, connector_type: str) -> Optional[Connector]:
        """Return the connector row for (org_id, connector_type), or None."""
        return (
            self.db.query(Connector)
            .filter_by(org_id=org_id, connector_type=connector_type)
            .first()
        )

    def upsert(self, org_id: int, connector_type: str, **kwargs) -> Connector:
        """Create or update the connector row. Returns the saved instance."""
        connector = self.get(org_id, connector_type)
        if connector is None:
            connector = Connector(org_id=org_id, connector_type=connector_type)
            self.db.add(connector)

        for key, value in kwargs.items():
            setattr(connector, key, value)

        connector.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(connector)
        log.info("connector_upserted", org_id=org_id, connector_type=connector_type)
        return connector

    def update_sync_status(
        self,
        org_id: int,
        connector_type: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Update sync_status and optionally increment error_count + last_error."""
        connector = self.get(org_id, connector_type)
        if connector is None:
            connector = Connector(org_id=org_id, connector_type=connector_type)
            self.db.add(connector)
            log.info("connector_auto_created", org_id=org_id, connector_type=connector_type)

        connector.sync_status = status
        connector.updated_at = datetime.utcnow()

        if error is not None:
            connector.last_error = error
            connector.error_count = (connector.error_count or 0) + 1
        else:
            connector.last_error = None

        if status == "success":
            connector.last_sync_at = datetime.utcnow()

        self.db.commit()

    def update_token(
        self,
        org_id: int,
        connector_type: str,
        token: str,
        expires_at: datetime,
    ) -> None:
        """Store a new (encrypted) token and its expiry."""
        connector = self.get(org_id, connector_type)
        if connector is None:
            connector = Connector(org_id=org_id, connector_type=connector_type)
            self.db.add(connector)

        connector.access_token_encrypted = token
        connector.token_expires_at = expires_at
        connector.updated_at = datetime.utcnow()
        self.db.commit()
        log.info("connector_token_updated", org_id=org_id, connector_type=connector_type)

    def list_active(self, connector_type: Optional[str] = None) -> list[Connector]:
        """Return connectors that have a token set. Optionally filter by type."""
        q = self.db.query(Connector).filter(
            Connector.access_token_encrypted.isnot(None)
        )
        if connector_type:
            q = q.filter_by(connector_type=connector_type)
        return q.all()

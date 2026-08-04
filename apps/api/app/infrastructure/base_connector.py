"""BaseConnector ABC — contract for all external platform connectors.

Every connector (Swiggy live; Square POS, Google Reviews as further
examples of the pattern) implements this interface. Two modes:

  sync()   — nightly job, writes historical data to the DB (Layer 0)
  enrich() — at planning time, returns live signals without touching the DB

Graceful degradation: enrich() must return None on any failure so that
LangGraph nodes can fall back to synthetic data without crashing.

This pattern is intentionally generic so the system can extend to future
integrations without touching this file or provider_registry.py's structure
-- only adding a new entry. Natural candidates: a different POS system, a
loyalty/rewards platform, an accounting or inventory tool, a review
aggregator, a payments processor. Kept single-provider (Swiggy) on the food
delivery / dining-out / quick-commerce side for now.
"""

import structlog
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

log = structlog.get_logger()


class BaseConnector(ABC):
    """Abstract connector that every platform integration must implement.

    client is intentionally untyped (Any) -- this base class must not assume
    any single platform's client shape. SwiggyConnector uses SwiggyMCPClient;
    a connector with no live API yet can pass None.
    """

    def __init__(self, client: Any, db: Session, org_id: int) -> None:
        self._client = client
        self._db = db
        self.org_id = org_id

    @abstractmethod
    async def sync(self) -> dict:
        """Nightly job. Pull historical data. Write to DB (Layer 0).

        Returns a summary dict: {"synced": N, "errors": M, ...}
        """

    @abstractmethod
    async def enrich(self, context: dict) -> dict | None:
        """At planning time. Fetch live signals. Do NOT write to DB.

        context — caller-supplied hints (scenario, target_date, etc.)
        Returns enrichment dict on success, None on any failure.
        """

    def _log(self, msg: str, **kwargs) -> None:
        """Structured log with org_id bound."""
        log.info(msg, org_id=self.org_id, connector=self.__class__.__name__, **kwargs)

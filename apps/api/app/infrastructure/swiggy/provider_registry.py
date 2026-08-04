"""
Capability-to-provider registry for MCP connectors.

Maps planning capabilities to ordered provider lists. At runtime, returns
the highest-priority provider that has an active connector record for the org.

No DB migration needed — reads from the existing `connectors` table which
already tracks per-org platform health (sync_status, error_count).

Adding a new provider means:
  1. Insert a row into CAPABILITY_PROVIDERS below
  2. Implement a BaseConnector subclass for it (see base_connector.py for the
     kinds of providers this fits -- POS systems, review platforms, loyalty/
     rewards, accounting/inventory tools, payment processors)
  3. The registry automatically routes to it once the org has an active connector row
     with a healthy sync_status for that provider -- no other code changes needed
"""

from sqlalchemy.orm import Session

CAPABILITY_PROVIDERS: dict[str, list[str]] = {
    "competitor_pricing": ["swiggy"],
    "reservation_data":   ["swiggy"],
    "procurement":        ["swiggy"],
    "order_history":      ["swiggy"],
}

# Maps capability → Swiggy endpoint tag for circuit breaker lookup.
# Only needed for Swiggy; other providers use their own circuit keys.
_SWIGGY_CAPABILITY_ENDPOINT: dict[str, str] = {
    "competitor_pricing": "food",
    "reservation_data":   "dineout",
    "procurement":        "im",
    "order_history":      "food",
}

_HEALTHY_STATUSES = {"success", "syncing"}


class ProviderRegistry:
    """
    Routes a planning capability to the best available provider for an org.

    Priority is positional: first provider in CAPABILITY_PROVIDERS[capability]
    that passes BOTH checks wins:
      1. DB health  — connector row exists with sync_status in _HEALTHY_STATUSES
                      (updated by nightly sync job)
      2. Circuit breaker — real-time open/closed state from Redis
                      (updated on every MCP call failure/success)

    Combining both gives accurate routing: DB catches connectors that were
    never configured or failed overnight; circuit breaker catches mid-day
    degradation that the DB hasn't seen yet.
    """

    def get_provider(self, org_id: int, capability: str, db: Session) -> str | None:
        """Synchronous version — DB health only. Use get_provider_async for full check."""
        from app.infrastructure.db.models import Connector

        candidates = CAPABILITY_PROVIDERS.get(capability, [])
        if not candidates:
            return None

        active_types = {
            row.connector_type
            for row in db.query(Connector).filter(
                Connector.org_id == org_id,
                Connector.sync_status.in_(list(_HEALTHY_STATUSES)),
            ).all()
        }
        for provider in candidates:
            if provider in active_types:
                return provider
        return None

    async def get_provider_async(
        self, org_id: int, capability: str, db: Session
    ) -> str | None:
        """
        Async version — DB health AND real-time circuit breaker state.

        Skips any provider whose circuit is open, falling through to the next
        priority candidate. Returns None if all candidates are unavailable.
        """
        from app.infrastructure.db.models import Connector
        from app.infrastructure.swiggy.circuit_breaker import is_open

        candidates = CAPABILITY_PROVIDERS.get(capability, [])
        if not candidates:
            return None

        active_types = {
            row.connector_type
            for row in db.query(Connector).filter(
                Connector.org_id == org_id,
                Connector.sync_status.in_(list(_HEALTHY_STATUSES)),
            ).all()
        }

        for provider in candidates:
            if provider not in active_types:
                continue
            if provider == "swiggy":
                endpoint = _SWIGGY_CAPABILITY_ENDPOINT.get(capability, "food")
                if await is_open(provider, endpoint):
                    continue    # circuit open — try next provider
            return provider

        return None

    def all_providers_for(self, capability: str) -> list[str]:
        """Return the full provider priority list for a capability."""
        return list(CAPABILITY_PROVIDERS.get(capability, []))

    def capabilities(self) -> dict[str, list[str]]:
        """Return the full capability → providers map."""
        return dict(CAPABILITY_PROVIDERS)

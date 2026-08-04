"""
Redis-backed circuit breaker for external MCP provider calls.

States (TTL-based, no persistent state machine):
  CLOSED — normal; fewer than FAILURE_THRESHOLD failures in WINDOW_SECONDS
  OPEN   — circuit:open:{provider}:{tag} key exists; calls short-circuit to None

On FAILURE_THRESHOLD reached → SET open key with OPEN_SECONDS TTL (auto-resets).
On success → DELETE failure counter so the circuit can close faster.
On Redis down → fail open (let the call through; circuit logic is optional).
"""

import structlog

import redis.asyncio as aioredis

from app.core.settings import get_settings

# structlog, not stdlib logging: stdlib .info()/.debug() calls are silently
# dropped in this app (no logging.basicConfig() is ever called, so the root
# logger's effective level is WARNING and there's no handler attached).
logger = structlog.get_logger()

FAILURE_THRESHOLD = 5       # failures within WINDOW_SECONDS to open circuit
WINDOW_SECONDS    = 300     # failure counter TTL (5 min)
OPEN_SECONDS      = 600     # open circuit duration (10 min)

# Widened from (3 failures / 30 min open) after repeated trips during heavy market-page
# development: CompetitorEnricher now makes more Food MCP calls per run (pagination +
# fetch_food_coupons + get_restaurant_menu), so occasional transient blips hit the old
# threshold too easily. Higher threshold tolerates blips better; shorter open window
# means a real outage still degrades gracefully but recovers faster instead of blocking
# the whole /market page for 30 minutes over 3 flaky calls.

_redis_client: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def is_open(provider: str, tag: str) -> bool:
    """True if the circuit is open — caller should skip the MCP call."""
    try:
        redis = await _get_redis()
        return bool(await redis.exists(f"circuit:open:{provider}:{tag}"))
    except Exception:
        return False    # fail open: if Redis is down, let the call through


async def record_failure(provider: str, tag: str) -> None:
    """Increment failure counter. Opens circuit when threshold is reached."""
    try:
        redis    = await _get_redis()
        fail_key = f"circuit:fail:{provider}:{tag}"
        open_key = f"circuit:open:{provider}:{tag}"

        count = await redis.incr(fail_key)
        if count == 1:
            await redis.expire(fail_key, WINDOW_SECONDS)

        if count >= FAILURE_THRESHOLD:
            await redis.setex(open_key, OPEN_SECONDS, "1")
            logger.warning(
                "circuit_opened",
                provider=provider, endpoint=tag, failures=count, ttl_seconds=OPEN_SECONDS,
            )
    except Exception as exc:
        logger.debug("circuit_breaker_record_failure_error", error=str(exc))


async def record_success(provider: str, tag: str) -> None:
    """On success, clear failure counter so circuit closes faster."""
    try:
        redis = await _get_redis()
        await redis.delete(f"circuit:fail:{provider}:{tag}")
    except Exception:
        pass


async def get_state(provider: str, tag: str) -> dict:
    """Return current circuit state — used by health endpoints and observability."""
    try:
        redis    = await _get_redis()
        open_key = f"circuit:open:{provider}:{tag}"
        fail_key = f"circuit:fail:{provider}:{tag}"

        open_exists = bool(await redis.exists(open_key))
        ttl         = await redis.ttl(open_key) if open_exists else -1
        failures    = int(await redis.get(fail_key) or 0)

        return {
            "provider":          provider,
            "endpoint":          tag,
            "state":             "open" if open_exists else "closed",
            "recent_failures":   failures,
            "resets_in_seconds": ttl if ttl > 0 else None,
        }
    except Exception:
        return {"provider": provider, "endpoint": tag, "state": "unknown"}

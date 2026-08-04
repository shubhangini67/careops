"""Redis-backed cache for planning run results.

Cache key:  plan:{org_id}:{scenario}:{target_date}   (TTL 1 hour)
Bypass when: simulation_mode=True, force_critic_decision set, debug=True

All public functions swallow Redis errors silently — if Redis is down the
planning run still executes; it just won't be cached.
"""

import json
from datetime import date
from typing import Optional

import redis.asyncio as aioredis
import structlog

from app.core.settings import get_settings

# structlog, not stdlib logging: stdlib .debug() calls are silently dropped
# in this app (no logging.basicConfig() is ever called).
logger = structlog.get_logger()

_client: Optional[aioredis.Redis] = None

PLAN_CACHE_TTL = 3600  # 1 hour


async def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


def build_cache_key(org_id: int, scenario: str, target_date: Optional[str]) -> str:
    resolved_date = target_date or date.today().isoformat()
    return f"plan:{org_id}:{scenario}:{resolved_date}"


async def get_cached_plan(key: str) -> Optional[dict]:
    try:
        client = await _get_client()
        raw = await client.get(key)
        if raw:
            logger.debug("plan_cache_hit", key=key)
            return json.loads(raw)
    except Exception as exc:
        logger.warning("plan_cache_get_failed", key=key, error=str(exc))
    return None


async def cache_plan(key: str, data: dict, ttl: int = PLAN_CACHE_TTL) -> None:
    try:
        client = await _get_client()
        await client.setex(key, ttl, json.dumps(data, default=str))
        logger.debug("plan_cache_set", key=key, ttl_seconds=ttl)
    except Exception as exc:
        logger.warning("plan_cache_set_failed", key=key, error=str(exc))

import time

from app.api.schemas.common import DependencyStatus
from app.core.constants import (
    DEPENDENCY_LLM,
    DEPENDENCY_POSTGRES,
    DEPENDENCY_QDRANT,
    DEPENDENCY_REDIS,
)
from app.core.settings import Settings


def check_postgres(settings: Settings) -> DependencyStatus:
    import psycopg2

    t0 = time.perf_counter()
    try:
        conn = psycopg2.connect(settings.postgres_url, connect_timeout=3)
        conn.close()
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return DependencyStatus(
            name=DEPENDENCY_POSTGRES, ok=True,
            detail="Connected", latency_ms=latency,
        )
    except Exception as exc:
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return DependencyStatus(
            name=DEPENDENCY_POSTGRES, ok=False,
            detail=str(exc)[:200], latency_ms=latency,
        )


def check_qdrant(settings: Settings) -> DependencyStatus:
    from qdrant_client import QdrantClient

    t0 = time.perf_counter()
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=3)
        client.get_collections()
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return DependencyStatus(
            name=DEPENDENCY_QDRANT, ok=True,
            detail="Connected", latency_ms=latency,
        )
    except Exception as exc:
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return DependencyStatus(
            name=DEPENDENCY_QDRANT, ok=False,
            detail=str(exc)[:200], latency_ms=latency,
        )


def check_redis(settings: Settings) -> DependencyStatus:
    import redis

    t0 = time.perf_counter()
    try:
        client = redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
        client.ping()
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return DependencyStatus(
            name=DEPENDENCY_REDIS, ok=True,
            detail="Connected", latency_ms=latency,
        )
    except Exception as exc:
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return DependencyStatus(
            name=DEPENDENCY_REDIS, ok=False,
            detail=str(exc)[:200], latency_ms=latency,
        )


def check_llm(settings: Settings) -> DependencyStatus:
    has_provider = bool(settings.llm_provider)
    has_key = bool(settings.gemini_api_key) if settings.llm_provider == "gemini" else bool(settings.groq_api_key)
    ok = has_provider and has_key
    return DependencyStatus(
        name=DEPENDENCY_LLM, ok=ok,
        detail="Configured" if ok else "Missing provider config or API key",
    )


async def check_swiggy_circuits() -> list[dict]:
    """Return circuit breaker state for all known Swiggy endpoints."""
    from app.infrastructure.swiggy.circuit_breaker import get_state
    endpoints = ["food", "im", "dineout"]
    return [await get_state("swiggy", tag) for tag in endpoints]


def get_dependency_statuses(settings: Settings) -> list[DependencyStatus]:
    return [
        check_postgres(settings),
        check_qdrant(settings),
        check_redis(settings),
        check_llm(settings),
    ]

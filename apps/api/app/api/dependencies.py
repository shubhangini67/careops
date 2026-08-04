"""
FastAPI dependency providers for infrastructure services.

All route handlers receive these via Depends() — never instantiate
infrastructure directly inside a route function.

Imports are intentionally lazy (inside functions) so that test
collection never triggers missing-package errors when deps are mocked.
"""

import asyncio
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

_bearer = HTTPBearer(auto_error=False)

# Module-level engine shared across all requests (avoids creating a new pool per call).
_engine = None
_SessionLocal = None

# Module-level checkpointer + pool, lazily created on first use and shared
# across all requests (mirrors _get_shared_engine()'s pattern) -- opening a
# fresh connection pool and re-running .setup() per request would be both
# slow and wrong (setup() is idempotent DDL, not something to race).
_checkpointer = None
_checkpointer_lock = asyncio.Lock()


def _get_shared_engine():
    global _engine, _SessionLocal
    if _engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.settings import get_settings
        _engine = create_engine(
            get_settings().postgres_url,
            pool_size=10,
            max_overflow=5,
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine, _SessionLocal


# ── Database ─────────────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and close it when the request is done."""
    _, SessionLocal = _get_shared_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_factory():
    """Return a sessionmaker so pipeline nodes can create their own isolated sessions.

    Each parallel LangGraph node calls db_factory() to get its own Session.
    This prevents the shared-session thread-safety issue when sync DB queries
    run concurrently via asyncio.to_thread().
    """
    _, SessionLocal = _get_shared_engine()
    return SessionLocal


# ── LangGraph checkpointing ───────────────────────────────────────────────────

async def get_checkpointer():
    """Return the shared AsyncPostgresSaver, creating its connection pool and
    running its (idempotent) table setup on first call.

    Enables true node re-execution for Kindred replay: with every superstep
    persisted, a replay can fetch the exact checkpoint immediately before a
    given node ran and resume the graph from there with current code --
    catching a real prompt/logic regression, not just LLM sampling variance
    (see docs/PRODUCT_MODES.md's P6-A27 note on why this was previously
    deliberately left unbuilt). Returns None if Postgres is unreachable so a
    planning run still completes uncheckpointed rather than failing outright.
    """
    global _checkpointer
    if _checkpointer is None:
        async with _checkpointer_lock:
            if _checkpointer is None:
                try:
                    from psycopg_pool import AsyncConnectionPool
                    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                    from app.core.settings import get_settings

                    pool = AsyncConnectionPool(
                        conninfo=get_settings().postgres_url,
                        max_size=10,
                        kwargs={"autocommit": True, "prepare_threshold": 0},
                        open=False,
                    )
                    await pool.open()
                    saver = AsyncPostgresSaver(pool)
                    await saver.setup()
                    _checkpointer = saver
                except Exception as exc:
                    # str(exc) only, no exc_info -- a raw traceback can contain
                    # non-ASCII bytes that crash structlog's print() under
                    # Windows' default cp1252 console encoding, which would
                    # otherwise mask the real error with an unrelated one.
                    try:
                        import structlog
                        structlog.get_logger().warning("checkpointer_setup_failed", error=str(exc)[:300])
                    except Exception:
                        pass
                    return None
    return _checkpointer


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Decode the Bearer JWT and return {user_id, org_id, role}."""
    from app.core.auth import decode_token

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    org_id  = payload.get("org_id")
    role    = payload.get("role")

    if not user_id or not org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")

    return {"user_id": int(user_id), "org_id": int(org_id), "role": role}


# ── LLM provider ─────────────────────────────────────────────────────────────

def get_llm():
    """Return the configured LLM provider with automatic fallback."""
    from app.infrastructure.llm.factory import create_llm_provider

    return create_llm_provider()


# ── Vector memory ─────────────────────────────────────────────────────────────

def get_memory():
    """Return a MemoryService backed by Qdrant."""
    from app.infrastructure.vector.qdrant_client import get_qdrant_client
    from app.infrastructure.vector.embedding_service import EmbeddingService
    from app.infrastructure.vector.memory_service import MemoryService

    qdrant = get_qdrant_client()
    embedder = EmbeddingService()
    return MemoryService(qdrant=qdrant, embedder=embedder)


def get_semantic_cache():
    """Return a SemanticPlanCache backed by Qdrant (P6-S04)."""
    from app.infrastructure.vector.qdrant_client import get_qdrant_client
    from app.infrastructure.vector.embedding_service import EmbeddingService
    from app.infrastructure.cache.semantic_cache import SemanticPlanCache

    qdrant   = get_qdrant_client()
    embedder = EmbeddingService()
    return SemanticPlanCache(qdrant=qdrant, embedder=embedder)


def get_chat_cache():
    """Return a SemanticChatCache backed by Qdrant (P6-S04)."""
    from app.infrastructure.vector.qdrant_client import get_qdrant_client
    from app.infrastructure.vector.embedding_service import EmbeddingService
    from app.infrastructure.cache.semantic_cache import SemanticChatCache

    qdrant   = get_qdrant_client()
    embedder = EmbeddingService()
    return SemanticChatCache(qdrant=qdrant, embedder=embedder)


def get_session_memory():
    """Return a SessionMemoryService backed by Qdrant (P6-S04)."""
    from app.infrastructure.vector.qdrant_client import get_qdrant_client
    from app.infrastructure.vector.embedding_service import EmbeddingService
    from app.infrastructure.vector.session_memory import SessionMemoryService

    qdrant   = get_qdrant_client()
    embedder = EmbeddingService()
    return SessionMemoryService(qdrant=qdrant, embedder=embedder)


# ── Orchestration deps bundle ─────────────────────────────────────────────────

async def get_orchestration_deps(
    db: Session = Depends(get_db),
    llm=Depends(get_llm),
    memory=Depends(get_memory),
) -> dict:
    """
    Bundle all infrastructure deps into the dict shape that
    build_graph() and run_friday_rush() expect.
    """
    from app.core.settings import get_settings
    from app.infrastructure.llm.factory import create_tiered_llm_providers

    deps = {
        "db": db, "llm": llm, "memory": memory, "db_factory": get_db_factory(),
        "checkpointer": await get_checkpointer(),
    }
    settings = get_settings()
    if settings.llm_provider.strip().lower() == "comet" and settings.comet_tiered:
        deps["llm_registry"] = create_tiered_llm_providers(settings)

    # Semantic cache and planning memory — silently skipped if Qdrant / Gemini not configured
    try:
        from app.infrastructure.vector.qdrant_client import get_qdrant_client
        from app.infrastructure.vector.embedding_service import EmbeddingService
        from app.infrastructure.cache.semantic_cache import SemanticPlanCache
        from app.infrastructure.vector.planning_memory import PlanningMemoryService

        qdrant   = get_qdrant_client()
        embedder = EmbeddingService()
        deps["semantic_cache"]   = SemanticPlanCache(qdrant=qdrant, embedder=embedder)
        deps["planning_memory"]  = PlanningMemoryService(qdrant=qdrant, embedder=embedder)
    except Exception:
        pass

    return deps

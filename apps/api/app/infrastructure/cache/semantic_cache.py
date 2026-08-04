"""
Qdrant-backed semantic cache for planning runs and chatbot responses (P6-S04).

Planning cache: collection 'semantic_cache'
  - Key: embed("org:{org_id} scenario:{scenario} date:{date}")
  - Hit threshold: cosine similarity >= 0.92
  - TTL: 1 hour (checked via payload.cached_at)

Chat cache: collection 'chat_semantic_cache'
  - Key: embed(question)
  - Hit threshold: cosine similarity >= 0.92
  - TTL: 24 hours

Both caches degrade gracefully — errors return None (cache miss).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from app.infrastructure.vector.qdrant_client import ensure_collection
from app.infrastructure.vector.embedding_service import EmbeddingService

# structlog, not stdlib logging: stdlib .debug() calls are silently dropped
# in this app (no logging.basicConfig() is ever called).
logger = structlog.get_logger()

PLAN_CACHE_COLLECTION = "semantic_cache"
CHAT_CACHE_COLLECTION = "chat_semantic_cache"
SIMILARITY_THRESHOLD  = 0.92
PLAN_TTL_HOURS        = 1
CHAT_TTL_HOURS        = 24


class SemanticPlanCache:
    """Embedding-based cache for planning run results."""

    def __init__(self, qdrant: QdrantClient, embedder: EmbeddingService) -> None:
        self.qdrant   = qdrant
        self.embedder = embedder
        ensure_collection(self.qdrant, PLAN_CACHE_COLLECTION)

    def _query_text(self, org_id: int, scenario: str, target_date: Optional[str]) -> str:
        """Lightweight query embedding — only what's known at retrieval time."""
        return f"org:{org_id} scenario:{scenario} date:{target_date or 'next'}"

    @staticmethod
    def _storage_text(
        org_id: int,
        scenario: str,
        target_date: Optional[str],
        conditions: Optional[dict],
    ) -> str:
        """Richer storage embedding — includes actual run conditions so future
        retrievals can match on scenario type AND situational signals, not just date."""
        base  = f"org:{org_id} scenario:{scenario} date:{target_date or 'next'}"
        if not conditions:
            return base
        parts = [base]
        if conditions.get("demand_ratio") is not None:
            parts.append(f"demand_ratio:{conditions['demand_ratio']}")
        if conditions.get("occupancy") is not None:
            parts.append(f"occupancy:{conditions['occupancy']}%")
        if conditions.get("shortages"):
            parts.append(f"shortages:{','.join(str(s) for s in conditions['shortages'][:4])}")
        if conditions.get("verdict"):
            parts.append(f"verdict:{conditions['verdict']}")
        return " ".join(parts)

    def get(self, org_id: int, scenario: str, target_date: Optional[str]) -> Optional[dict]:
        """Return cached plan if similarity >= 0.92 and not expired."""
        try:
            vector = self.embedder.embed(self._query_text(org_id, scenario, target_date))
            results = self.qdrant.query_points(
                collection_name=PLAN_CACHE_COLLECTION,
                query=vector,
                query_filter=Filter(
                    must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))]
                ),
                limit=1,
                with_payload=True,
            ).points

            if not results or results[0].score < SIMILARITY_THRESHOLD:
                return None

            payload = results[0].payload
            cached_at_str = payload.get("cached_at")
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                if datetime.now(timezone.utc) - cached_at > timedelta(hours=PLAN_TTL_HOURS):
                    return None

            raw = payload.get("result")
            if raw is None:
                return None
            return json.loads(raw) if isinstance(raw, str) else raw

        except Exception as exc:
            logger.debug("semantic_plan_cache_get_failed", error=str(exc))
            return None

    def set(
        self,
        org_id: int,
        scenario: str,
        target_date: Optional[str],
        result: dict,
        conditions: Optional[dict] = None,
    ) -> None:
        """Store an approved planning result in the semantic cache.

        Uses a richer storage embedding (conditions included) so future
        retrievals can match on situational signals, not just scenario + date.
        """
        try:
            storage_text = self._storage_text(org_id, scenario, target_date, conditions)
            vector = self.embedder.embed(storage_text)
            self.qdrant.upsert(
                collection_name=PLAN_CACHE_COLLECTION,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "org_id":      org_id,
                        "scenario":    scenario,
                        "target_date": target_date or "next",
                        "cached_at":   datetime.now(timezone.utc).isoformat(),
                        "result":      json.dumps(result, default=str),
                    },
                )],
            )
        except Exception as exc:
            logger.debug("semantic_plan_cache_set_failed", error=str(exc))


class SemanticChatCache:
    """Embedding-based cache for chatbot question-answer pairs."""

    def __init__(self, qdrant: QdrantClient, embedder: EmbeddingService) -> None:
        self.qdrant   = qdrant
        self.embedder = embedder
        ensure_collection(self.qdrant, CHAT_CACHE_COLLECTION)

    def get(self, org_id: int, question: str) -> Optional[str]:
        """Return cached answer if a similar question was asked recently."""
        try:
            vector = self.embedder.embed(question)
            results = self.qdrant.query_points(
                collection_name=CHAT_CACHE_COLLECTION,
                query=vector,
                query_filter=Filter(
                    must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))]
                ),
                limit=1,
                with_payload=True,
            ).points

            if not results or results[0].score < SIMILARITY_THRESHOLD:
                return None

            payload = results[0].payload
            cached_at_str = payload.get("cached_at")
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                if datetime.now(timezone.utc) - cached_at > timedelta(hours=CHAT_TTL_HOURS):
                    return None

            return payload.get("answer")

        except Exception as exc:
            logger.debug("semantic_chat_cache_get_failed", error=str(exc))
            return None

    def set(self, org_id: int, question: str, answer: str) -> None:
        """Store a Q&A pair in the semantic cache."""
        try:
            vector = self.embedder.embed(question)
            self.qdrant.upsert(
                collection_name=CHAT_CACHE_COLLECTION,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "org_id":    org_id,
                        "question":  question[:500],
                        "answer":    answer,
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    },
                )],
            )
        except Exception as exc:
            logger.debug("semantic_chat_cache_set_failed", error=str(exc))

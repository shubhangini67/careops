"""
Qdrant-backed cross-session memory for the chatbot (P6-S04).

Stores conversation summaries per (org_id, user_id) in the 'chat_sessions'
collection. On session start, retrieves the most recent summaries so the LLM
has continuity across sessions without replaying full history.

Storage format per point:
  vector  : embedding of the session summary
  payload : {org_id, user_id, summary, created_at, message_count}
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition, Filter, MatchValue, PointStruct
)

from app.infrastructure.vector.qdrant_client import ensure_collection
from app.infrastructure.vector.embedding_service import EmbeddingService

# structlog, not stdlib logging: stdlib .debug() calls are silently dropped
# in this app (no logging.basicConfig() is ever called).
logger = structlog.get_logger()

SESSION_COLLECTION = "chat_sessions"
MAX_SESSIONS_STORED = 20


class SessionMemoryService:
    """Stores and retrieves chatbot session summaries from Qdrant."""

    def __init__(self, qdrant: QdrantClient, embedder: EmbeddingService) -> None:
        self.qdrant   = qdrant
        self.embedder = embedder
        ensure_collection(self.qdrant, SESSION_COLLECTION)

    def _org_user_filter(self, org_id: int, user_id: int) -> Filter:
        return Filter(must=[
            FieldCondition(key="org_id",  match=MatchValue(value=org_id)),
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
        ])

    def store_session(
        self,
        org_id: int,
        user_id: int,
        summary: str,
        message_count: int = 0,
    ) -> None:
        """Embed and store a session summary in Qdrant."""
        try:
            vector = self.embedder.embed(summary)
            self.qdrant.upsert(
                collection_name=SESSION_COLLECTION,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "org_id":        org_id,
                        "user_id":       user_id,
                        "summary":       summary,
                        "message_count": message_count,
                        "created_at":    datetime.now(timezone.utc).isoformat(),
                    },
                )],
            )
        except Exception as exc:
            logger.debug("session_memory_store_failed", error=str(exc))

    def get_recent_sessions(
        self,
        org_id: int,
        user_id: int,
        query: str = "recent conversation context",
        top_k: int = 3,
    ) -> list[dict]:
        """
        Retrieve the most relevant past session summaries for context injection.
        Uses semantic similarity so the most topically relevant sessions are returned,
        not just the most recent.
        """
        try:
            vector = self.embedder.embed(query)
            results = self.qdrant.query_points(
                collection_name=SESSION_COLLECTION,
                query=vector,
                query_filter=self._org_user_filter(org_id, user_id),
                limit=top_k,
                with_payload=True,
            ).points
            return [
                {
                    "summary":    r.payload.get("summary", ""),
                    "created_at": r.payload.get("created_at", ""),
                    "score":      round(r.score, 3),
                }
                for r in results
            ]
        except Exception as exc:
            logger.debug("session_memory_retrieve_failed", error=str(exc))
            return []

    @staticmethod
    def build_summary_from_messages(messages: list[dict], question: str) -> str:
        """
        Lightweight local summary: extract key topics from the conversation
        without an LLM call. Used when the session ends.
        """
        turns = len(messages) // 2
        topics: list[str] = []

        for msg in messages:
            text = msg.get("content", "").lower()
            if any(kw in text for kw in ("inventory", "stock", "shortage")):
                topics.append("inventory")
            if any(kw in text for kw in ("forecast", "demand", "predicted")):
                topics.append("demand")
            if any(kw in text for kw in ("menu", "highlight", "deprioritize")):
                topics.append("menu")
            if any(kw in text for kw in ("reservation", "booking", "cover")):
                topics.append("reservations")
            if any(kw in text for kw in ("critic", "score", "rejected", "approved")):
                topics.append("critic evaluation")

        unique_topics = list(dict.fromkeys(topics))
        topic_str = ", ".join(unique_topics) if unique_topics else "general operations"
        return (
            f"Session with {turns} turn(s) covering: {topic_str}. "
            f"Last question: {question[:200]}"
        )

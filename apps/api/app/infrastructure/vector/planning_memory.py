"""
Long-term planning memory: stores per-run insights in Qdrant after approved plans,
retrieved with exponential recency decay during qdrant_enrichment.

Collection: 'planning_memory'
  vector  : embedding of extracted insight text (scenario + conditions + outcome)
  payload : {org_id, scenario, run_id, generated_at (ISO), insights}

Retrieval scoring: raw_score * 2^(-age_days / HALF_LIFE_DAYS)
Staleness cutoff : memories older than MAX_MEMORY_AGE_DAYS are skipped.
"""

import math
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

PLANNING_MEMORY_COLLECTION = "planning_memory"
RECENCY_HALF_LIFE_DAYS     = 14   # score halves every 14 days
MAX_MEMORY_AGE_DAYS        = 90   # hard cutoff; older memories are excluded


class PlanningMemoryService:
    """Stores approved planning run insights and retrieves them with recency decay."""

    def __init__(self, qdrant: QdrantClient, embedder: EmbeddingService) -> None:
        self.qdrant   = qdrant
        self.embedder = embedder
        ensure_collection(self.qdrant, PLANNING_MEMORY_COLLECTION)

    # ── Insight extraction ────────────────────────────────────────────────────

    @staticmethod
    def _extract_insight_text(scenario: str, final_response: dict) -> str:
        """Build a rich semantic text from a planning response for embedding.

        Embeds condition signals (demand ratio, shortages, occupancy, outcome) so
        future retrievals match on scenario *type + conditions*, not just date.
        """
        recs   = final_response.get("recommendations", {})
        critic = final_response.get("critic", {})
        parts  = [f"scenario:{scenario}"]

        forecast_data = recs.get("demand_forecast", {})
        if isinstance(forecast_data, dict):
            data      = forecast_data.get("data") or forecast_data
            predicted = data.get("predicted_orders")
            avg       = data.get("avg_friday_orders") or data.get("avg_same_day_orders")
            if predicted and avg:
                ratio = round(predicted / max(avg, 1), 2)
                parts.append(f"demand_ratio:{ratio} predicted:{predicted}")

        inventory_data = recs.get("inventory", {})
        if isinstance(inventory_data, dict):
            data      = inventory_data.get("data") or inventory_data
            shortages = data.get("shortage_alerts") or []
            if shortages:
                items = [s.get("item", str(s)) if isinstance(s, dict) else str(s) for s in shortages[:6]]
                parts.append(f"shortages:{','.join(items)}")

        reservation_data = recs.get("reservation", {})
        if isinstance(reservation_data, dict):
            data = reservation_data.get("data") or reservation_data
            occ  = data.get("occupancy_pct")
            if occ is not None:
                parts.append(f"occupancy:{occ}%")

        if critic:
            parts.append(f"verdict:{critic.get('verdict', 'unknown')} score:{critic.get('score', 0):.2f}")

        menu_data = recs.get("menu_intelligence", {})
        if isinstance(menu_data, dict):
            rec = menu_data.get("recommendation") or ""
            if isinstance(rec, str) and rec:
                parts.append(f"menu:{rec[:150]}")

        return " | ".join(parts)

    # ── Store ─────────────────────────────────────────────────────────────────

    def store(
        self,
        org_id: int,
        scenario: str,
        run_id: Optional[int],
        final_response: dict,
    ) -> None:
        """Embed and persist insights from an approved planning run."""
        try:
            insight_text = self._extract_insight_text(scenario, final_response)
            vector       = self.embedder.embed(insight_text)
            self.qdrant.upsert(
                collection_name=PLANNING_MEMORY_COLLECTION,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "org_id":       org_id,
                        "scenario":     scenario,
                        "run_id":       run_id,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "insights":     insight_text,
                    },
                )],
            )
            logger.debug("planning_memory_stored", org_id=org_id, scenario=scenario)
        except Exception as exc:
            logger.warning("planning_memory_store_failed", error=str(exc))

    # ── Retrieve ──────────────────────────────────────────────────────────────

    def retrieve(
        self,
        org_id: int,
        scenario: str,
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """
        Retrieve past planning insights ranked by recency-decayed similarity.

        Score = raw_similarity * 2^(-age_days / HALF_LIFE_DAYS)
        Memories older than MAX_MEMORY_AGE_DAYS are excluded.
        Returns at most top_k results, sorted by decayed score descending.
        """
        try:
            vector  = self.embedder.embed(query)
            results = self.qdrant.query_points(
                collection_name=PLANNING_MEMORY_COLLECTION,
                query=vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(key="org_id",   match=MatchValue(value=org_id)),
                        FieldCondition(key="scenario",  match=MatchValue(value=scenario)),
                    ]
                ),
                limit=top_k * 2,
                with_payload=True,
            ).points

            now     = datetime.now(timezone.utc)
            decayed = []
            for r in results:
                generated_at = r.payload.get("generated_at")
                if not generated_at:
                    continue
                age_days = (now - datetime.fromisoformat(generated_at)).days
                if age_days > MAX_MEMORY_AGE_DAYS:
                    continue
                decay         = math.pow(2, -age_days / RECENCY_HALF_LIFE_DAYS)
                decayed_score = round(r.score * decay, 4)
                decayed.append({
                    "insights":     r.payload.get("insights", ""),
                    "generated_at": generated_at,
                    "age_days":     age_days,
                    "raw_score":    round(r.score, 3),
                    "score":        decayed_score,
                })

            decayed.sort(key=lambda x: x["score"], reverse=True)
            return decayed[:top_k]

        except Exception as exc:
            logger.warning("planning_memory_retrieve_failed", error=str(exc))
            return []

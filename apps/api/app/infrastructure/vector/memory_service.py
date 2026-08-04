from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue, PointStruct
import uuid

from app.infrastructure.vector.qdrant_client import ensure_collection
from app.infrastructure.vector.embedding_service import EmbeddingService


# Collection names
COMPLAINT_COLLECTION = "complaint_memory"
SOP_COLLECTION       = "sop_memory"

# Legacy demo vectors — purge before CareOps reseed
_RESTAURANT_KEYWORDS = (
    "pizza", "margherita", "garlic bread", "mozzarella", "swiggy", "zomato",
    "restaurant", "kitchen staff", "burger bun", "pepperoni", "dough",
)


class MemoryService:
    """Main interface for storing and retrieving vector memories in Qdrant."""

    def __init__(self, qdrant: QdrantClient, embedder: EmbeddingService):
        self.qdrant   = qdrant
        self.embedder = embedder

        # Ensure both collections exist
        ensure_collection(self.qdrant, COMPLAINT_COLLECTION)
        ensure_collection(self.qdrant, SOP_COLLECTION)

    def purge_org_memory(self, org_id: int) -> dict[str, int]:
        """Delete all vectors scoped to org_id from complaint and sop collections."""
        org_filter = Filter(must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))])
        selector = FilterSelector(filter=org_filter)
        removed: dict[str, int] = {}
        for collection in (COMPLAINT_COLLECTION, SOP_COLLECTION):
            before = self.qdrant.get_collection(collection).points_count
            self.qdrant.delete(collection_name=collection, points_selector=selector)
            after = self.qdrant.get_collection(collection).points_count
            removed[collection] = before - after
        return removed

    def purge_policy_vectors(self, org_id: int) -> int:
        """Delete sop_memory policy-index vectors (metadata.domain=hospital_operations)."""
        policy_filter = Filter(must=[
            FieldCondition(key="org_id", match=MatchValue(value=org_id)),
            FieldCondition(key="domain", match=MatchValue(value="hospital_operations")),
        ])
        before = self.qdrant.get_collection(SOP_COLLECTION).points_count
        self.qdrant.delete(
            collection_name=SOP_COLLECTION,
            points_selector=FilterSelector(filter=policy_filter),
        )
        after = self.qdrant.get_collection(SOP_COLLECTION).points_count
        return before - after

    def purge_legacy_restaurant_vectors(self, collections: list[str] | None = None) -> dict[str, int]:
        """Remove any remaining restaurant/Swiggy vectors by keyword scan."""
        targets = collections or [COMPLAINT_COLLECTION, SOP_COLLECTION, "planning_memory"]
        removed: dict[str, int] = {}
        for collection in targets:
            try:
                self.qdrant.get_collection(collection)
            except Exception:
                continue
            offset = None
            delete_ids: list[str] = []
            while True:
                points, offset = self.qdrant.scroll(
                    collection_name=collection,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                )
                if not points:
                    break
                for point in points:
                    text = (point.payload or {}).get("text", "")
                    lowered = text.lower()
                    if any(kw in lowered for kw in _RESTAURANT_KEYWORDS):
                        delete_ids.append(point.id)
                if offset is None:
                    break
            if delete_ids:
                self.qdrant.delete(collection_name=collection, points_selector=delete_ids)
            removed[collection] = len(delete_ids)
        return removed

    def collection_counts(self) -> dict[str, int]:
        counts = {}
        for name in (COMPLAINT_COLLECTION, SOP_COLLECTION, "planning_memory"):
            try:
                counts[name] = self.qdrant.get_collection(name).points_count
            except Exception:
                counts[name] = 0
        return counts

    def store_complaint(self, text: str, org_id: int, metadata: dict = None) -> str:
        """Embed and store a complaint in Qdrant, scoped to the org."""
        vector = self.embedder.embed(text)
        point_id = str(uuid.uuid4())

        self.qdrant.upsert(
            collection_name=COMPLAINT_COLLECTION,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={"text": text, "org_id": org_id, **(metadata or {})}
            )]
        )
        return point_id

    def store_sop(self, text: str, org_id: int, metadata: dict = None) -> str:
        """Embed and store an SOP rule in Qdrant, scoped to the org."""
        vector = self.embedder.embed(text)
        point_id = str(uuid.uuid4())

        self.qdrant.upsert(
            collection_name=SOP_COLLECTION,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={"text": text, "org_id": org_id, **(metadata or {})}
            )]
        )
        return point_id

    def _org_filter(self, org_id: int) -> Filter:
        return Filter(must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))])

    def retrieve_similar_complaints(self, query: str, org_id: int, top_k: int = 3) -> list[dict]:
        """Find the most semantically similar past complaints for this org."""
        vector = self.embedder.embed(query)

        results = self.qdrant.query_points(
            collection_name=COMPLAINT_COLLECTION,
            query=vector,
            query_filter=self._org_filter(org_id),
            limit=top_k,
        ).points

        return [
            {
                "text": r.payload.get("text", ""),
                "score": round(r.score, 3),
                "metadata": {k: v for k, v in r.payload.items() if k not in ("text", "org_id")}
            }
            for r in results
        ]

    def retrieve_relevant_sops(self, query: str, org_id: int, top_k: int = 3) -> list[dict]:
        """Find the most relevant SOP rules for this org."""
        vector = self.embedder.embed(query)

        results = self.qdrant.query_points(
            collection_name=SOP_COLLECTION,
            query=vector,
            query_filter=self._org_filter(org_id),
            limit=top_k,
        ).points

        return [
            {
                "text": r.payload.get("text", ""),
                "score": round(r.score, 3),
                "metadata": {k: v for k, v in r.payload.items() if k not in ("text", "org_id")}
            }
            for r in results
        ]
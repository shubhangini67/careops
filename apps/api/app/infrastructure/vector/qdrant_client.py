from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import os

# Qdrant connection setup
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# Matches the default output of text-embedding-004
EMBEDDING_DIM = 3072

def get_qdrant_client() -> QdrantClient:
    """Returns a connected Qdrant client."""
    return QdrantClient(url=QDRANT_URL)

def ensure_collection(client: QdrantClient, collection_name: str) -> None:
    """Create collection if it doesn't exist with correct dimensions."""
    existing = [c.name for c in client.get_collections().collections]
    
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE
            )
        )
        print(f"  [OK] Created Qdrant collection: {collection_name}")
    else:
        print(f"  [INFO] Collection already exists: {collection_name}")
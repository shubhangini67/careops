import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'apps', 'api')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'apps', 'api', '.env'))

from app.infrastructure.vector.qdrant_client import get_qdrant_client
from app.infrastructure.vector.embedding_service import EmbeddingService
from app.infrastructure.vector.memory_service import MemoryService

qdrant   = get_qdrant_client()
embedder = EmbeddingService()
memory   = MemoryService(qdrant, embedder)

print("=== Similar complaints to: pizza took too long ===")
results = memory.retrieve_similar_complaints("pizza took too long", top_k=3)
for r in results:
    print(f"  Score {r['score']}: {r['text']}")

print()
print("=== Relevant SOPs for: Friday peak staffing ===")
results = memory.retrieve_relevant_sops("Friday peak staffing", top_k=3)
for r in results:
    print(f"  Score {r['score']}: {r['text']}")
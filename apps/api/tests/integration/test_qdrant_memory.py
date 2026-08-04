import pytest
import sys
import os

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.infrastructure.vector.qdrant_client import get_qdrant_client
from app.infrastructure.vector.embedding_service import EmbeddingService
from app.infrastructure.vector.memory_service import MemoryService


@pytest.fixture
def memory():
    qdrant   = get_qdrant_client()
    embedder = EmbeddingService()
    return MemoryService(qdrant, embedder)


def test_retrieve_similar_complaints(memory):
    """Test semantic complaint retrieval."""
    results = memory.retrieve_similar_complaints("pizza took too long", top_k=3)
    print(f"\nComplaints: {results}")

    assert len(results) == 3
    assert all("text" in r for r in results)
    assert all("score" in r for r in results)
    assert results[0]["score"] > 0.5


def test_retrieve_relevant_sops(memory):
    """Test semantic SOP retrieval."""
    results = memory.retrieve_relevant_sops("Friday peak staffing", top_k=3)
    print(f"\nSOPs: {results}")

    assert len(results) == 3
    assert all("text" in r for r in results)
    assert results[0]["score"] > 0.5


def test_store_and_retrieve_complaint(memory):
    """Test storing a new complaint and retrieving it."""
    test_text = "The Nutella Pizza was burnt and completely inedible."

    point_id = memory.store_complaint(
        text=test_text,
        metadata={"feedback_id": 9999, "sentiment": "negative"}
    )

    assert point_id is not None

    results = memory.retrieve_similar_complaints("burnt pizza bad quality", top_k=3)
    texts = [r["text"] for r in results]
    print(f"\nRetrieved: {texts}")

    assert any("Nutella Pizza" in t or "burnt" in t for t in texts)
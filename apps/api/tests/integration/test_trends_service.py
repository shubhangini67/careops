"""Live integration test for TrendsService (P6-A22).

No mocking -- hits the real curated RSS feeds and the real configured LLM
provider, per this task's acceptance criteria ("RSS fetch+parse works
against a known feed in a live test; LLM produces a coherent digest from
real feed content"). Requires network access and a configured LLM API key.
"""

import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.infrastructure.external.trends_service import TrendsService


@pytest.mark.asyncio
async def test_live_digest_from_real_feeds():
    result = await TrendsService().get_digest()

    print(f"\nTrends digest: {result}")

    assert result is not None
    assert isinstance(result["digest"], str)
    assert len(result["digest"]) > 0
    assert result["headline_count"] > 0
    assert result["sources_used"] >= 1

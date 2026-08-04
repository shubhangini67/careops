"""Unit tests for TrendsService (P6-A22).

All RSS/HTTP and LLM calls are mocked -- no live network needed. Cache is
monkeypatched directly on the instance (same pattern as the Swiggy enricher
tests) rather than mocking Redis, since the fail-open cache wrapper is
already covered generically elsewhere.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.trends_service import _FEEDS, TrendsService

_SAMPLE_RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<title>Sample Feed</title>
<item>
<title>Restaurant delivery costs rise as fuel prices climb</title>
<pubDate>Sat, 11 Jul 2026 08:00:00 +0530</pubDate>
</item>
<item>
<title>FSSAI tightens hygiene norms for cloud kitchens</title>
<pubDate>Fri, 10 Jul 2026 08:00:00 +0530</pubDate>
</item>
</channel></rss>"""


def _mock_http_get(*, raise_error: bool = False, content: bytes = _SAMPLE_RSS):
    mock_response = MagicMock()
    if raise_error:
        mock_response.raise_for_status.side_effect = Exception("HTTP error")
    else:
        mock_response.raise_for_status.return_value = None
        mock_response.content = content

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _service_with_no_cache() -> TrendsService:
    service = TrendsService()
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_all_feeds_unreachable_returns_none():
    service = _service_with_no_cache()
    with patch(
        "app.infrastructure.external.trends_service.httpx.AsyncClient",
        return_value=_mock_http_get(raise_error=True),
    ):
        result = await service.get_digest()

    assert result is None


@pytest.mark.asyncio
async def test_llm_failure_returns_none_not_raise():
    service = _service_with_no_cache()
    with patch(
        "app.infrastructure.external.trends_service.httpx.AsyncClient",
        return_value=_mock_http_get(),
    ), patch(
        "app.infrastructure.llm.factory.create_llm_provider",
        side_effect=Exception("LLM unavailable"),
    ):
        result = await service.get_digest()

    assert result is None


@pytest.mark.asyncio
async def test_success_builds_digest_from_headlines():
    service = _service_with_no_cache()
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="- Delivery costs are rising with fuel prices\n- FSSAI tightening cloud kitchen hygiene rules")

    with patch(
        "app.infrastructure.external.trends_service.httpx.AsyncClient",
        return_value=_mock_http_get(),
    ), patch(
        "app.infrastructure.llm.factory.create_llm_provider",
        return_value=mock_llm,
    ):
        result = await service.get_digest()

    assert result is not None
    assert "Delivery costs" in result["digest"]
    assert result["headline_count"] > 0
    assert result["sources_used"] >= 1
    assert result["fetched_at"] is not None
    service._cache_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_partial_feed_failure_still_produces_digest():
    """One feed raising an error must not block headlines from the others."""
    service = _service_with_no_cache()
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="- Some trend")

    call_count = {"n": 0}

    class _FlakyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("this feed is down")
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.content = _SAMPLE_RSS
            return resp

    with patch(
        "app.infrastructure.external.trends_service.httpx.AsyncClient",
        side_effect=lambda **kwargs: _FlakyClient(),
    ), patch(
        "app.infrastructure.llm.factory.create_llm_provider",
        return_value=mock_llm,
    ):
        result = await service.get_digest()

    assert result is not None
    assert result["headline_count"] > 0


def _rss_with_items(count: int, start_date: str) -> bytes:
    """Builds a minimal valid RSS feed with `count` items, each one day older
    than the last starting from `start_date` (RFC822 format)."""
    from email.utils import format_datetime, parsedate_to_datetime

    base = parsedate_to_datetime(start_date)
    items = "".join(
        f"<item><title>Headline {i}</title>"
        f"<pubDate>{format_datetime(base - __import__('datetime').timedelta(days=i))}</pubDate></item>"
        for i in range(count)
    )
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>".encode()


@pytest.mark.asyncio
async def test_high_frequency_feed_does_not_crowd_out_low_frequency_feed():
    """A per-feed cap must guarantee every feed some representation in the
    final headline pool -- a flat "pool everything, take the global top N by
    recency" let a high-frequency feed crowd a low-frequency one out entirely,
    confirmed live with the two feeds added 2026-07-31 (BusinessLine's high
    posting frequency left restaurantindia.in's feeds with 0-1 headlines out
    of the previous flat top-20)."""
    service = _service_with_no_cache()

    # First feed in _FEEDS publishes 20 items today; the last feed publishes
    # only 2 items, both slightly older -- under pure global recency sort,
    # the high-frequency feed alone would fill the entire top-20 cap.
    feed_content = {
        _FEEDS[0]: _rss_with_items(20, "Fri, 31 Jul 2026 12:00:00 +0000"),
        _FEEDS[-1]: _rss_with_items(2, "Wed, 29 Jul 2026 12:00:00 +0000"),
    }
    for url in _FEEDS[1:-1]:
        feed_content[url] = _rss_with_items(0, "Fri, 31 Jul 2026 12:00:00 +0000")

    class _MultiFeedClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.content = feed_content[url]
            return resp

    with patch(
        "app.infrastructure.external.trends_service.httpx.AsyncClient",
        side_effect=lambda **kwargs: _MultiFeedClient(),
    ):
        headlines = await service._fetch_headlines()

    sources = {h["source"] for h in headlines}
    assert _FEEDS[-1] in sources, "low-frequency feed must still be represented despite being older"


@pytest.mark.asyncio
async def test_cache_hit_skips_fetch_entirely():
    service = TrendsService()
    cached = {
        "digest": "- cached trend",
        "headline_count": 2,
        "sources_used": 1,
        "prompt_text": "## Industry Trends\n- cached trend",
        "fetched_at": "2026-07-11",
    }
    service._cache_get = AsyncMock(return_value=cached)

    with patch("app.infrastructure.external.trends_service.httpx.AsyncClient") as mock_client_cls:
        result = await service.get_digest()

    mock_client_cls.assert_not_called()
    assert result == cached

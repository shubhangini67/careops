"""Unit tests for ComplianceAlertsService (P6-A23).

All FSSAI HTTP calls are mocked -- no live network needed. Cache is
monkeypatched directly on the instance (same pattern as trends_service's
tests) rather than mocking Redis, since the fail-open cache wrapper is
already covered generically elsewhere.

FSSAI rebuilt notifications.php as a client-side-rendered SPA (2026-07-31):
the notice list is no longer in the raw page HTML at all, it's a static JSON
array embedded inside the SPA's fingerprinted JS bundle. So the fetch flow is
now two calls: the page (to find the current bundle URL) then the bundle
itself (to extract the embedded array), plus one PDF fetch per notice for a
real text excerpt (not just the title). `_fetch_excerpt` is monkeypatched
directly for the notice-parsing tests (same boundary-mocking convention as
`_cache_get`/`_cache_set`) since it does its own real PDF download/parse and
is covered by its own dedicated tests below.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.compliance_alerts_service import ComplianceAlertsService

_SAMPLE_PAGE_HTML = """
<html><head>
<script type="module" crossorigin src="/assets/index-DYrNOKvM.js"></script>
</head><body><div id="root"></div></body></html>
"""

_PAGE_WITH_NO_BUNDLE_SCRIPT = """
<html><head></head><body><h1>New site design</h1></body></html>
"""

_SAMPLE_BUNDLE_JS = """var x=1;[{"category":"Gazette","date":"30-06-2026","title":"Gazette Notification regarding Vegan Foods labelling","href":"/docs/whatsnew/gazette/vegan_final.pdf","kind":"pdf"},{"category":"Press Note","date":"29-06-2026","title":"Unrelated press note","href":"/docs/press/x.pdf","kind":"pdf"},{"category":"Gazette","date":"24-06-2026","title":"Gazette Notification on Contaminants and Toxins","href":"/docs/whatsnew/gazette/contaminants.pdf","kind":"pdf"}];console.log("done");"""

_BUNDLE_WITH_NO_GAZETTE = """var x=1;[{"category":"Press Note","date":"29-06-2026","title":"Unrelated press note","href":"/docs/press/x.pdf","kind":"pdf"}];"""

_BUNDLE_WITH_NO_ARRAY = """var x=1;console.log("no embedded dataset here");"""


def _service_with_no_cache(excerpt: str = "") -> ComplianceAlertsService:
    service = ComplianceAlertsService()
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()
    service._fetch_excerpt = AsyncMock(return_value=excerpt)
    return service


def _mock_client_sequence(*texts: str, raise_on_call: int | None = None):
    """Returns responses in order for successive client.get() calls (page, bundle)."""
    call_count = {"n": 0}

    class _SequencedClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, timeout=None):
            call_count["n"] += 1
            if raise_on_call is not None and call_count["n"] == raise_on_call:
                raise Exception("HTTP error")
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.text = texts[call_count["n"] - 1]
            return resp

    return _SequencedClient()


@pytest.mark.asyncio
async def test_parses_real_notice_structure():
    service = _service_with_no_cache(excerpt="Real extracted PDF text about vegan food labelling requirements.")
    with patch(
        "app.infrastructure.external.compliance_alerts_service.httpx.AsyncClient",
        side_effect=lambda **kwargs: _mock_client_sequence(_SAMPLE_PAGE_HTML, _SAMPLE_BUNDLE_JS),
    ):
        result = await service.get_alerts()

    assert result is not None
    assert result["notice_count"] == 2
    assert result["notices"][0]["title"] == "Gazette Notification regarding Vegan Foods labelling"
    assert result["notices"][0]["uploaded_on"] == "30-06-2026"
    assert result["notices"][0]["url"].endswith("vegan_final.pdf")
    assert result["notices"][0]["excerpt"] == "Real extracted PDF text about vegan food labelling requirements."
    assert "Real extracted PDF text" in result["prompt_text"]
    service._cache_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_gazette_notices_returns_none():
    service = _service_with_no_cache()
    with patch(
        "app.infrastructure.external.compliance_alerts_service.httpx.AsyncClient",
        side_effect=lambda **kwargs: _mock_client_sequence(_SAMPLE_PAGE_HTML, _BUNDLE_WITH_NO_GAZETTE),
    ):
        result = await service.get_alerts()

    assert result is None


@pytest.mark.asyncio
async def test_http_error_returns_none_not_raise():
    service = _service_with_no_cache()
    with patch(
        "app.infrastructure.external.compliance_alerts_service.httpx.AsyncClient",
        side_effect=lambda **kwargs: _mock_client_sequence(_SAMPLE_PAGE_HTML, _SAMPLE_BUNDLE_JS, raise_on_call=1),
    ):
        result = await service.get_alerts()

    assert result is None


@pytest.mark.asyncio
async def test_page_redesign_with_no_bundle_script_returns_none():
    """Simulates a further FSSAI redesign -- no <script type=module> at all."""
    service = _service_with_no_cache()
    with patch(
        "app.infrastructure.external.compliance_alerts_service.httpx.AsyncClient",
        side_effect=lambda **kwargs: _mock_client_sequence(_PAGE_WITH_NO_BUNDLE_SCRIPT),
    ):
        result = await service.get_alerts()

    assert result is None


@pytest.mark.asyncio
async def test_bundle_with_no_embedded_array_returns_none_not_crash():
    """Simulates the SPA changing how it ships data -- no embedded JSON array marker."""
    service = _service_with_no_cache()
    with patch(
        "app.infrastructure.external.compliance_alerts_service.httpx.AsyncClient",
        side_effect=lambda **kwargs: _mock_client_sequence(_SAMPLE_PAGE_HTML, _BUNDLE_WITH_NO_ARRAY),
    ):
        result = await service.get_alerts()

    assert result is None


@pytest.mark.asyncio
async def test_exception_returns_none_never_raises():
    service = _service_with_no_cache()
    with patch(
        "app.infrastructure.external.compliance_alerts_service.httpx.AsyncClient",
        side_effect=RuntimeError("network down"),
    ):
        result = await service.get_alerts()

    assert result is None


@pytest.mark.asyncio
async def test_cache_hit_skips_fetch_entirely():
    service = ComplianceAlertsService()
    cached = {
        "notices": [{"title": "Cached notice", "uploaded_on": "01-01-2026", "url": "https://fssai.gov.in/x.pdf", "excerpt": "cached excerpt"}],
        "notice_count": 1,
        "prompt_text": "## Regulatory Alerts (FSSAI)\n- Cached notice (uploaded 01-01-2026)\n  cached excerpt",
        "fetched_at": "2026-07-31",
    }
    service._cache_get = AsyncMock(return_value=cached)

    with patch("app.infrastructure.external.compliance_alerts_service.httpx.AsyncClient") as mock_client_cls:
        result = await service.get_alerts()

    mock_client_cls.assert_not_called()
    assert result == cached


# ── _fetch_excerpt (real PDF download + text extraction) ─────────────────────

def _mock_pdf_client(content: bytes = b"%PDF-fake", raise_error: bool = False):
    mock_response = MagicMock()
    if raise_error:
        mock_response.raise_for_status.side_effect = Exception("PDF fetch failed")
    else:
        mock_response.raise_for_status.return_value = None
        mock_response.content = content

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


def _mock_pdf_reader(page_texts: list[str]):
    pages = []
    for t in page_texts:
        page = MagicMock()
        page.extract_text.return_value = t
        pages.append(page)
    reader = MagicMock()
    reader.pages = pages
    return reader


@pytest.mark.asyncio
async def test_fetch_excerpt_extracts_and_truncates_text():
    service = ComplianceAlertsService()
    client = _mock_pdf_client()
    with patch(
        "app.infrastructure.external.compliance_alerts_service.pypdf.PdfReader",
        return_value=_mock_pdf_reader(["A" * 2000]),
    ):
        excerpt = await service._fetch_excerpt(client, "https://fssai.gov.in/x.pdf")

    assert len(excerpt) == 1200  # _EXCERPT_MAX_CHARS
    assert excerpt == "A" * 1200


@pytest.mark.asyncio
async def test_fetch_excerpt_collapses_whitespace():
    service = ComplianceAlertsService()
    client = _mock_pdf_client()
    with patch(
        "app.infrastructure.external.compliance_alerts_service.pypdf.PdfReader",
        return_value=_mock_pdf_reader(["Line one\n\n\nLine   two\t\tLine three"]),
    ):
        excerpt = await service._fetch_excerpt(client, "https://fssai.gov.in/x.pdf")

    assert excerpt == "Line one Line two Line three"


@pytest.mark.asyncio
async def test_fetch_excerpt_reads_all_pages_not_just_the_first():
    """These gazettes run 1-3 pages, and a page-1 Hindi masthead can already
    exceed the excerpt cap by itself -- if extraction stopped early, page 2's
    (often the only English-language) content would never be reached."""
    service = ComplianceAlertsService()
    client = _mock_pdf_client()
    reader = _mock_pdf_reader(["A" * 1300, "B" * 1300])
    with patch(
        "app.infrastructure.external.compliance_alerts_service.pypdf.PdfReader",
        return_value=reader,
    ):
        await service._fetch_excerpt(client, "https://fssai.gov.in/x.pdf")

    reader.pages[0].extract_text.assert_called_once()
    reader.pages[1].extract_text.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_excerpt_prefers_longest_english_run_over_document_start():
    """Real FSSAI gazettes are laid out Hindi-notification-first, English-
    notification-second -- a naive "first N chars" grab would return almost
    entirely Hindi masthead text and miss the actual English regulation body
    that only appears later (often on a subsequent page)."""
    service = ComplianceAlertsService()
    client = _mock_pdf_client()
    hindi_header_with_short_ascii = "हिन्दी हिन्दी No. 452] सी.जी. " * 3  # short ascii fragments only
    english_body = (
        "This is the real English regulation body text that should be selected "
        "because it is the longest ASCII run available in the document and "
        "clearly exceeds the minimum threshold length required for selection."
    )
    reader = _mock_pdf_reader([hindi_header_with_short_ascii, english_body])
    with patch(
        "app.infrastructure.external.compliance_alerts_service.pypdf.PdfReader",
        return_value=reader,
    ):
        excerpt = await service._fetch_excerpt(client, "https://fssai.gov.in/x.pdf")

    assert excerpt.endswith(english_body)
    assert "हिन्दी" not in excerpt


@pytest.mark.asyncio
async def test_fetch_excerpt_falls_back_to_document_start_when_hindi_only():
    """A notice with no substantial English section at all (confirmed to happen
    live) still yields a real excerpt -- just the Hindi text, not an empty string."""
    service = ComplianceAlertsService()
    client = _mock_pdf_client()
    hindi_only = "हिन्दी सूचना पाठ " * 20
    reader = _mock_pdf_reader([hindi_only])
    with patch(
        "app.infrastructure.external.compliance_alerts_service.pypdf.PdfReader",
        return_value=reader,
    ):
        excerpt = await service._fetch_excerpt(client, "https://fssai.gov.in/x.pdf")

    assert excerpt != ""
    assert "हिन्दी" in excerpt


@pytest.mark.asyncio
async def test_fetch_excerpt_http_error_returns_empty_string_not_raise():
    service = ComplianceAlertsService()
    client = _mock_pdf_client(raise_error=True)
    excerpt = await service._fetch_excerpt(client, "https://fssai.gov.in/x.pdf")

    assert excerpt == ""


@pytest.mark.asyncio
async def test_fetch_excerpt_malformed_pdf_returns_empty_string_not_raise():
    service = ComplianceAlertsService()
    client = _mock_pdf_client(content=b"not a real pdf")
    with patch(
        "app.infrastructure.external.compliance_alerts_service.pypdf.PdfReader",
        side_effect=Exception("malformed PDF"),
    ):
        excerpt = await service._fetch_excerpt(client, "https://fssai.gov.in/x.pdf")

    assert excerpt == ""


@pytest.mark.asyncio
async def test_fetch_excerpt_empty_url_returns_empty_string():
    service = ComplianceAlertsService()
    excerpt = await service._fetch_excerpt(MagicMock(), "")

    assert excerpt == ""

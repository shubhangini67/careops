"""ComplianceAlertsService — P6-A23.

Reads FSSAI's public "what's new" notice list (Gazette Notification category
-- finalized regulations, not drafts/comments-under-review) for recent
regulatory notices relevant to Indian restaurants. Public government
regulatory data -- no ToS tension of any kind, the cleanest source of the
four live-intelligence signals on that front.

Confirmed live 2026-07-31: FSSAI rebuilt notifications.php as a client-side-
rendered SPA (a bare `<div id="root">` + one fingerprinted JS module bundle)
-- the plain-HTML scrape this service originally used (P6-A23) stopped
returning any notices once that redesign shipped, since the notice list no
longer exists in the raw HTTP response at all. Investigating the bundle
found something better than a same-shape HTML fix: the SPA ships its entire
notice dataset (~3700 entries, every category, going back years) as one
static embedded JSON array baked directly into the JS bundle, not fetched
via a separate API call. Parsing that array is actually more robust than the
old HTML scrape (structured fields, no brittle CSS selectors) and still
needs no headless browser -- just one extra fetch for the bundle itself.

Explicit fail-open contract given this is still page-structure scraping one
level removed -- any further FSSAI redesign (a different bundling approach,
a real backend API replacing the embedded array) breaks this parser too --
must degrade to None cleanly, never raise, never block the other three
live-intelligence signals (weather, industry trends, anonymised Swiggy area
signals).

Each notice also carries a short text excerpt from its actual Gazette PDF,
not just its title -- confirmed live that these PDFs (600KB-1.3MB each, but
that's embedded letterhead/font assets, not page count) are only 1-3 pages
with a real embedded text layer (bilingual Hindi/English), not scanned
images, so pypdf extraction works with no OCR needed. Deliberately not a RAG
pipeline: no chunking, no embeddings, no vector store -- just the already-
capped top 5 notices' PDFs fetched once per cache window, full text
extracted (still cheap at 1-3 pages) and the excerpt taken from the longest
run of Latin-script text, not just the first N characters -- confirmed live
these gazettes are laid out Hindi-notification-first, English-notification-
second (when an English version exists at all; some are Hindi-only), so a
naive "first N chars" grab returns almost entirely Hindi masthead/header
text and never reaches the substantive English regulation body on a later
page. Falls back to the start of the extracted text when no substantial
Latin-script run is found (a Hindi-only notice). One bad/unreachable PDF
degrades to an empty excerpt for that notice only, never blocks the others
or the overall result.
"""

import asyncio
import io
import json
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
import pypdf
import redis.asyncio as aioredis
import structlog
from bs4 import BeautifulSoup

from app.core.settings import get_settings

log = structlog.get_logger()

_TIMEOUT = 10.0
_PDF_TIMEOUT = 20.0  # gazette PDFs run up to ~1.3MB, slower than the page/bundle fetches
_BASE_URL = "https://fssai.gov.in"
_PAGE_URL = f"{_BASE_URL}/notifications.php"
_GAZETTE_CATEGORY = "Gazette"  # finalized regulations, not drafts/comments-under-review
_MAX_NOTICES = 5
_ARRAY_MARKER = '[{"category":'  # start of the SPA's embedded notice dataset
_EXCERPT_MAX_CHARS = 1200  # per notice -- bounds total prompt size regardless of PDF length
_MIN_ENGLISH_RUN_CHARS = 150  # below this, a Latin-script run is just a header/date fragment,
                              # not the actual English notification body
_ENGLISH_RUN_RE = re.compile(r"[\x00-\x7F]{%d,}" % _MIN_ENGLISH_RUN_CHARS)

_CACHE_TTL = 3600  # 1 hour -- regulatory notices move far slower than Swiggy signals,
                   # and the bundle + PDF fetches aren't free
_CACHE_KEY = "compliance_alerts_service:notices"


class ComplianceAlertsService:
    """Live FSSAI regulatory notice digest. get_alerts() is the only public method."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def get_alerts(self, force_refresh: bool = False) -> Optional[dict]:
        try:
            return await self._get_alerts(force_refresh=force_refresh)
        except Exception as exc:
            log.warning("compliance_alerts_service_error", error=str(exc))
            return None

    async def _get_alerts(self, force_refresh: bool = False) -> Optional[dict]:
        if not force_refresh:
            cached = await self._cache_get()
            if cached is not None:
                log.info("compliance_alerts_service_cache_hit")
                return cached

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            page_resp = await client.get(_PAGE_URL, headers={"User-Agent": "Mozilla/5.0"})
            page_resp.raise_for_status()

            bundle_url = self._find_bundle_url(page_resp.text)
            if not bundle_url:
                return None

            bundle_resp = await client.get(bundle_url, headers={"User-Agent": "Mozilla/5.0"})
            bundle_resp.raise_for_status()

            notices = self._parse_notices(bundle_resp.text)
            if not notices:
                return None

            excerpts = await asyncio.gather(
                *(self._fetch_excerpt(client, n["url"]) for n in notices)
            )
            for notice, excerpt in zip(notices, excerpts):
                notice["excerpt"] = excerpt

        result = {
            "notices": notices,
            "notice_count": len(notices),
            "prompt_text": self._build_prompt(notices),
            "fetched_at": date.today().isoformat(),
        }
        await self._cache_set(result)
        return result

    def _find_bundle_url(self, page_html: str) -> Optional[str]:
        soup = BeautifulSoup(page_html, "html.parser")
        script = soup.find("script", attrs={"type": "module", "src": True})
        if not script:
            return None
        return urljoin(_BASE_URL, script["src"])

    def _parse_notices(self, bundle_js: str) -> list[dict]:
        idx = bundle_js.find(_ARRAY_MARKER)
        if idx == -1:
            return []

        try:
            entries, _ = json.JSONDecoder().raw_decode(bundle_js, idx)
        except (ValueError, json.JSONDecodeError):
            return []

        gazette = [e for e in entries if e.get("category") == _GAZETTE_CATEGORY and e.get("title") and e.get("date")]

        def _sort_key(entry: dict) -> datetime:
            try:
                return datetime.strptime(entry["date"], "%d-%m-%Y")
            except ValueError:
                return datetime.min

        gazette.sort(key=_sort_key, reverse=True)

        notices = []
        for entry in gazette[:_MAX_NOTICES]:
            href = entry.get("href") or ""
            notices.append({
                "title":       entry["title"].strip(),
                "uploaded_on": entry["date"].strip(),
                "url":         urljoin(_BASE_URL, href) if href else "",
            })
        return notices

    async def _fetch_excerpt(self, client: httpx.AsyncClient, url: str) -> str:
        """Real Gazette PDF text, truncated. Prefers the longest Latin-script
        (English) run over the raw start of the document -- these gazettes are
        laid out Hindi-first/English-second, so "first N chars" would almost
        always return masthead Hindi and miss the actual English regulation
        text. Falls back to the document start when no substantial English
        run exists (a Hindi-only notice). Never raises -- one bad PDF just
        means that notice's excerpt is empty, never blocks the others."""
        if not url:
            return ""
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=_PDF_TIMEOUT)
            resp.raise_for_status()
            reader = pypdf.PdfReader(io.BytesIO(resp.content))

            # These notices run 1-3 pages -- full extraction is cheap, and
            # partial extraction risks stopping before an English section
            # that only appears on a later page (confirmed live).
            text = " ".join((page.extract_text() or "") for page in reader.pages)
            text = re.sub(r"\s+", " ", text).strip()

            english_runs = _ENGLISH_RUN_RE.findall(text)
            excerpt = max(english_runs, key=len) if english_runs else text

            return excerpt[:_EXCERPT_MAX_CHARS].strip()
        except Exception as exc:
            log.debug("compliance_alerts_service_pdf_excerpt_error", url=url, error=str(exc))
            return ""

    def _build_prompt(self, notices: list[dict]) -> str:
        lines = ["## Regulatory Alerts (FSSAI)"]
        for n in notices:
            lines.append(f"- {n['title']} (uploaded {n['uploaded_on']})")
            if n.get("excerpt"):
                lines.append(f"  {n['excerpt']}")
        return "\n".join(lines)

    # ── Redis cache ──────────────────────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                get_settings().redis_url, encoding="utf-8", decode_responses=True,
            )
        return self._redis

    async def _cache_get(self) -> Optional[dict]:
        try:
            r = await self._get_redis()
            raw = await r.get(_CACHE_KEY)
            return json.loads(raw) if raw else None
        except Exception as exc:
            log.debug("compliance_alerts_service_cache_get_error", error=str(exc))
            return None

    async def _cache_set(self, value: dict) -> None:
        try:
            r = await self._get_redis()
            await r.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(value, default=str))
        except Exception as exc:
            log.debug("compliance_alerts_service_cache_set_error", error=str(exc))

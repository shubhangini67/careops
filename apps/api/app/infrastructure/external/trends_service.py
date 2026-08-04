"""TrendsService — P6-A22.

Fetches a curated list of Indian F&B/hospitality trade-press RSS feeds via
feedparser and summarizes recent headlines into a short "what's trending"
digest using the existing LLM provider (create_llm_provider() -- no new LLM
integration). RSS-only, deliberately: not Google Trends/pytrends, which
scrapes a Google-internal endpoint outside its public API surface -- a ToS
gray area this project has chosen to avoid given how carefully it treats
Swiggy's own terms. RSS is a syndication format meant to be fetched by
third parties, zero ToS risk.

Never raises -- returns None if every feed is unreachable (or the LLM call
fails) so callers run fine without it. Caches the digest in Redis for 1 hour
(trade news moves far slower than Swiggy pricing/occupancy, and an LLM call
isn't free) -- keyed globally, not per-org, since every operator reading
this sees the same real-world industry news.
"""

import asyncio
import calendar
import json
from datetime import date
from typing import Optional

import feedparser
import httpx
import redis.asyncio as aioredis
import structlog

from app.core.settings import get_settings

log = structlog.get_logger()

_TIMEOUT = 10.0
_CACHE_TTL = 3600  # 1 hour
_CACHE_KEY = "trends_service:digest"
_MAX_HEADLINES = 20  # capped across all feeds combined, most recent first -- headline
                     # count alone (not depth) is what lets the LLM actually find the
                     # restaurant-relevant handful instead of forcing generic ones through

# Curated Indian F&B/hospitality/agri-commodity trade press -- each confirmed
# live (2026-07-11; two more added 2026-07-31) as a real, publicly syndicated
# RSS feed. Deliberately more than one source: any single feed going away
# (redesign, moved URL) degrades the digest, not the whole signal. Generic
# retail top-stories deliberately left out -- it diluted the digest with
# non-food retail news (electronics, apparel) crowding out the genuinely
# food/restaurant-relevant headlines; same reason ET's broader "industry"/
# "companies"-style feeds and LiveMint's were rejected during the 2026-07-31
# source search (banking/telecom/EV/IT noise, not food/restaurant). The two
# added then (restaurantindia.in, aka indianretailer.com/restaurant) are
# menu-trend and restaurant-operations trade press specifically -- confirmed
# to directly address the "digest was coming back empty many days" problem
# the original two-feed set had, since restaurant-operations news is more
# consistently available day-to-day than macro agri/FMCG headlines clearing
# the strict relevance bar in _DIGEST_SYSTEM_PROMPT below.
_FEEDS: tuple[str, ...] = (
    "https://retail.economictimes.indiatimes.com/rss/food-entertainment",
    "https://www.thehindubusinessline.com/economy/agri-business/feeder/default.rss",
    "https://www.restaurantindia.in/rss/food-and-beverages",
    "https://www.restaurantindia.in/rss/operations",
)

_DIGEST_SYSTEM_PROMPT = (
    "You brief a small, independent Indian restaurant's owner on trade-press news that "
    "actually changes something they'd do THIS WEEK, in THEIR restaurant. You are given "
    "headlines PLUS their article summaries -- use the summary detail, don't just "
    "restate the headline.\n\n"
    "Only these count as relevant:\n"
    "- Domestic price/supply moves for ingredients a typical Indian restaurant actually "
    "buys and cooks with (vegetables, dairy, meat/poultry, grains/pulses, cooking oil, "
    "spices, sugar) -- e.g. \"urad prices up\" or \"egg prices at a high\" are exactly "
    "the kind of thing to include.\n"
    "- FSSAI or other food-safety/licensing rules that apply to running a restaurant in "
    "India.\n"
    "- Delivery-platform (Swiggy/Zomato) policy, commission, or fee changes that affect "
    "a listed restaurant.\n"
    "- Genuine local consumer-demand shifts in what Indian diners are ordering.\n"
    "- Real, cited menu/cuisine/ingredient-demand trends: a dish category, cuisine "
    "style, or ingredient genuinely gaining or losing traction with Indian diners, "
    "backed by an actual number, survey, or named data source (e.g. \"RTD tea sales up "
    "109%\", \"millets appearing on more café menus this quarter\"). This is about what "
    "people are measurably ordering more or less of, not a restaurant-industry advice "
    "or opinion piece that merely mentions a cuisine or dish in passing.\n\n"
    "These do NOT count, no matter how the headline is worded -- do not force a "
    "restaurant angle onto them:\n"
    "- International trade/export/import compliance disputes (an EU or US customs "
    "ruling on a cargo shipment is not something a neighborhood restaurant deals with).\n"
    "- Big-conglomerate retail/e-commerce expansion or corporate strategy news (a "
    "company opening thousands of grocery/retail stores is not restaurant-relevant just "
    "because it also sells food) -- unless it is specifically about a food-delivery "
    "platform's terms for restaurants.\n"
    "- Funding rounds, M&A, IPOs, or executive/leadership news.\n"
    "- Anything whose only real subject is a large chain, exporter, or B2B supplier "
    "transaction the owner has no part in.\n"
    "- Lifestyle/opinion features and generic restaurant-advice content dressed up as a "
    "\"trend\" -- e.g. \"why location strategy matters,\" \"how hotels are redefining "
    "hospitality through experience,\" generic profitability or cash-flow advice. These "
    "have no cited data point behind them and are not a real market signal, even when "
    "the headline sounds trend-adjacent or names a cuisine/dish.\n\n"
    "SEPARATELY, also include genuinely interesting real food/DINING-industry "
    "happenings even when there's no THIS-WEEK operational implication -- a notable "
    "new restaurant/bar/cafe opening, a real cultural or culinary trend piece, a "
    "specific new dish/menu-item launch, or another concrete, cited development "
    "specifically about restaurants/dining/menus the owner would just find interesting. "
    "The SAME exclusions above still apply here, strictly, even though the bar for "
    "\"relevant\" is otherwise looser -- in particular, still exclude: any named chain's "
    "store-count or expansion news (e.g. \"opens its Nth store,\" \"expanding to N "
    "cities\") even if it also mentions a product; any brand-ambassador, ad-campaign, or "
    "marketing-launch news for a packaged-goods/CPG product (mints, snacks, beverages "
    "sold retail) that isn't itself a restaurant/dining development; and funding/M&A/"
    "IPO/executive news, full stop. When genuinely unsure whether something is dining-"
    "specific enough to qualify, leave it out rather than including it. "
    "Prefix every line in this category with \"(FYI) \" so it reads clearly as "
    "interesting-not-actionable, never disguised as something requiring action.\n\n"
    "CRITICAL OUTPUT FORMAT: output ONLY the bullet lines themselves (or the exact "
    "fallback sentence) -- never an introductory or explanatory sentence before the "
    "list (e.g. never write something like \"No specific ingredient moves were found, "
    "however here are some other trends:\"). If there are zero actionable items but "
    "some (FYI) items, start directly with the first (FYI) line -- do not explain the "
    "absence of actionable items first. Write one line per relevant headline (plain "
    "text, no markdown headers). For the actionable category, state the specific fact "
    "(a number, a policy, a named ingredient, or a cited demand statistic) and a "
    "concrete operational implication -- e.g. add/feature/promote a specific dish or "
    "ingredient, adjust pricing, or a compliance action -- not generic advice like "
    "'monitor the situation'. For the (FYI) category, just state the real fact plainly, "
    "no forced operational spin. List actionable lines first, then (FYI) lines. Do not "
    "pad to reach a target count: if only 1-2 headlines genuinely qualify for either "
    "category, write only those; if absolutely nothing qualifies for either category, "
    "write exactly \"No restaurant-relevant trends this week.\"\n\n"
    "Tone: stay neutral and factual about any named platform or company (Swiggy, "
    "Zomato, etc.) -- never phrase a bullet as scrutinizing, doubting, or casting a "
    "platform's compliance/practices in a negative light. If a headline involves one, "
    "state what happened plainly and pivot straight to what the restaurant owner should "
    "do for their OWN business, without implying distrust of the platform."
)


class TrendsService:
    """Live industry-trends digest from curated RSS feeds. get_digest() is the only public method."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def get_digest(self, force_refresh: bool = False) -> Optional[dict]:
        try:
            return await self._get_digest(force_refresh=force_refresh)
        except Exception as exc:
            log.warning("trends_service_error", error=str(exc))
            return None

    async def _get_digest(self, force_refresh: bool = False) -> Optional[dict]:
        if not force_refresh:
            cached = await self._cache_get()
            if cached is not None:
                log.info("trends_service_cache_hit")
                return cached

        headlines = await self._fetch_headlines()
        if not headlines:
            return None

        digest = await self._summarize(headlines)
        if not digest:
            return None

        result = {
            "digest": digest,
            "headline_count": len(headlines),
            "sources_used": len({h["source"] for h in headlines}),
            "prompt_text": f"## Industry Trends\n{digest}",
            "fetched_at": date.today().isoformat(),
        }
        await self._cache_set(result)
        log.info("trends_service_done", headlines=len(headlines), sources=result["sources_used"])
        return result

    async def _fetch_headlines(self) -> list[dict]:
        """Fetch all feeds concurrently; one feed failing never blocks the others."""

        async def _fetch_one(url: str) -> list[dict]:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
                entries = []
                for entry in parsed.entries[:_MAX_HEADLINES]:
                    title = str(entry.get("title") or "").strip()
                    if not title:
                        continue
                    published_struct = entry.get("published_parsed")
                    entries.append({
                        "title": title,
                        "summary": str(entry.get("summary") or "").strip(),
                        "published_epoch": calendar.timegm(published_struct) if published_struct else 0,
                        "source": url,
                    })
                return entries
            except Exception as exc:
                log.warning("trends_service_feed_error", url=url, error=str(exc))
                return []

        results = await asyncio.gather(*(_fetch_one(url) for url in _FEEDS))

        # Cap each feed's contribution before combining, not after -- a flat
        # "pool everything then take the global top N by recency" let a
        # high-frequency-publishing feed (BusinessLine posts far more often
        # than the restaurant-trade-press feeds) crowd out lower-frequency
        # feeds entirely, confirmed live: the two feeds added 2026-07-31
        # contributed zero and one headline respectively to a flat top-20,
        # despite being the most directly restaurant-relevant sources. An
        # even per-feed share guarantees every feed actually reaches the LLM.
        per_feed_cap = max(1, _MAX_HEADLINES // len(_FEEDS))
        all_headlines = []
        for feed_entries in results:
            feed_entries.sort(key=lambda h: h["published_epoch"], reverse=True)
            all_headlines.extend(feed_entries[:per_feed_cap])

        # Most recent first overall; entries with no parseable date sort last.
        all_headlines.sort(key=lambda h: h["published_epoch"], reverse=True)
        return all_headlines[:_MAX_HEADLINES]

    async def _summarize(self, headlines: list[dict]) -> Optional[str]:
        from app.infrastructure.llm.factory import create_llm_provider

        headline_lines = "\n\n".join(
            f"HEADLINE: {h['title']}\nSUMMARY: {h['summary']}" if h["summary"] else f"HEADLINE: {h['title']}"
            for h in headlines
        )
        prompt = f"Recent headlines with article summaries:\n\n{headline_lines}"

        try:
            llm = create_llm_provider(get_settings())
            # Low temperature: this is a relevance CLASSIFICATION (does this
            # headline qualify or not), not narrative generation -- default
            # sampling temperature made this call flip between "nothing
            # qualifies" and "these two qualify" on the exact same headline
            # set across separate calls (confirmed live, 2026-07-31), which
            # then got frozen into the hourly cache as whichever answer
            # happened to land first.
            digest = await llm.complete(prompt, system_prompt=_DIGEST_SYSTEM_PROMPT, temperature=0.1)
        except Exception as exc:
            log.warning("trends_service_llm_error", error=str(exc))
            return None

        return digest.strip() if digest else None

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
            log.debug("trends_service_cache_get_error", error=str(exc))
            return None

    async def _cache_set(self, value: dict) -> None:
        try:
            r = await self._get_redis()
            await r.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(value, default=str))
        except Exception as exc:
            log.debug("trends_service_cache_set_error", error=str(exc))

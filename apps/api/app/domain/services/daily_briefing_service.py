"""BriefingService -- P6-A30 v2 Dashboard redesign.

Synthesizes a 2-3 sentence executive summary from data BusinessAnalyticsService
and InventoryService already compute (health score, net margin, inventory
shortages, recent complaints) -- no new queries, same pattern as
infrastructure/external/trends_service.py's get_digest(): an LLM turning
already-computed structured data into a short brief, cached in Redis since
it's an LLM call on a dashboard-load path and the underlying numbers don't
change meaningfully within an hour.

Never raises -- returns None on any failure (LLM unavailable, cache error)
so a missing executive summary never blocks the rest of the dashboard.
"""

import json
from datetime import date
from typing import Optional

import redis.asyncio as aioredis
import structlog
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.domain.services.business_analytics_service import BusinessAnalyticsService
from app.infrastructure.db.models import Inventory

log = structlog.get_logger()

_CACHE_TTL = 3600  # 1 hour -- health score/margin/inventory don't shift meaningfully faster than this
_CACHE_KEY_PREFIX = "careops:briefing:summary:"

_SUPPLY_DISPLAY = {
    "Burger Buns": "Surgical Gloves",
    "Paneer": "IV Saline Bags",
    "Mozzarella": "N95 Respirators",
    "Chicken Breast": "Sterile Syringes",
    "Tomatoes": "Wound Dressings",
    "Olive Oil": "Hand Sanitizer",
    "Pizza Dough": "Oxygen Cannulas",
}


def _to_supply_label(name: str) -> str:
    return _SUPPLY_DISPLAY.get(name, name)


def _hospitalize_risk_text(text: str) -> str:
    out = text
    for legacy, label in _SUPPLY_DISPLAY.items():
        out = out.replace(legacy, label)
    return (
        out.replace("below threshold", "below reorder threshold")
        .replace("reorder before next service", "reorder before next shift handoff")
        .replace("ingredient", "supply item")
    )

_SUMMARY_SYSTEM_PROMPT = (
    "You write a 2-3 sentence operations brief for a hospital operations director "
    "opening their CareOps dashboard for the day. You are given their current "
    "operational health score, net margin (cost efficiency proxy), supply shortages, "
    "and recent safety/complaint themes — all already computed, do not invent numbers "
    "not given to you.\n\n"
    "Write plain prose, no markdown, no bullet points, 2-3 sentences total. Lead with "
    "an overall read (solid/mixed/concerning), name the single most important metric, "
    "then flag the one or two things that actually need attention today (a supply "
    "shortage, a safety incident trend, bed-capacity pressure) if any exist. If nothing "
    "needs attention, say so plainly instead of inventing a concern. Use hospital "
    "operations language — supply items, departments, patient satisfaction, ED wait "
    "times — never restaurant or food terms. Specific beats generic — name the actual "
    "supply item or incident category, not \"some items\" or \"certain areas\"."
)


class BriefingService:
    def __init__(self, db: Session):
        self.db = db
        self._redis: Optional[aioredis.Redis] = None

    async def get_summary(self, org_id: int | None) -> Optional[dict]:
        try:
            return await self._get_summary(org_id)
        except Exception as exc:
            log.warning("briefing_service_error", error=str(exc))
            return None

    async def _get_summary(self, org_id: int | None) -> Optional[dict]:
        cache_key = f"{_CACHE_KEY_PREFIX}{org_id or 'default'}:{date.today().isoformat()}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            log.info("briefing_service_cache_hit", org_id=org_id)
            return cached

        analytics = BusinessAnalyticsService(self.db)
        # Real net margin, same reconciliation business.py's own route computes
        # -- previously hardcoded to None here, which silently produced a
        # fake near-zero health_score (~15) while the rest of the dashboard
        # showed the real one (~85, computed with the real margin).
        net_margin_pct = analytics.get_net_margin_pct(days=30)
        positive_sentiment_pct = analytics.get_positive_sentiment_pct(days=28)
        complaints = analytics.get_complaints_by_category(days=28)
        risks = analytics.get_upcoming_risks()
        health_score = analytics.compute_health_score(net_margin_pct, positive_sentiment_pct)

        inventory_count = self.db.query(Inventory).count()
        critical_shortages = [
            _hospitalize_risk_text(r["text"]) for r in risks if r["kind"] == "inventory"
        ]
        complaint_categories = [
            c["category"]
            .replace("Wait Time", "ED Wait Time")
            .replace("Food Quality", "Care Quality")
            for c in complaints[:2]
        ]

        facts = {
            "operational_health_score": health_score,
            "net_margin_pct": net_margin_pct,
            "positive_sentiment_pct": positive_sentiment_pct,
            "top_safety_incident_categories": complaint_categories,
            "critical_supply_shortages": critical_shortages,
            "total_supply_items_tracked": inventory_count,
        }
        summary_text = await self._summarize(facts)
        if not summary_text:
            return None

        result = {"summary": summary_text, "generated_at": date.today().isoformat()}
        await self._cache_set(cache_key, result)
        log.info("briefing_service_done", org_id=org_id)
        return result

    async def _summarize(self, facts: dict) -> Optional[str]:
        from app.infrastructure.llm.factory import create_llm_provider

        prompt = f"Today's computed facts:\n{json.dumps(facts, indent=2)}"
        try:
            llm = create_llm_provider(get_settings())
            summary = await llm.complete(prompt, system_prompt=_SUMMARY_SYSTEM_PROMPT)
        except Exception as exc:
            log.warning("briefing_service_llm_error", error=str(exc))
            return None
        return summary.strip() if summary else None

    # ── Redis cache ──────────────────────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                get_settings().redis_url, encoding="utf-8", decode_responses=True,
            )
        return self._redis

    async def _cache_get(self, key: str) -> Optional[dict]:
        try:
            r = await self._get_redis()
            raw = await r.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            log.debug("briefing_service_cache_get_error", error=str(exc))
            return None

    async def _cache_set(self, key: str, value: dict) -> None:
        try:
            r = await self._get_redis()
            await r.setex(key, _CACHE_TTL, json.dumps(value, default=str))
        except Exception as exc:
            log.debug("briefing_service_cache_set_error", error=str(exc))

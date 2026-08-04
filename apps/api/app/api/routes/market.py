"""market.py — live market intelligence, independent of any planning run.

GET /api/v1/market/pulse fetches current area market data (competitor
pricing, area demand, Instamart procurement) directly via the enrichers used
inside the planning pipeline, plus live weather (P6-A21, Open-Meteo) and an
industry-trends digest (P6-A22, curated RSS) -- neither is Swiggy MCP, so
both are returned regardless of Swiggy connection status, all without
requiring a plan to be run first. Each Swiggy enricher already caches its
own result in Redis for 30 minutes (keyed by org_id + date), and
TrendsService caches its digest for 1 hour, so calling this endpoint
repeatedly (e.g. every dashboard load) does not re-hit external services
each time.
"""

import asyncio
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.constants import DEFAULT_RESTAURANT_LAT, DEFAULT_RESTAURANT_LNG
from app.core.settings import get_settings
from app.domain.services.inventory_service import InventoryService
from app.domain.services.run_service import RunService
from app.infrastructure.db.models import MenuItem, Organization
from app.infrastructure.external.compliance_alerts_service import ComplianceAlertsService
from app.infrastructure.external.trends_service import TrendsService
from app.infrastructure.external.weather_service import WeatherService
from app.infrastructure.swiggy.client import SwiggyMCPClient
from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher
from app.infrastructure.swiggy.enrichers.occupancy import OccupancyEnricher
from app.infrastructure.swiggy.enrichers.procurement import ProcurementEnricher

router = APIRouter(prefix="/market", tags=["market"])


class PricingComparison(BaseModel):
    item: str
    area_avg: float
    your_price: float | None = None
    diff_pct: float | None = None   # always positive -- see `direction` for above/below
    direction: Literal["above", "below"] | None = None


class PricingImpactItem(BaseModel):
    item: str
    our_price: float
    area_avg: float
    gap_pct: float
    direction: Literal["above", "below"]
    volume_change_pct: float
    weekly_revenue_impact_inr: float


class DishPrice(BaseModel):
    """Dish name + price only -- never which restaurant serves it."""
    name: str
    price: float


class CategoryPricing(BaseModel):
    category: str
    your_avg: float
    area_avg: float
    diff_pct: float
    verdict: Literal["above", "below", "in line"]
    competitor_dishes_sampled: int
    cheapest_dish: DishPrice
    priciest_dish: DishPrice


class LandscapeSummary(BaseModel):
    """Area aggregate only -- no restaurant is individually named."""
    count: int
    avg_rating: float | None = None
    cost_for_two_min: float | None = None
    cost_for_two_max: float | None = None
    offers_count: int = 0


class PositioningInsight(BaseModel):
    your_cost_for_two_estimate: float
    rank: int
    total: int
    cheaper_than_count: int
    pricier_than_count: int


class MenuBreadth(BaseModel):
    your_item_count: int
    competitor_avg_item_count: float
    competitors_sampled: int


class CuisineCrowding(BaseModel):
    cuisine: str
    matching_count: int
    total_checked: int


class VegMix(BaseModel):
    veg_count: int
    total: int


class CompetitorPricing(BaseModel):
    restaurants_checked_count: int = 0
    comparisons: list[PricingComparison]
    deals_active_count: int = 0
    deals_summary: str = ""
    pricing_impact: list[PricingImpactItem] = []
    category_pricing: list[CategoryPricing] = []
    landscape_summary: LandscapeSummary | None = None
    positioning: PositioningInsight | None = None
    menu_breadth: MenuBreadth | None = None
    cuisine_crowding: CuisineCrowding | None = None
    veg_mix: VegMix | None = None
    fetched_at: str | None = None


class SlotDeal(BaseModel):
    time: str
    deal_title: str
    discount_pct: float
    is_free: bool


class SlotAvailability(BaseModel):
    time: str
    avg_availability: float
    signal: Literal["HIGH", "MEDIUM", "LOW"]


class AreaOccupancy(BaseModel):
    signal: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    tonight_busy: bool | None = None
    competitors_checked: int = 0
    dineout_deals_count: int = 0
    dineout_deals_summary: str = ""
    slot_deals_found: list[SlotDeal] = []
    slot_availability_by_time: list[SlotAvailability] = []
    fetched_at: str | None = None


class ProcurementItem(BaseModel):
    name: str
    price: float
    unit: str
    in_stock: bool


class Weather(BaseModel):
    """P6-A21 -- Open-Meteo, not Swiggy MCP, so independent of swiggy_connected."""
    condition: Literal["heavy_rain", "light_rain", "very_hot", "clear"]
    avg_precipitation_pct: float | None = None
    avg_temp_celsius: float | None = None
    delivery_impact: str
    dinein_impact: str
    signal: str


class UpcomingHoliday(BaseModel):
    date: str
    name: str
    days_away: int


class IndustryTrends(BaseModel):
    """P6-A22 -- curated RSS trade press, not Swiggy MCP, independent of swiggy_connected."""
    digest: str
    headline_count: int
    sources_used: int
    fetched_at: str | None = None


class RegulatoryNotice(BaseModel):
    title: str
    uploaded_on: str
    url: str


class ComplianceAlerts(BaseModel):
    """P6-A23 -- FSSAI public notices, not Swiggy MCP, independent of swiggy_connected."""
    notices: list[RegulatoryNotice] = []
    notice_count: int
    fetched_at: str | None = None


class MarketPulseResponse(BaseModel):
    swiggy_connected: bool
    competitor_pricing: CompetitorPricing | None = None
    area_occupancy: AreaOccupancy | None = None
    procurement: list[ProcurementItem] = []
    weather: Weather | None = None
    upcoming_holiday: UpcomingHoliday | None = None
    industry_trends: IndustryTrends | None = None
    compliance_alerts: ComplianceAlerts | None = None


def _get_upcoming_holiday() -> UpcomingHoliday | None:
    """Cheap dict scan against INDIAN_HOLIDAYS_2026 -- no API call, independent
    of Swiggy connection status. Always returns the nearest holiday from today
    onward, however far out -- the frontend styles it differently depending on
    days_away (highlighted if within a week, a plain mention otherwise), but
    the section should never just go empty because nothing was imminent."""
    from app.core.constants import INDIAN_HOLIDAYS_2026

    today = date.today()
    upcoming = [
        (parsed, name)
        for iso, name in INDIAN_HOLIDAYS_2026.items()
        if (parsed := date.fromisoformat(iso)) >= today
    ]
    if not upcoming:
        return None
    nearest_date, nearest_name = min(upcoming, key=lambda pair: pair[0])
    days_away = (nearest_date - today).days
    return UpcomingHoliday(date=nearest_date.isoformat(), name=nearest_name, days_away=days_away)


@router.get("/pulse", response_model=MarketPulseResponse)
async def get_market_pulse(
    force_refresh: bool = False,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketPulseResponse:
    # Weather + holiday + industry trends + regulatory alerts are independent
    # of Swiggy connection status -- none of the four is Swiggy MCP, never
    # gated behind swiggy_connected. They're also independent of EACH OTHER
    # (3 separate external calls: Open-Meteo, curated RSS, FSSAI notices), so
    # gather them concurrently instead of awaiting one after another -- this
    # was previously the single biggest contributor to /market/pulse's real
    # end-to-end latency (three sequential network round-trips before Swiggy
    # was even reached).
    # `force_refresh` bypasses trends/compliance's 1-hour Redis cache -- used
    # by the frontend's manual refresh button, since the hourly cache is
    # otherwise shared/automatic and a user has no other way to force a
    # genuinely fresh read (WeatherService has no cache to bypass).
    weather_signal, trends_signal, compliance_signal = await asyncio.gather(
        WeatherService().get_forecast(lat=DEFAULT_RESTAURANT_LAT, lng=DEFAULT_RESTAURANT_LNG, target_date=date.today()),
        TrendsService().get_digest(force_refresh=force_refresh),
        ComplianceAlertsService().get_alerts(force_refresh=force_refresh),
    )
    weather = Weather(**weather_signal) if weather_signal else None
    upcoming_holiday = _get_upcoming_holiday()
    industry_trends = IndustryTrends(**trends_signal) if trends_signal else None
    compliance_alerts = ComplianceAlerts(**compliance_signal) if compliance_signal else None

    client = SwiggyMCPClient()
    if not client.is_available():
        return MarketPulseResponse(
            swiggy_connected=False, weather=weather, upcoming_holiday=upcoming_holiday,
            industry_trends=industry_trends, compliance_alerts=compliance_alerts,
        )

    org = db.query(Organization).filter(Organization.id == current["org_id"]).first()
    cuisine = (org.settings or {}).get("cuisine_type", "restaurant") if org else "restaurant"

    our_items = [
        {"name": item.name, "price": item.price, "category": item.category}
        for item in db.query(MenuItem).filter(MenuItem.is_available.is_(True)).all()
    ]

    inventory_service = InventoryService(db=db, llm=None)
    context = {"org_id": current["org_id"], "cuisine": cuisine, "our_items": our_items}

    # shortage_data doesn't depend on competitor/occupancy (or vice versa) --
    # only procurement below depends on shortage_data's result -- so all
    # three run concurrently instead of shortage_data blocking ahead of the
    # Swiggy gather.
    shortage_data, competitor_ctx, occupancy_ctx = await asyncio.gather(
        inventory_service.compute_shortage_data(),
        CompetitorEnricher(client).enrich(context),
        OccupancyEnricher(client).enrich(context),
    )
    shortage_names = [
        alert["ingredient"]
        for alert in shortage_data["actionable_shortages"]
        if isinstance(alert, dict) and alert.get("ingredient")
    ]

    procurement_ctx = None
    if shortage_names:
        procurement_ctx = await ProcurementEnricher(client).enrich({
            "org_id": current["org_id"],
            "shortage_items": shortage_names,
        })

    competitor_pricing = None
    if competitor_ctx:
        area_avg = competitor_ctx.get("area_avg") or {}
        our_price_by_name = {str(i["name"]).strip().lower(): i["price"] for i in our_items}

        # Show EVERY dish found nearby (up to a display cap), not just the handful
        # that happen to exact-string-match one of our own item names -- "area pricing
        # across all dishes" means all dishes, matched or not. Matched dishes
        # (our_price present) surface first so the actionable comparisons lead.
        comparisons: list[PricingComparison] = []
        for dish, avg_price in area_avg.items():
            if not avg_price:
                continue
            our_price = our_price_by_name.get(dish)
            if our_price is not None:
                raw_diff_pct = (our_price - avg_price) / avg_price * 100
                comparisons.append(PricingComparison(
                    item=dish.title(),
                    area_avg=avg_price,
                    your_price=our_price,
                    diff_pct=round(abs(raw_diff_pct), 1),
                    direction="above" if raw_diff_pct >= 0 else "below",
                ))
            else:
                comparisons.append(PricingComparison(item=dish.title(), area_avg=avg_price))

        comparisons.sort(key=lambda c: (c.your_price is None, -(c.diff_pct or 0), -c.area_avg))
        comparisons = comparisons[:40]

        positioning_data = competitor_ctx.get("positioning")
        landscape_data = competitor_ctx.get("landscape_summary")

        competitor_pricing = CompetitorPricing(
            restaurants_checked_count=competitor_ctx.get("area_restaurant_count") or 0,
            comparisons=comparisons,
            deals_active_count=competitor_ctx.get("deals_active_count") or 0,
            deals_summary=competitor_ctx.get("deals_summary") or "",
            pricing_impact=[
                PricingImpactItem(**impact) for impact in (competitor_ctx.get("pricing_impact") or [])
            ],
            category_pricing=[
                CategoryPricing(**cat) for cat in (competitor_ctx.get("category_pricing") or [])
            ],
            landscape_summary=LandscapeSummary(**landscape_data) if landscape_data else None,
            positioning=PositioningInsight(**positioning_data) if positioning_data else None,
            menu_breadth=MenuBreadth(**competitor_ctx["menu_breadth"]) if competitor_ctx.get("menu_breadth") else None,
            cuisine_crowding=CuisineCrowding(**competitor_ctx["cuisine_crowding"]) if competitor_ctx.get("cuisine_crowding") else None,
            veg_mix=VegMix(**competitor_ctx["veg_mix"]) if competitor_ctx.get("veg_mix") else None,
            fetched_at=competitor_ctx.get("fetched_at"),
        )

    area_occupancy = None
    if occupancy_ctx:
        area_occupancy = AreaOccupancy(
            signal=occupancy_ctx.get("occupancy_signal"),
            tonight_busy=occupancy_ctx.get("tonight_busy"),
            competitors_checked=occupancy_ctx.get("competitors_checked") or 0,
            dineout_deals_count=occupancy_ctx.get("dineout_deals_count") or 0,
            dineout_deals_summary=occupancy_ctx.get("dineout_deals_summary") or "",
            slot_deals_found=[
                SlotDeal(**d) for d in (occupancy_ctx.get("slot_deals_found") or [])
            ],
            slot_availability_by_time=[
                SlotAvailability(**s) for s in (occupancy_ctx.get("slot_availability_by_time") or [])
            ],
            fetched_at=occupancy_ctx.get("fetched_at"),
        )

    # NOTE: your_go_to_items (Instamart "frequent reorder" data) is deliberately not
    # used here or anywhere else on this page. It returns the PERSONAL Swiggy consumer
    # account's own purchase history (seen live: pet food, personal groceries) — not
    # restaurant procurement data. See CLAUDE.md's Swiggy MCP consumer-data warning.
    procurement: list[ProcurementItem] = []
    if procurement_ctx:
        for opt in procurement_ctx.get("procurement_options") or []:
            procurement.append(ProcurementItem(
                name=str(opt.get("ingredient", "")).title(),
                price=float(opt.get("price") or 0),
                unit=str(opt.get("unit") or ""),
                in_stock=bool(opt.get("inStock", False)),
            ))

    return MarketPulseResponse(
        swiggy_connected=True,
        competitor_pricing=competitor_pricing,
        area_occupancy=area_occupancy,
        procurement=procurement,
        weather=weather,
        upcoming_holiday=upcoming_holiday,
        industry_trends=industry_trends,
        compliance_alerts=compliance_alerts,
    )


# ── Live ingredient price lookup (on-demand, not cached) ───────────────────────

class IngredientSearchResult(BaseModel):
    name: str
    category: str
    price: float
    unit: str
    in_stock: bool


class IngredientSearchResponse(BaseModel):
    swiggy_connected: bool
    query: str
    results: list[IngredientSearchResult] = []


@router.get("/ingredient-search", response_model=IngredientSearchResponse)
async def search_ingredient(
    query: str = Query(..., min_length=1, max_length=80),
    current: dict = Depends(get_current_user),
) -> IngredientSearchResponse:
    """On-demand Instamart search — owner types an ingredient, sees live price/stock.

    Independent of shortage computation, unlike the shortage-driven procurement list
    in /market/pulse. Not cached — this is an explicit user action, freshness matters
    more than avoiding a repeat Swiggy call for the exact same query.
    """
    client = SwiggyMCPClient()
    if not client.is_available():
        return IngredientSearchResponse(swiggy_connected=False, query=query)

    address_id = get_settings().swiggy_address_id or ""
    results = await ProcurementEnricher(client).search_live(address_id, query)

    return IngredientSearchResponse(
        swiggy_connected=True,
        query=query,
        results=[
            IngredientSearchResult(
                name=r["name"], category=r["category"], price=r["price"],
                unit=r["unit"], in_stock=r["inStock"],
            )
            for r in (results or [])
        ],
    )


# ── Price trends across past planning runs (P6-MI11) ──────────────────────────
# No new Swiggy calls — reads market_intel already stored in each PlanningRun's
# final_response, so this is free to call on every /market page load.

class PricePoint(BaseModel):
    date: str
    area_avg: float


class OccupancyPoint(BaseModel):
    date: str
    signal: Literal["HIGH", "MEDIUM", "LOW"]


class MarketTrendsResponse(BaseModel):
    price_trends: dict[str, list[PricePoint]] = {}
    occupancy_trend: list[OccupancyPoint] = []
    days_returned: int
    note: str | None = None


@router.get("/trends", response_model=MarketTrendsResponse)
async def get_market_trends(
    days: int = Query(default=7, ge=1, le=90),
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketTrendsResponse:
    # Scan a generous window of recent runs since not every run necessarily has
    # market_intel data (Swiggy unavailable, cache miss, etc) — we want up to
    # `days` runs that actually carry it, not just the last `days` runs overall.
    runs = RunService(db).list_runs(current["org_id"], limit=max(days * 3, 30))

    price_series: dict[str, list[PricePoint]] = {}
    occupancy_series: list[OccupancyPoint] = []
    points_collected = 0

    for run in runs:
        if points_collected >= days:
            break

        market_intel = (run.final_response or {}).get("market_intel") or {}
        area_avg = market_intel.get("competitor_pricing") or {}
        occupancy_signal = market_intel.get("area_occupancy")
        run_date = market_intel.get("fetched_at") or run.target_date or (
            run.created_at.date().isoformat() if run.created_at else None
        )

        if not run_date or (not area_avg and not occupancy_signal):
            continue

        for dish, avg_price in area_avg.items():
            price_series.setdefault(dish, []).append(
                PricePoint(date=run_date, area_avg=float(avg_price))
            )

        if occupancy_signal in ("HIGH", "MEDIUM", "LOW"):
            occupancy_series.append(OccupancyPoint(date=run_date, signal=occupancy_signal))

        points_collected += 1

    # Runs are newest-first from list_runs(); flip to chronological order for charting.
    for points in price_series.values():
        points.reverse()
    occupancy_series.reverse()

    note = None
    if points_collected < 3:
        note = "Run 3+ plans with Swiggy market intelligence enabled to see pricing trends."

    return MarketTrendsResponse(
        price_trends=price_series,
        occupancy_trend=occupancy_series,
        days_returned=points_collected,
        note=note,
    )

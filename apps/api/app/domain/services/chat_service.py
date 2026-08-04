"""
P5-12 RAG chatbot service — enhanced for P6-S04 with:
  - Groq function calling (ReAct tool use)
  - Cross-session memory (Qdrant session summaries)
  - Proactive critic failure pattern surfacing
  - Semantic cache (Qdrant, similarity >= 0.92)
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Optional

import structlog
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.domain.services.business_analytics_service import BusinessAnalyticsService
from app.infrastructure.db.models import Feedback, PlanningRun, SentimentType
from app.infrastructure.llm.prompt_utils import PromptUtils
from app.infrastructure.swiggy.client import (
    FOOD_ENDPOINT,
    INSTAMART_ENDPOINT,
    SwiggyMCPClient,
)
from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher
from app.infrastructure.swiggy.enrichers.occupancy import OccupancyEnricher

# structlog, not stdlib logging: stdlib .info()/.debug() calls are silently
# dropped in this app (no logging.basicConfig() is ever called).
logger = structlog.get_logger()

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 1024
_MAX_RUNS = 10
_MAX_TOOL_ITERATIONS = 3
_MAX_TOOL_RESULT_ITEMS = 8  # cap on list-shaped Swiggy tool results (orders/products) fed
                            # back into the LLM -- an unbounded list was the confirmed cause
                            # of a single swiggy_search_products call alone hitting ~11,000
                            # tokens and blowing the Groq free-tier 12,000 TPM budget

_SWIGGY_TOOL_NAMES = {
    "swiggy_get_food_orders", "swiggy_search_products",
    "swiggy_get_competitor_deals", "swiggy_get_area_occupancy", "swiggy_get_common_dishes",
}


# ── Tool definitions (Groq / OpenAI function calling format) ─────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_runs",
            "description": (
                "Query recent planning runs for this org. Returns scenario, verdict, "
                "score, and key highlights. Use when the user asks about past plans, "
                "recent runs, or historical performance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "How many recent runs to return (default 5, max 10)",
                        "default": 5,
                    },
                    "scenario_filter": {
                        "type": "string",
                        "description": "Optional scenario name to filter by (e.g. 'friday_rush')",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_run_detail",
            "description": (
                "Get full detail on a specific planning run by its ID. "
                "Use when the user references a specific run or asks to explain a result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "integer",
                        "description": "The database ID of the planning run",
                    }
                },
                "required": ["run_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_status",
            "description": (
                "Get current inventory shortage and overstock alerts from the most recent "
                "planning run. Use when the user asks about stock levels, shortages, or "
                "what needs restocking."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_planning_run",
            "description": (
                "Trigger a new planning run for the given scenario. Use ONLY when the user "
                "explicitly asks to run a new plan or refresh a scenario. Do NOT use just "
                "to look up information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario": {
                        "type": "string",
                        "description": "Scenario ID (e.g. 'friday_rush', 'weekday_lunch')",
                    }
                },
                "required": ["scenario"],
            },
        },
    },
    # ── Swiggy live data tools (P6-S13c) ────────────────────────────────────
    # NOTE: swiggy_search_menu was removed (P6-A3) -- confirmed to return zero
    # results for every query tested against this Swiggy sandbox, same finding
    # that led to removing it from CompetitorEnricher.
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_food_orders",
            "description": (
                "Fetch recent food orders from Swiggy for this restaurant. Use when the user "
                "asks about Swiggy order history, top-selling items, order volume, or past "
                "Swiggy performance. Returns order list with items, amounts, and timestamps."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_search_products",
            "description": (
                "Search Swiggy Instamart for ingredient prices and availability. Use when the "
                "user asks about ingredient costs, procurement options, or what something costs "
                "on Instamart right now. Returns product name, price, unit, and stock status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Ingredient or product to search for (e.g. 'tomatoes', 'cream', 'onions')",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # ── Swiggy Dineout area-market tools (P6-MI04) ──────────────────────────
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_competitor_deals",
            "description": (
                "Get a count/summary of live promotional deals active nearby right now, combining "
                "Swiggy Food coupons and Dineout pre-booking offers. Area aggregate only -- no "
                "individual restaurant names or per-restaurant deal detail. Use when the user asks "
                "what deals or offers are around tonight, or whether anyone nearby is discounting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cuisine": {
                        "type": "string",
                        "description": "Cuisine or restaurant type to search nearby (e.g. 'North Indian', 'Biryani'). Defaults to a broad search if omitted.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_area_occupancy",
            "description": (
                "Get how full nearby restaurants are right now, based on live Swiggy Dineout table "
                "availability. Area aggregate signal only. Use when the user asks how busy the area "
                "is or what tonight's demand signal looks like."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cuisine": {
                        "type": "string",
                        "description": "Cuisine or restaurant type to search nearby (e.g. 'North Indian'). Defaults to a broad search if omitted.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_common_dishes",
            "description": (
                "Get dishes that commonly appear across nearby menus on Swiggy, with area-average "
                "pricing for each. NOTE: this reflects menu presence, not order volume or "
                "popularity — Swiggy's consumer API does not expose sales data. Use when the user "
                "asks what dishes are commonly offered nearby or what's typically priced around a "
                "certain range in the area."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cuisine": {
                        "type": "string",
                        "description": "Cuisine or restaurant type to search nearby (e.g. 'North Indian'). Defaults to a broad search if omitted.",
                    },
                },
                "required": [],
            },
        },
    },
    # ── Action Queue + market brief tools (P6-A13) -- same capabilities the
    # MCP server exposes to Claude Desktop, wired here so the in-app chatbot
    # has them too. ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_market_brief",
            "description": (
                "Get a full live market snapshot: category-level pricing vs the area average, "
                "your market positioning, menu breadth, cuisine crowding, veg/non-veg mix, "
                "live area deals, and area occupancy tonight. Broader than the individual "
                "swiggy_* tools -- use when the user asks for an overall market summary or "
                "'how are we doing' rather than one specific signal."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_action_queue",
            "description": (
                "List pending (or other-status) actions in the Action Queue -- e.g. restock "
                "alerts, WhatsApp vendor order drafts awaiting approval, pricing/promo review "
                "flags. Use when the user asks what's waiting for their approval or attention."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status. Defaults to 'pending' if omitted.",
                        "enum": ["pending", "approved", "executed", "rejected", "expired"],
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_action",
            "description": (
                "Approve a specific Action Queue item by its ID. For a WhatsApp vendor-order "
                "action, this is the same step that actually sends the message -- there's "
                "nothing further to approve once the user has explicitly said to approve it. "
                "Use ONLY when the user explicitly approves a specific action (e.g. 'approve "
                "the mozzarella reorder') -- never approve on your own initiative."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_id": {
                        "type": "integer",
                        "description": "The ID of the action to approve, from get_action_queue's results.",
                    },
                },
                "required": ["action_id"],
            },
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────────────

def _run_tool(name: str, args: dict, db: Session, org_id: int, user_id: Optional[int] = None) -> str:
    """Execute a tool call and return a JSON string result."""
    try:
        if name == "get_action_queue":
            from app.domain.services.action_queue_service import ActionQueueService
            from app.domain.services.trust_ladder_service import TrustLadderService
            from app.infrastructure.db.models import ActionStatus

            status_arg = args.get("status") or "pending"
            try:
                status_enum = ActionStatus(status_arg)
            except ValueError:
                return json.dumps({"error": f"Invalid status '{status_arg}'"})

            service = ActionQueueService(db)
            trust_ladder = TrustLadderService(db)
            actions = service.list_actions(org_id, status=status_enum)
            return json.dumps({
                "actions": [
                    {
                        "id": a.id, "category": a.category, "tier": a.tier.value,
                        "status": a.status.value, "title": a.title,
                        "approval_streak": trust_ladder.count_consecutive_approvals(org_id, a.category),
                    }
                    for a in actions
                ]
            })

        if name == "approve_action":
            from app.domain.services.action_execution_service import approve_and_execute
            from app.domain.services.action_queue_service import ActionQueueService

            action_id = int(args["action_id"])
            existing = ActionQueueService(db).get(action_id)
            if existing is None or existing.org_id != org_id:
                return json.dumps({"error": f"Action {action_id} not found for this org"})
            if not user_id:
                return json.dumps({"error": "Cannot approve -- no authenticated user for this session"})

            action = approve_and_execute(db, action_id, user_id)
            return json.dumps({
                "id": action.id, "status": action.status.value,
                "error": action.error, "title": action.title,
            })

        if name == "query_runs":
            limit = min(int(args.get("limit", 5)), 10)
            sf    = args.get("scenario_filter")
            q = db.query(PlanningRun).filter(PlanningRun.org_id == org_id)
            if sf:
                q = q.filter(PlanningRun.scenario == sf)
            runs = q.order_by(PlanningRun.created_at.desc()).limit(limit).all()
            rows = []
            for r in runs:
                rows.append({
                    "id":       r.id,
                    "scenario": r.scenario,
                    "date":     r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
                    "verdict":  r.critic_verdict,
                    "score":    round(r.critic_score, 2) if r.critic_score else None,
                    "notes":    (r.critic or {}).get("notes", "")[:200],
                })
            return json.dumps({"runs": rows})

        if name == "get_run_detail":
            run_id = int(args["run_id"])
            r = db.query(PlanningRun).filter(
                PlanningRun.id == run_id,
                PlanningRun.org_id == org_id,
            ).first()
            if not r:
                return json.dumps({"error": f"Run {run_id} not found for this org"})
            return json.dumps({
                "id":       r.id,
                "scenario": r.scenario,
                "verdict":  r.critic_verdict,
                "score":    r.critic_score,
                "critic":   r.critic,
                "final_response": (r.final_response or {}).get("recommendations"),
            }, default=str)

        if name == "get_inventory_status":
            r = (
                db.query(PlanningRun)
                .filter(PlanningRun.org_id == org_id)
                .order_by(PlanningRun.created_at.desc())
                .first()
            )
            if not r or not r.final_response:
                return json.dumps({"error": "No planning runs found"})
            inv = (r.final_response.get("recommendations") or {}).get("inventory") or {}
            inv_data = inv.get("data") or {}
            return json.dumps({
                "shortages":        inv_data.get("shortage_alerts", []),
                "overstock":        inv_data.get("overstock_alerts", []),
                "restock_actions":  inv.get("restock_actions", []),
                "as_of_run_date":   r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
            })

        if name == "trigger_planning_run":
            scenario = args.get("scenario", "friday_rush")
            return json.dumps({
                "status":  "triggered",
                "message": (
                    f"Planning run for '{scenario}' has been queued. "
                    "Results will appear in the Runs section shortly."
                ),
                "scenario": scenario,
            })

    except Exception as exc:
        logger.warning("chat_tool_failed", tool=name, error=str(exc))
        return json.dumps({"error": str(exc)})

    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Swiggy live tool execution ────────────────────────────────────────────────

async def _run_swiggy_tool(name: str, args: dict, org_id: int = 0) -> str:
    """Execute a Swiggy MCP tool and return a JSON string result.

    Uses settings.swiggy_address_id as the default addressId for all calls.
    Returns graceful error JSON if Swiggy is unavailable — never raises.
    """
    client = SwiggyMCPClient()
    if not client.is_available():
        return json.dumps({
            "error": "Swiggy not connected",
            "hint": "Connect your Swiggy account in the /connectors page to use live Swiggy data.",
        })

    settings = get_settings()
    address_id = settings.swiggy_address_id or ""

    try:
        if name == "swiggy_get_food_orders":
            result = await client.call_tool(
                FOOD_ENDPOINT,
                "get_food_orders",
                {"addressId": address_id},
            )
            if result is None:
                return json.dumps({"error": "Swiggy get_food_orders returned no data"})
            orders = result.get("orders") or result.get("data") or result
            # Trim each order to what a chat answer actually needs -- the raw
            # order carries a full "actions"/"reorderMeta" UI-action tree
            # (per-item addons, choice IDs, etc.) meant for a checkout client,
            # not a text answer. Confirmed live: this alone was ~2-3x the size
            # a plain order summary needs.
            trimmed = [
                {
                    "restaurant":    o.get("restaurantName"),
                    "total":         o.get("orderTotal"),
                    "items":         o.get("orderedItems"),
                    "ordered_at":    o.get("orderedTime"),
                    "status":        o.get("orderStatus"),
                }
                for o in (orders if isinstance(orders, list) else [])
            ][:_MAX_TOOL_RESULT_ITEMS]
            return json.dumps({"source": "Swiggy Food (live)", "orders": trimmed})

        if name == "swiggy_search_products":
            result = await client.call_tool(
                INSTAMART_ENDPOINT,
                "search_products",
                {"query": args.get("query", ""), "addressId": address_id},
            )
            if result is None:
                return json.dumps({"error": "Swiggy search_products returned no data"})

            # This MCP tool returns its payload as an MCP "text" content block
            # (a JSON string), not structured content -- confirmed live: the
            # unwrapped shape is {"data": {"products": [...], "similarProducts":
            # [...]}, "message": "<a long multi-paragraph display-instructions
            # string meant for a UI client, not this chatbot>"}. The previous
            # `result.get("products") or result.get("items") or result`
            # matched neither key, so it silently fell through to `result`
            # itself -- dumping the ENTIRE raw wrapper (20 products + 9
            # "similar" products + that instructions paragraph, every field
            # including image URLs/ratings/SLA/badges) into the tool result.
            # Measured live: ~44,000 characters (~11,000 tokens) for a single
            # "pasta" search -- almost the entire Groq free-tier 12,000 TPM
            # budget from one tool call, confirmed as the actual cause of the
            # rate-limit failures reported on this tool specifically.
            payload = result
            if isinstance(result, dict) and "text" in result and "products" not in result:
                try:
                    payload = json.loads(result["text"]).get("data", {})
                except Exception:
                    payload = {}
            raw_products = payload.get("products") or payload.get("items") or []

            def _summarize(p: dict) -> dict:
                variation = (p.get("variations") or [{}])[0]
                price = variation.get("price") or {}
                return {
                    "name":       p.get("displayName"),
                    "brand":      p.get("brand"),
                    "quantity":   variation.get("quantityDescription"),
                    "mrp":        price.get("mrp"),
                    "offer_price": price.get("offerPrice"),
                    "in_stock":   p.get("inStock", variation.get("isInStockAndAvailable")),
                }

            products = [_summarize(p) for p in raw_products[:_MAX_TOOL_RESULT_ITEMS]]
            return json.dumps({"source": "Swiggy Instamart (live)", "products": products})

        # ── Dineout competitive-intelligence tools (P6-MI04) ────────────────
        # Reuse the same enrichers the planning pipeline uses, so the chatbot's
        # answer is always consistent with what a plan run would see — and
        # benefits from the same 30-min Redis cache (no extra Swiggy load).
        if name == "swiggy_get_competitor_deals":
            cuisine = args.get("cuisine") or "restaurant"
            context = {"org_id": org_id, "cuisine": cuisine}
            competitor_ctx, occupancy_ctx = await asyncio.gather(
                CompetitorEnricher(client).enrich(context),
                OccupancyEnricher(client).enrich(context),
            )
            food_deals_count = (competitor_ctx or {}).get("deals_active_count") or 0
            food_deals_summary = (competitor_ctx or {}).get("deals_summary") or ""
            dineout_deals_count = (occupancy_ctx or {}).get("dineout_deals_count") or 0
            dineout_deals_summary = (occupancy_ctx or {}).get("dineout_deals_summary") or ""
            slot_deals = (occupancy_ctx or {}).get("slot_deals_found") or []
            if not food_deals_count and not dineout_deals_count and not slot_deals:
                return json.dumps({"error": "No area deal data available right now"})
            return json.dumps({
                "source": "Swiggy Food + Dineout (live, area aggregate)",
                "food_deals_summary": food_deals_summary,
                "dineout_prebooking_deals_summary": dineout_deals_summary,
                "dineout_slot_deals_tonight": slot_deals,
            })

        if name == "swiggy_get_area_occupancy":
            cuisine = args.get("cuisine") or "restaurant"
            occupancy_ctx = await OccupancyEnricher(client).enrich({"org_id": org_id, "cuisine": cuisine})
            if not occupancy_ctx:
                return json.dumps({"error": "No area occupancy data available right now"})
            return json.dumps({
                "source": "Swiggy Dineout (live)",
                "occupancy_signal": occupancy_ctx.get("occupancy_signal"),
                "tonight_busy": occupancy_ctx.get("tonight_busy"),
                "competitors_checked": occupancy_ctx.get("competitors_checked"),
            })

        if name == "swiggy_get_common_dishes":
            cuisine = args.get("cuisine") or "restaurant"
            competitor_ctx = await CompetitorEnricher(client).enrich({"org_id": org_id, "cuisine": cuisine})
            if not competitor_ctx or not competitor_ctx.get("area_avg"):
                return json.dumps({"error": "No competitor menu data available right now"})
            dishes = [
                {"dish": dish, "area_avg_price": price}
                for dish, price in sorted(competitor_ctx["area_avg"].items())
            ]
            return json.dumps({
                "source": "Swiggy Food (live)",
                "dishes": dishes[:20],
                "note": "Reflects dishes found across nearby competitor menus, not order-volume "
                        "popularity — Swiggy's consumer API doesn't expose competitor sales data.",
            })

    except Exception as exc:
        logger.warning("swiggy_chat_tool_failed", tool=name, error=str(exc))
        return json.dumps({"error": str(exc)})

    return json.dumps({"error": f"Unknown Swiggy tool: {name}"})


async def _run_market_brief(org_id: int, db: Session) -> str:
    """Reuses GET /market/pulse's own handler directly (same process, same
    logic) rather than duplicating its enricher-orchestration code here --
    current only needs org_id, so it's safe to construct a minimal dict
    instead of going through the real auth dependency."""
    try:
        from app.api.routes.market import get_market_pulse
        pulse = await get_market_pulse(current={"org_id": org_id}, db=db)
        return json.dumps(pulse.model_dump(), default=str)
    except Exception as exc:
        logger.warning("chat_tool_failed", tool="get_market_brief", error=str(exc))
        return json.dumps({"error": str(exc)})


# ── Context formatters ────────────────────────────────────────────────────────

def _format_runs(runs: list[PlanningRun]) -> str:
    if not runs:
        return "No planning runs found."
    lines = []
    for r in runs:
        score = f"{r.critic_score:.2f}" if r.critic_score else "n/a"
        date  = r.created_at.strftime("%Y-%m-%d") if r.created_at else "?"
        critic = r.critic or {}
        fr = r.final_response or {}
        recs = fr.get("recommendations", {})

        parts = [f"[{date}] scenario={r.scenario} verdict={r.critic_verdict} score={score}"]

        notes = critic.get("notes", "")
        if notes:
            parts.append(f"  critic_notes: {notes[:300]}")

        try:
            fd = recs["forecast"].get("data", {})
            predicted = fd.get("predicted_orders")
            avg = fd.get("avg_friday_orders") or fd.get("avg_same_day_orders")
            if predicted:
                parts.append(f"  demand: predicted_orders={predicted} avg={avg}")
        except (KeyError, TypeError, AttributeError):
            pass

        try:
            menu_rec = recs.get("menu") or {}
            highlights = menu_rec.get("highlight_items") or []
            top = (menu_rec.get("data") or {}).get("top_items") or []
            items = highlights or top
            if items:
                parts.append(f"  menu_highlights: {', '.join(str(i) for i in items[:6])}")
        except (KeyError, TypeError, AttributeError):
            pass

        try:
            inv = recs.get("inventory") or {}
            inv_data = inv.get("data") or {}
            shortages = inv_data.get("shortage_alerts", [])
            if shortages:
                names = [a.get("ingredient", a.get("item", "?")) for a in shortages[:4]]
                parts.append(f"  shortages: {', '.join(names)}")
            restock = inv.get("restock_actions", [])
            if restock:
                parts.append(f"  restock_actions: {'; '.join(str(a) for a in restock[:3])}")
        except (KeyError, TypeError, AttributeError):
            pass

        try:
            res = recs.get("reservation") or {}
            res_data = res.get("data") or {}
            guests = res_data.get("total_guests")
            occ = res_data.get("occupancy_pct")
            if guests:
                parts.append(f"  reservations: total_guests={guests} occupancy={occ}%")
        except (KeyError, TypeError, AttributeError):
            pass

        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _format_feedback(rows) -> str:
    if not rows:
        return "No feedback records found."
    neg = [r for r in rows if r.sentiment and r.sentiment.value == "negative"]
    pos = [r for r in rows if r.sentiment and r.sentiment.value == "positive"]
    samples = neg[:5] or rows[:5]
    lines = [f"Total feedback: {len(rows)} ({len(neg)} negative, {len(pos)} positive)"]
    if samples:
        lines.append("Sample negative feedback:")
        for fb in samples:
            lines.append(f"  - {str(fb.raw_text or '')[:150]}")
    return "\n".join(lines)


# ── Proactive pattern surfacing ───────────────────────────────────────────────

def get_recurring_failures(org_id: int, db: Session) -> Optional[str]:
    """
    Check the last 5 planning runs for a pattern of non-approved verdicts.
    Returns a warning string if >= 2 of the last 5 runs were not approved, else None.
    """
    try:
        recent = (
            db.query(PlanningRun)
            .filter(PlanningRun.org_id == org_id)
            .order_by(PlanningRun.created_at.desc())
            .limit(5)
            .all()
        )
        if len(recent) < 2:
            return None

        non_approved = [r for r in recent if r.critic_verdict != "approved"]
        if len(non_approved) < 2:
            return None

        verdicts = [r.critic_verdict for r in non_approved[:3]]
        scenarios = list({r.scenario for r in non_approved[:3]})
        return (
            f"⚠ Pattern detected: {len(non_approved)} of your last {len(recent)} planning runs "
            f"received non-approved verdicts ({', '.join(verdicts)}). "
            f"Affected scenarios: {', '.join(scenarios)}. "
            "Consider reviewing the recurring critic feedback or running an updated plan."
        )
    except Exception:
        return None


# ── Context builder ───────────────────────────────────────────────────────────

def build_context(
    org_id: int,
    org_name: str,
    question: str,
    db: Session,
    memory=None,
    session_memory=None,
    user_id: Optional[int] = None,
) -> str:
    runs = (
        db.query(PlanningRun)
        .filter(PlanningRun.org_id == org_id)
        .order_by(PlanningRun.created_at.desc())
        .limit(_MAX_RUNS)
        .all()
    )

    feedback_rows = (
        db.query(Feedback)
        .order_by(Feedback.created_at.desc())
        .limit(30)
        .all()
    )

    system_prompt = PromptUtils.format_chat_system_prompt(
        org_name=org_name,
        runs_text=_format_runs(runs),
        feedback_text=_format_feedback(feedback_rows),
        run_count=len(runs),
    )

    # P6-A2: retrieve semantically relevant past complaints + SOPs for the actual
    # question asked -- this parameter used to be accepted and never called, so
    # context was built entirely from raw SQL (last N runs/feedback rows) with no
    # relevance ranking at all.
    if memory:
        try:
            similar_complaints = memory.retrieve_similar_complaints(question, org_id, top_k=3)
            relevant_sops = memory.retrieve_relevant_sops(question, org_id, top_k=3)
            rag_lines = []
            if similar_complaints:
                rag_lines.append("\n## Relevant past complaints")
                rag_lines.extend(f"- {c['text']}" for c in similar_complaints)
            if relevant_sops:
                rag_lines.append("\n## Relevant SOPs")
                rag_lines.extend(f"- {s['text']}" for s in relevant_sops)
            if rag_lines:
                system_prompt += "\n" + "\n".join(rag_lines)
        except Exception:
            pass

    # Inject past session context if available
    if session_memory and user_id:
        try:
            past_sessions = session_memory.get_recent_sessions(
                org_id=org_id, user_id=user_id, query=question, top_k=3
            )
            if past_sessions:
                session_lines = ["\n## Previous session context"]
                for s in past_sessions:
                    session_lines.append(f"- {s['summary']}")
                system_prompt += "\n" + "\n".join(session_lines)
        except Exception:
            pass

    # Business analytics -- margin-aware dish performance, complaint category counts,
    # and real peak hours, the same signals the Today dashboard shows and the planning
    # pipeline now reads. Previously the chatbot had none of this structured data --
    # only raw planning-run/feedback rows -- so it couldn't answer "what's my margin on
    # X" or "what's my top complaint theme" with a real number.
    try:
        analytics = BusinessAnalyticsService(db)
        dishes = analytics.get_dish_performance(days=14)[:5]
        categories = analytics.get_complaints_by_category(days=28)[:3]
        peak = sorted(analytics.get_peak_hours(days=14), key=lambda h: h["avg_orders"], reverse=True)[:2]

        analytics_lines = ["\n## Business analytics (last 14 days)"]
        if dishes:
            analytics_lines.append("Top dishes by revenue (with margin where known):")
            analytics_lines.extend(
                f"- {d['name']}: Rs.{d['revenue']:.0f} revenue"
                + (f", {d['margin_pct']:.0f}% margin" if d["margin_pct"] is not None else ", margin unknown")
                for d in dishes
            )
        if categories:
            analytics_lines.append("Top complaint categories (last 28 days):")
            analytics_lines.extend(f"- {c['category']}: {c['count']}" for c in categories)
        if peak and any(h["avg_orders"] > 0 for h in peak):
            analytics_lines.append(
                "Real peak hours (actual orders): " +
                ", ".join(f"{h['hour']}:00 (avg {h['avg_orders']} orders)" for h in peak if h["avg_orders"] > 0)
            )
        if len(analytics_lines) > 1:
            system_prompt += "\n" + "\n".join(analytics_lines)
    except Exception:
        pass

    # Proactive pattern warning
    pattern_warning = get_recurring_failures(org_id, db)
    if pattern_warning:
        system_prompt += f"\n\n## Proactive insight\n{pattern_warning}"

    return system_prompt


# ── Chat LLM client factory ───────────────────────────────────────────────────

def _get_chat_client(settings):
    """
    Return (async_client, model_name) for the chatbot based on LLM_PROVIDER.

    Both Groq and CometAPI expose an OpenAI-compatible chat.completions interface,
    so the rest of stream_reply works unchanged regardless of provider.
    """
    provider = settings.llm_provider.strip().lower()
    if provider == "groq":
        from groq import AsyncGroq
        return AsyncGroq(api_key=settings.groq_api_key), _MODEL

    # comet / gemini / any other → CometAPI OpenAI-compatible endpoint
    from openai import AsyncOpenAI
    return (
        AsyncOpenAI(api_key=settings.cometapi_key, base_url="https://api.cometapi.com/v1"),
        settings.cometapi_model_fast,
    )


# ── Agentic streaming reply (ReAct via configurable LLM provider) ─────────────

async def stream_reply(
    question: str,
    history: list[dict],
    system_prompt: str,
    db: Optional[Session] = None,
    org_id: Optional[int] = None,
    chat_cache=None,
    user_id: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream a reply via the configured LLM provider with optional ReAct tool use.

    Flow:
    1. Check semantic cache — if hit, stream cached answer immediately.
    2. ReAct loop (max 3 iterations): call LLM with tools, execute any tool calls,
       feed results back, call again.
    3. Stream the final text response.
    4. Store in semantic cache.
    """
    settings = get_settings()
    client, model = _get_chat_client(settings)

    # ── Semantic cache check ─────────────────────────────────────────────────
    if chat_cache and org_id:
        cached_answer = chat_cache.get(org_id, question)
        if cached_answer:
            yield cached_answer
            return

    # ── Build message history with within-session compression ───────────────
    # Keep the last 8 turns verbatim. If there are older turns, summarise them
    # locally (no LLM call) and inject as a single context message so the model
    # retains continuity without blowing the token window.
    _RECENT_WINDOW = 8
    messages = [{"role": "system", "content": system_prompt}]
    if len(history) > _RECENT_WINDOW:
        from app.infrastructure.vector.session_memory import SessionMemoryService
        older  = history[:-_RECENT_WINDOW]
        recent = history[-_RECENT_WINDOW:]
        summary = SessionMemoryService.build_summary_from_messages(older, question)
        messages.append({"role": "assistant", "content": f"[Earlier in this session: {summary}]"})
        for msg in recent:
            messages.append({"role": msg["role"], "content": msg["content"]})
    else:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    # ── ReAct tool-use loop ──────────────────────────────────────────────────
    full_answer = ""
    tools_available = bool(db and org_id)

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=_TOOLS if tools_available else None,
            tool_choice="auto" if tools_available else None,
            max_tokens=_MAX_TOKENS,
            temperature=0.4,
            stream=False,
        )

        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            # Final text response — stream it
            full_answer = msg.content or ""
            break

        # Execute tool calls and append results
        messages.append({
            "role":       "assistant",
            "content":    msg.content or "",
            "tool_calls": [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}

            if tc.function.name == "get_market_brief":
                result = await _run_market_brief(org_id or 0, db)
            elif tc.function.name in _SWIGGY_TOOL_NAMES:
                result = await _run_swiggy_tool(tc.function.name, args, org_id or 0)
            else:
                result = _run_tool(tc.function.name, args, db, org_id, user_id)
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

    else:
        # Exhausted iterations without a text response — make one final call without tools
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=_MAX_TOKENS,
            temperature=0.4,
            stream=False,
        )
        full_answer = response.choices[0].message.content or ""

    # ── Store in semantic cache ──────────────────────────────────────────────
    if chat_cache and org_id and full_answer:
        try:
            chat_cache.set(org_id, question, full_answer)
        except Exception:
            pass

    # ── Stream the accumulated answer token-by-token via SSE ────────────────
    if full_answer:
        yield full_answer
        return

    # Fallback: streaming path if no tool calls were made on first pass
    stream = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}]
        + [{"role": msg["role"], "content": msg["content"]} for msg in history[-6:]]
        + [{"role": "user", "content": question}],
        stream=True,
        max_tokens=_MAX_TOKENS,
        temperature=0.4,
    )
    collected = []
    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            collected.append(token)
            yield token

    if chat_cache and org_id and collected:
        try:
            chat_cache.set(org_id, question, "".join(collected))
        except Exception:
            pass

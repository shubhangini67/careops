"""
Phase 6A-34 (originally scoped as Phase 6B): Guest Concierge Service.

Orchestrates all 3 Swiggy MCP servers (Food, Instamart, Dineout) to plan
complete consumer dining/event experiences end-to-end -- finding venues,
checking real slot availability, ordering food for delivery, and suggesting
+ ordering Instamart supplies. Fully independent of the restaurant-operator
side (chat_service.py): no shared data, no fake restaurant, no auth --
this serves a Swiggy consumer account directly, matching clause 1.1's
Proposed Arrangement in the signed Integration Agreement.

Modeled on chat_service.py's ReAct tool-calling shape (Groq function calling,
non-streaming per iteration, final answer chunked to the caller), but with
a purpose-built tool set and multi-turn session state persisted in Redis
(2-hour TTL) rather than the operator chatbot's DB-backed ChatSession model
-- a guest concierge session is disposable and has no user account to own it.

Every tool handler follows the same contract as the rest of this codebase's
Swiggy integration: never raise, degrade to an honest "not available right
now" message, and never silently fabricate a booking/order that didn't
actually happen. Execution tools (book_table, checkout) are staging-gated
exactly like the rest of the app -- shown with a clear "coming soon" notice
rather than hidden, since the enrichment/pricing/approval flow up to that
point is real today.
"""

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import AsyncGenerator, Optional

import redis.asyncio as aioredis
import structlog

from app.core.constants import DEFAULT_RESTAURANT_LAT, DEFAULT_RESTAURANT_LNG
from app.core.settings import get_settings
from app.infrastructure.swiggy.client import (
    DINEOUT_ENDPOINT,
    FOOD_ENDPOINT,
    INSTAMART_ENDPOINT,
    SwiggyMCPClient,
)

log = structlog.get_logger()

# search_restaurants_dineout returns EMPTY structuredContent and puts
# everything in freeform text meant for an LLM to read (confirmed live --
# see infrastructure/swiggy/enrichers/occupancy.py's _get_competitors for the
# original discovery), with lines like:
# "17. Ashz Cafe — Italian, North Indian | [object Object]★ | ₹500 for two | Kopar Khairane (ID: 662725)"
# The text also carries a "Search coordinates" hint with the coordinates
# Swiggy itself resolved for the query (e.g. a locality name) -- capturing
# that is how a guest's stated area (not just our fixed default) drives the
# rest of the session's Dineout calls.
_DINEOUT_ID_LINE_RE = re.compile(r'^\d+\.\s+(?P<name>.+?)\s+—.*\(ID:\s*(?P<id>\d+)\)', re.MULTILINE)
_DINEOUT_COORD_RE = re.compile(r'latitude=([\d.]+),\s*longitude=([\d.]+)')

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 1024
_MAX_TOOL_ITERATIONS = 4  # one more than chat_service.py's 3 -- concierge tool
                          # chains run slightly longer (e.g. find_venues then
                          # immediately check_table_availability in one turn)
_SESSION_TTL = 7200  # 2 hours
_SESSION_KEY_PREFIX = "concierge_session:"
_MAX_SUPPLY_SEARCHES = 5  # same per-run cap convention as ProcurementEnricher
_FOOD_ORDER_CAP_INR = 1000.0  # Builders Club v1 cap, COD only
_MAX_MENU_CATEGORIES = 4
_MAX_MENU_ITEMS_PER_CATEGORY = 6

# Hard rule: a guest never sees a raw exception, stack trace, or internal tool
# name. Every failure degrades to one of these fixed, friendly strings --
# the real error always still gets logged server-side via structlog.
_GENERIC_TOOL_ERROR = "Had trouble completing that just now. Let's try a different angle."
_GENERIC_TURN_ERROR = "Sorry, something went wrong on my end. Let's try that again."
_BUSY_TURN_ERROR = "I'm getting a lot of requests right now. Please try again in a few minutes."

# Friendly "what I'm doing right now" labels shown to the guest while a tool
# call is in flight, purely cosmetic -- never derived from tool internals.
_TOOL_STATUS_LABELS = {
    "find_venues": "Finding venues...",
    "get_venue_details": "Getting venue details...",
    "check_table_availability": "Checking table availability...",
    "book_table": "Booking your table...",
    "check_my_bookings": "Checking your bookings...",
    "find_food": "Finding restaurants...",
    "browse_menu": "Loading the menu...",
    "add_food_to_cart": "Updating your cart...",
    "view_food_cart": "Checking your cart...",
    "apply_best_coupon": "Applying the best coupon...",
    "place_food_order": "Placing your order...",
    "track_food_order": "Tracking your order...",
    "view_past_orders": "Checking past orders...",
    "find_supplies": "Finding supplies on Instamart...",
    "add_supplies_to_cart": "Updating your supplies cart...",
    "view_supplies_cart": "Checking your supplies cart...",
    "order_supplies": "Placing your Instamart order...",
    "track_supplies_delivery": "Tracking your delivery...",
    "get_budget_summary": "Adding up your budget...",
    "track_everything": "Gathering everything so far...",
}


def _staging_enabled() -> bool:
    return bool(get_settings().swiggy_staging_base_url)


def _friendly_turn_error(exc: Exception) -> str:
    if getattr(exc, "status_code", None) == 429 or "429" in str(exc):
        return _BUSY_TURN_ERROR
    return _GENERIC_TURN_ERROR


# ── Session state ─────────────────────────────────────────────────────────────

@dataclass
class ConciergeSession:
    session_id: str
    occasion: Optional[str] = None          # "birthday" | "anniversary" | "corporate" | "date" | "general"
    headcount: Optional[int] = None
    budget_inr: Optional[float] = None
    preferences: list[str] = field(default_factory=list)
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    address_id: Optional[str] = None
    budget_spent: float = 0.0
    active_bookings: list[dict] = field(default_factory=list)
    active_food_orders: list[dict] = field(default_factory=list)
    active_instamart_orders: list[dict] = field(default_factory=list)
    suggested_venues: list[dict] = field(default_factory=list)
    instamart_cart: list[dict] = field(default_factory=list)

    @property
    def budget_remaining(self) -> Optional[float]:
        if self.budget_inr is None:
            return None
        return self.budget_inr - self.budget_spent

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, raw: str) -> "ConciergeSession":
        data = json.loads(raw)
        return cls(**data)


# ── Tool definitions (Groq function calling) ──────────────────────────────────

CONCIERGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_venues",
            "description": (
                "Search for restaurants suitable for dining in. Use for birthday parties, "
                "anniversary dinners, corporate lunches, date nights, or any dine-in occasion. "
                "Returns real venues with ratings, deals, and estimated costs. "
                "Always call this before check_table_availability."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Cuisine or restaurant type (e.g. 'Italian', 'pizza', 'fine dining')"},
                    "occasion": {"type": "string", "description": "Type of occasion (birthday/anniversary/corporate/date/general)"},
                    "headcount": {"type": "integer", "description": "Number of guests"},
                    "locality": {"type": "string", "description": "Area or neighborhood the guest mentioned, if any (e.g. 'Vashi', 'Bandra'). Omit if the guest didn't specify one."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_venue_details",
            "description": (
                "Get full details for a specific restaurant including deals, amenities "
                "(Private Dining, Rooftop, Live Music), and timings. Use when the guest "
                "wants to know more about a specific venue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string", "description": "Dineout restaurant ID from find_venues"},
                    "restaurant_name": {"type": "string", "description": "Restaurant name (for display)"},
                },
                "required": ["restaurant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_table_availability",
            "description": (
                "Check real table availability at a restaurant for a specific date and party size. "
                "Returns available time slots with deals. Actual booking requires staging credentials "
                "-- will show available slots and confirm booking when available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string"},
                    "restaurant_name": {"type": "string"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "headcount": {"type": "integer"},
                },
                "required": ["restaurant_id", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_table",
            "description": (
                "Book a table at a restaurant. Requires a slot_id from check_table_availability. "
                "Confirmation isn't automatic yet, it will follow shortly. Shows the "
                "guest what the booking will look like."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string"},
                    "restaurant_name": {"type": "string"},
                    "slot_id": {"type": "integer", "description": "slotId from check_table_availability deals"},
                    "item_id": {"type": "string", "description": "itemId from the slot's deals"},
                    "reservation_time": {"type": "integer", "description": "epoch timestamp from slot"},
                    "display_time": {"type": "string", "description": "human-readable time for display"},
                    "headcount": {"type": "integer"},
                    "estimated_cost": {"type": "number"},
                },
                "required": ["restaurant_id", "slot_id", "item_id", "reservation_time", "headcount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_my_bookings",
            "description": "Show the guest's active Dineout bookings and their status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_food",
            "description": (
                "Search for food delivery options. Use when the guest wants to order food for "
                "delivery to their home address. Different from find_venues, which is for dine-in."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Food type or restaurant name (e.g. 'pizza', 'biryani', 'Dominos')"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_menu",
            "description": "Browse the menu of a specific restaurant for food delivery. Returns categories and items with prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string"},
                    "restaurant_name": {"type": "string"},
                    "page": {"type": "integer", "default": 1},
                },
                "required": ["restaurant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_food_to_cart",
            "description": "Add food items to the delivery cart. Cart is per-restaurant, switching restaurant clears it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_id": {"type": "string"},
                                "name": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "price": {"type": "number"},
                            },
                        },
                    },
                },
                "required": ["restaurant_id", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_food_cart",
            "description": "Show the guest's current food delivery cart with total and available coupons.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_best_coupon",
            "description": "Find and apply the best available COD-compatible coupon for the current cart.",
            "parameters": {
                "type": "object",
                "properties": {"restaurant_id": {"type": "string"}},
                "required": ["restaurant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_food_order",
            "description": (
                "Place a real food delivery order. Works right now (COD, under Rs.1000 per order). "
                "For larger orders, multiple orders may be needed. Always confirm with the guest "
                "before placing."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_food_order",
            "description": "Track active food delivery orders. Shows real-time status and ETA.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "Optional, if omitted tracks all active orders"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_past_orders",
            "description": "Show the guest's recent food delivery order history.",
            "parameters": {
                "type": "object",
                "properties": {"count": {"type": "integer", "default": 5}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_supplies",
            "description": (
                "Search Instamart for supplies, decorations, or grocery items. Best for: birthday "
                "cake, candles, balloons, paper plates, soft drinks, napkins, snacks, beverages, "
                "cleaning supplies. Be honest if specialty items (gaming merchandise, custom items) "
                "aren't found, and suggest Amazon or Meesho for those."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}, "description": "List of items to search for"},
                    "occasion": {"type": "string", "description": "Optional occasion context for smart defaults"},
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_supplies_to_cart",
            "description": "Add Instamart supply items to cart using their spin_ids. Cart is REPLACED not appended, include all items you want.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "spin_id": {"type": "string"},
                                "name": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "price": {"type": "number"},
                            },
                        },
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_supplies_cart",
            "description": "Show the current Instamart cart with all supply items and total cost.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "order_supplies",
            "description": (
                "Place Instamart order for supplies. Confirmation isn't automatic yet, it will "
                "follow shortly. Shows the guest what will be ordered and estimated delivery "
                "time (15-25 mins)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_supplies_delivery",
            "description": "Track active Instamart delivery. Shows real-time status and ETA.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_summary",
            "description": "Show a complete budget breakdown: total budget, amount spent so far, breakdown by category, remaining budget.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_everything",
            "description": "Show all active orders and bookings in one view: Dineout bookings, food delivery orders, Instamart deliveries.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

_HONEST_LIMITATIONS = (
    "HONEST LIMITATIONS: always keep these in mind and mention them plainly when relevant, "
    "never hide them or imply something works when it doesn't.\n"
    "- Food delivery orders are capped at Rs.1000 per order (Builders Club v1, COD only). For a "
    "large group, multiple separate orders (or contacting the restaurant directly) may be needed.\n"
    "- Dineout table booking (book_table) isn't confirming automatically yet. You can show real "
    "available slots and a booking summary, but say booking confirmation will follow shortly "
    "rather than claiming it's confirmed.\n"
    "- Instamart order placement (order_supplies) isn't confirming automatically yet. You can show "
    "a real cart and prices, but say order placement will follow shortly.\n"
    "- Instamart stocks everyday basics (cake, drinks, decor, paper goods), not gaming merchandise "
    "or other specialty items. Suggest Amazon or Meesho for those, honestly, rather than pretending "
    "Instamart has them.\n"
    "- Table availability for 14+ guests may be limited on Dineout. Suggest calling the venue ahead "
    "for very large groups.\n"
)


def _default_saturday() -> str:
    today = date.today()
    days_ahead = (5 - today.weekday()) % 7  # Monday=0 .. Saturday=5
    days_ahead = days_ahead or 7
    return (today + timedelta(days=days_ahead)).isoformat()


# ── Service ────────────────────────────────────────────────────────────────────

class ConciergeService:
    """Guest-facing orchestrator over Food/Instamart/Dineout MCP. No auth, no
    restaurant-operator data -- every session is a standalone, disposable
    consumer conversation persisted only in Redis."""

    def __init__(self, client: Optional[SwiggyMCPClient] = None) -> None:
        self._client = client or SwiggyMCPClient()
        self._redis: Optional[aioredis.Redis] = None
        self._dispatch = {
            "find_venues": self._tool_find_venues,
            "get_venue_details": self._tool_get_venue_details,
            "check_table_availability": self._tool_check_table_availability,
            "book_table": self._tool_book_table,
            "check_my_bookings": self._tool_check_my_bookings,
            "find_food": self._tool_find_food,
            "browse_menu": self._tool_browse_menu,
            "add_food_to_cart": self._tool_add_food_to_cart,
            "view_food_cart": self._tool_view_food_cart,
            "apply_best_coupon": self._tool_apply_best_coupon,
            "place_food_order": self._tool_place_food_order,
            "track_food_order": self._tool_track_food_order,
            "view_past_orders": self._tool_view_past_orders,
            "find_supplies": self._tool_find_supplies,
            "add_supplies_to_cart": self._tool_add_supplies_to_cart,
            "view_supplies_cart": self._tool_view_supplies_cart,
            "order_supplies": self._tool_order_supplies,
            "track_supplies_delivery": self._tool_track_supplies_delivery,
            "get_budget_summary": self._tool_get_budget_summary,
            "track_everything": self._tool_track_everything,
        }

    # ── Session persistence (Redis, 2h TTL) ─────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                get_settings().redis_url, encoding="utf-8", decode_responses=True,
            )
        return self._redis

    def new_session(self) -> ConciergeSession:
        return ConciergeSession(session_id=str(uuid.uuid4()))

    async def load_session(self, session_id: str) -> Optional[ConciergeSession]:
        try:
            r = await self._get_redis()
            raw = await r.get(f"{_SESSION_KEY_PREFIX}{session_id}")
            return ConciergeSession.from_json(raw) if raw else None
        except Exception as exc:
            log.warning("concierge_session_load_error", error=str(exc))
            return None

    async def save_session(self, session: ConciergeSession) -> None:
        try:
            r = await self._get_redis()
            await r.setex(f"{_SESSION_KEY_PREFIX}{session.session_id}", _SESSION_TTL, session.to_json())
        except Exception as exc:
            log.warning("concierge_session_save_error", error=str(exc))

    async def delete_session(self, session_id: str) -> None:
        try:
            r = await self._get_redis()
            await r.delete(f"{_SESSION_KEY_PREFIX}{session_id}")
        except Exception as exc:
            log.warning("concierge_session_delete_error", error=str(exc))

    # ── Intent extraction ────────────────────────────────────────────────────

    async def extract_intent(self, message: str) -> dict:
        """One-shot structured extraction. Never raises -- empty dict on failure."""
        try:
            client, model = self._get_llm_client()
            prompt = (
                "Extract structured event-planning info from this guest message. "
                "Return ONLY valid JSON, no markdown, no explanation, matching exactly this shape "
                '(use null for anything not mentioned):\n'
                '{"occasion": "birthday"|"anniversary"|"corporate"|"date"|"general"|null, '
                '"headcount": integer|null, "budget_inr": number|null, '
                '"preferences": [string, ...], '
                '"intent": "find_venue"|"check_slots"|"order_food"|"find_supplies"|'
                '"track_order"|"view_bookings"|"budget_summary"|"general"}\n\n'
                f"Message: {message}"
            )
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1,
                stream=False,
            )
            raw = response.choices[0].message.content or "{}"
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            return json.loads(clean.strip())
        except Exception as exc:
            log.warning("concierge_extract_intent_error", error=str(exc))
            return {}

    def _apply_intent(self, session: ConciergeSession, intent: dict) -> None:
        """Merge newly-extracted intent into session -- only overwrite fields
        that are actually present, so multi-turn context accumulates instead
        of getting wiped by a follow-up message that doesn't repeat everything."""
        if intent.get("occasion"):
            session.occasion = intent["occasion"]
        if intent.get("headcount"):
            session.headcount = int(intent["headcount"])
        if intent.get("budget_inr"):
            session.budget_inr = float(intent["budget_inr"])
        for pref in intent.get("preferences") or []:
            if pref and pref not in session.preferences:
                session.preferences.append(pref)

    # ── LLM client (same pattern as chat_service.py's _get_chat_client) ─────

    def _get_llm_client(self):
        settings = get_settings()
        provider = settings.llm_provider.strip().lower()
        if provider == "groq":
            from groq import AsyncGroq
            return AsyncGroq(api_key=settings.groq_api_key), _MODEL
        from openai import AsyncOpenAI
        return (
            AsyncOpenAI(api_key=settings.cometapi_key, base_url="https://api.cometapi.com/v1"),
            settings.cometapi_model_fast,
        )

    # ── System prompt ────────────────────────────────────────────────────────

    def _build_system_prompt(self, session: ConciergeSession) -> str:
        lines = [
            "You are CareOps AI's Guest Concierge, a consumer-facing assistant that plans "
            "complete dining and event experiences using Swiggy's Food, Instamart, and Dineout "
            "platforms. You are talking directly to a guest planning something for themselves, "
            "not a restaurant operator. Always mention you're 'Powered by Swiggy' naturally when "
            "you first help with something concrete.",
            "",
            "Be warm, concise, and proactive. Use tools to actually find real venues, food, and "
            "supplies rather than giving generic advice. Never fabricate a price, slot, or product "
            "that a tool didn't actually return. Never use em dashes or double hyphens in your "
            "responses; write in plain sentences with periods and commas instead.",
            "",
            "For birthday, anniversary, or party occasions: don't stop at venue or food. "
            "Proactively call find_supplies for the obvious event essentials (cake, decorations, "
            "balloons, drinks) in the same turn once the occasion is known, rather than waiting "
            "to be asked. A full plan covers venue/food AND supplies together.",
            "",
            "## Current session context",
            f"- Occasion: {session.occasion or 'not yet known'}",
            f"- Headcount: {session.headcount or 'not yet known'}",
        ]
        if session.budget_inr is not None:
            lines.append(f"- Budget: Rs.{session.budget_inr:.0f} (spent so far: Rs.{session.budget_spent:.0f}, remaining: Rs.{session.budget_remaining:.0f})")
        if session.preferences:
            lines.append(f"- Preferences mentioned: {', '.join(session.preferences)}")
        if session.active_bookings:
            lines.append(f"- Active Dineout bookings: {len(session.active_bookings)}")
        if session.active_food_orders:
            lines.append(f"- Active food orders: {len(session.active_food_orders)}")
        if session.active_instamart_orders:
            lines.append(f"- Active Instamart orders: {len(session.active_instamart_orders)}")
        lines += ["", _HONEST_LIMITATIONS]
        return "\n".join(lines)

    # ── Core orchestration (ReAct tool loop, chat_service.py-style) ─────────

    async def handle_message(
        self,
        message: str,
        session: ConciergeSession,
    ) -> AsyncGenerator[dict, None]:
        """Yields tagged chunks: {"type": "tool_result", "tool": ..., "data": ...}
        as each Swiggy call completes (so the frontend can render a rich
        VenueCard/SlotCard/ProductCard immediately), then {"type": "text",
        "content": ...} word-by-word for the narrated final answer."""
        try:
            intent = await self.extract_intent(message)
            self._apply_intent(session, intent)

            client, model = self._get_llm_client()
            system_prompt = self._build_system_prompt(session)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]

            full_answer = ""
            for _ in range(_MAX_TOOL_ITERATIONS):
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=CONCIERGE_TOOLS,
                    tool_choice="auto",
                    max_tokens=_MAX_TOKENS,
                    temperature=0.4,
                    stream=False,
                )
                msg = response.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None) or []

                if not tool_calls:
                    full_answer = msg.content or ""
                    break

                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                })

                for tc in tool_calls:
                    yield {"type": "status", "content": _TOOL_STATUS_LABELS.get(tc.function.name, "Working on it...")}
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}
                    result = await self._dispatch_tool(tc.function.name, args, session)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    try:
                        result_data = json.loads(result)
                    except Exception:
                        result_data = {"raw": result}
                    yield {"type": "tool_result", "tool": tc.function.name, "data": result_data}
            else:
                response = await client.chat.completions.create(
                    model=model, messages=messages, max_tokens=_MAX_TOKENS, temperature=0.4, stream=False,
                )
                full_answer = response.choices[0].message.content or ""

            for word in full_answer.split(" "):
                yield {"type": "text", "content": word + " "}

        except Exception as exc:
            log.warning("concierge_handle_message_error", error=str(exc))
            yield {"type": "text", "content": _friendly_turn_error(exc)}
        finally:
            await self.save_session(session)

    async def _dispatch_tool(self, name: str, args: dict, session: ConciergeSession) -> str:
        handler = self._dispatch.get(name)
        if handler is None:
            log.warning("concierge_unknown_tool", tool=name)
            return json.dumps({"error": _GENERIC_TOOL_ERROR})
        try:
            return await handler(args, session)
        except Exception as exc:
            log.warning("concierge_tool_error", tool=name, error=str(exc))
            return json.dumps({"error": _GENERIC_TOOL_ERROR})

    # ── Shared helpers ────────────────────────────────────────────────────────

    async def _ensure_food_address(self, session: ConciergeSession) -> Optional[str]:
        if session.address_id:
            return session.address_id
        data = await self._client.call_tool(FOOD_ENDPOINT, "get_addresses", {})
        addresses = (data or {}).get("addresses") or []
        if not addresses:
            return None
        session.address_id = str(addresses[0]["id"])
        return session.address_id

    async def _ensure_dineout_location(self, session: ConciergeSession) -> bool:
        """get_saved_locations nests its payload one level deeper than most other
        Dineout tools ({"data": {"locations": [...]}}, confirmed live -- see
        occupancy.py's _get_location for the same workaround) and never actually
        includes lat/lng fields, even though get_available_slots and
        get_restaurant_details require them. The Builders Club v1 test account
        also has zero saved Dineout locations at all (there's no "save location"
        option in Swiggy's own UI, only wishlist) -- so this always falls back to
        DEFAULT_RESTAURANT_LAT/LNG (same default already used for the weather
        signal) rather than surfacing an internal "couldn't resolve location"
        error to a guest who has no way to act on it."""
        if session.location_lat is not None and session.location_lng is not None:
            return True
        data = await self._client.call_tool(DINEOUT_ENDPOINT, "get_saved_locations", {})
        locations = ((data or {}).get("data") or {}).get("locations") or (data or {}).get("locations") or []
        first = next((loc for loc in locations if loc.get("id")), {})
        session.location_lat = float(first.get("lat") or DEFAULT_RESTAURANT_LAT)
        session.location_lng = float(first.get("lng") or DEFAULT_RESTAURANT_LNG)
        return True

    @staticmethod
    def _unwrap_list(data: dict, *keys: str) -> list[dict]:
        """Some Swiggy tools return structuredContent as {} live and instead
        wrap the real payload as {"text": "<json string>"} (confirmed pattern
        for search_products). Try each direct key first, then fall back to
        parsing the text-wrapped JSON. search_restaurants_dineout's "text"
        field is a different shape entirely (freeform natural-language lines
        for an LLM to read, not a JSON string) -- see _parse_dineout_search_text
        for that one."""
        for key in keys:
            if data.get(key):
                return data[key]
        if "text" in data:
            try:
                parsed = json.loads(data["text"])
                inner = parsed.get("data", parsed)
                for key in keys:
                    if inner.get(key):
                        return inner[key]
            except Exception:
                pass
        return []

    @staticmethod
    def _parse_dineout_search_text(text: str) -> tuple[list[dict], Optional[float], Optional[float]]:
        """Extract restaurant id/name candidates and the "Search coordinates"
        hint out of search_restaurants_dineout's freeform text response (same
        approach as occupancy.py's _parse_search_text)."""
        candidates = [
            {"id": m.group("id"), "name": m.group("name").strip()}
            for m in _DINEOUT_ID_LINE_RE.finditer(text)
        ]
        coord_m = _DINEOUT_COORD_RE.search(text)
        lat = float(coord_m.group(1)) if coord_m else None
        lng = float(coord_m.group(2)) if coord_m else None
        return candidates, lat, lng

    @staticmethod
    def _parse_price(value) -> Optional[float]:
        """render_restaurants_dineout's costForTwo (undocumented endpoint, no
        confirmed live schema anywhere in this codebase) came back as a string
        rather than a number in practice (e.g. "Rs.1,200" or "1200 for two"),
        crashing a later float multiplication with "can't multiply sequence
        by non-int of type 'float'". Strips to the first numeric run instead
        of assuming any particular type."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace(",", "")
        match = re.search(r"\d+(?:\.\d+)?", cleaned)
        return float(match.group()) if match else None

    @staticmethod
    def _stringify_list(items) -> list[str]:
        """Fields documented as plain string lists (highlights, offers, cuisines,
        amenities) come back from the real Dineout API as objects in practice
        (confirmed live -- " ".join() on the raw list throws "expected str
        instance, dict found"). Normalizes either shape to flat strings instead
        of crashing or leaking raw objects to the frontend."""
        result = []
        for item in items or []:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("title") or item.get("name")
                if text:
                    result.append(str(text))
        return result

    @staticmethod
    def _best_variant(variants: list[dict]) -> Optional[dict]:
        for v in variants:
            spin_id = v.get("spinId")
            if not spin_id:
                continue
            price_obj = v.get("price") or {}
            price = float(price_obj.get("offerPrice") or price_obj.get("mrp") or v.get("price") or 0)
            return {
                "spinId": str(spin_id),
                "price": price,
                "unit": str(v.get("quantityDescription") or v.get("unit") or ""),
                "inStock": bool(v.get("isInStockAndAvailable", v.get("inStock", True))),
            }
        return None

    # ── Dineout tool handlers ────────────────────────────────────────────────

    async def _tool_find_venues(self, args: dict, session: ConciergeSession) -> str:
        await self._ensure_dineout_location(session)

        query = args.get("query", "")
        occasion = args.get("occasion") or session.occasion
        headcount = args.get("headcount") or session.headcount
        locality = args.get("locality")

        # search_restaurants_dineout resolves locality/cuisine queries server-side
        # and returns empty structuredContent -- everything (including the
        # coordinates it resolved) lives in freeform text, requiring a second
        # render_restaurants_dineout call for real structured data (confirmed
        # live, see occupancy.py). A locality query lets Swiggy's own geocoding
        # find the guest's actual stated area instead of always using our
        # fixed default -- session.location_lat/lng get updated below once
        # resolved, so every later call in this session benefits too.
        search_query = locality or query
        entity_type = "locality" if locality else "CUISINE"

        search_data = await self._client.call_tool(
            DINEOUT_ENDPOINT, "search_restaurants_dineout",
            {"query": search_query, "entityType": entity_type, "latitude": session.location_lat, "longitude": session.location_lng},
        )
        if not search_data:
            return json.dumps({"error": "Dineout search unavailable right now.", "venues": []})

        raw_restaurants = search_data.get("restaurants")
        if raw_restaurants:
            candidates = [
                {"id": str(r.get("id") or r.get("restaurantId") or ""), "name": str(r.get("name") or "")}
                for r in raw_restaurants
            ]
            search_lat = search_lng = None
        else:
            candidates, search_lat, search_lng = self._parse_dineout_search_text(search_data.get("text", ""))

        organic = [c for c in candidates if c["id"] and "(ad)" not in c["name"].lower()]
        ids_to_render = [c["id"] for c in organic[:6]]
        if not ids_to_render:
            return json.dumps({"venues": [], "note": f"No venues found for '{search_query}'."})

        render_data = await self._client.call_tool(
            DINEOUT_ENDPOINT, "render_restaurants_dineout",
            {
                "restaurantIds": ids_to_render,
                "searches": [{
                    "query": search_query, "entityType": entity_type,
                    "latitude": search_lat or session.location_lat, "longitude": search_lng or session.location_lng,
                }],
            },
        )
        if not render_data:
            return json.dumps({"venues": [], "note": f"No venues found for '{search_query}'."})

        restaurants = render_data.get("restaurants") or []
        if not restaurants:
            return json.dumps({"venues": [], "note": f"No venues found for '{search_query}'."})

        resolved_lat = render_data.get("latitude") or search_lat
        resolved_lng = render_data.get("longitude") or search_lng
        if resolved_lat and resolved_lng:
            session.location_lat = float(resolved_lat)
            session.location_lng = float(resolved_lng)

        # Occasion-based re-ranking (reorder, never drop).
        occasion_keywords = {
            "birthday": ["private dining", "birthday", "party"],
            "anniversary": ["rooftop", "candle", "romantic", "private dining"],
            "date": ["rooftop", "candle", "romantic"],
        }
        keywords = occasion_keywords.get((occasion or "").lower(), [])

        def _score(r: dict) -> int:
            haystack = " ".join(self._stringify_list(r.get("highlights")) + self._stringify_list(r.get("offers")))
            return sum(1 for k in keywords if k in haystack.lower())

        restaurants.sort(key=_score, reverse=True)
        top = restaurants[:5]

        # Enrich top 3 with real deals/amenities.
        venues = []
        for r in top[:3]:
            details = await self._client.call_tool(
                DINEOUT_ENDPOINT, "get_restaurant_details",
                {"restaurantId": r["id"], "latitude": session.location_lat, "longitude": session.location_lng},
            )
            cost_for_two = self._parse_price(r.get("costForTwo"))
            estimated_cost = (
                round(cost_for_two * (headcount / 2), -1) if (cost_for_two and headcount) else cost_for_two
            )
            details = details or {}
            # get_restaurant_details' deals live at the top-level "offers" key,
            # not "deals" -- "deals" only exists nested inside "restaurant"
            # (confirmed live, see occupancy.py's _fetch_competitor_dineout_details).
            nested = details.get("restaurant") or {}
            venues.append({
                "restaurant_id": r["id"],
                "name": r.get("name"),
                "avg_rating": r.get("avgRating"),
                "cost_for_two": cost_for_two,
                "estimated_cost": estimated_cost,
                "distance_km": r.get("distanceKm"),
                "cuisines": self._stringify_list(r.get("cuisines")),
                "amenities": self._stringify_list(details.get("amenities")),
                "deals": details.get("offers") or nested.get("deals") or [],
            })
        for r in top[3:]:
            venues.append({
                "restaurant_id": r["id"], "name": r.get("name"), "avg_rating": r.get("avgRating"),
                "cost_for_two": self._parse_price(r.get("costForTwo")), "cuisines": self._stringify_list(r.get("cuisines")),
            })

        session.suggested_venues = venues
        return json.dumps({"venues": venues, "source": "Swiggy Dineout (live)"})

    async def _tool_get_venue_details(self, args: dict, session: ConciergeSession) -> str:
        await self._ensure_dineout_location(session)
        data = await self._client.call_tool(
            DINEOUT_ENDPOINT, "get_restaurant_details",
            {"restaurantId": args["restaurant_id"], "latitude": session.location_lat, "longitude": session.location_lng},
        )
        if not data:
            return json.dumps({"error": "Venue details unavailable right now."})
        # name/timings live nested under "restaurant", deals live at the
        # top-level "offers" key -- not top-level "name"/"timings"/"deals"
        # (confirmed live, see occupancy.py's _fetch_competitor_dineout_details).
        nested = data.get("restaurant") or {}
        return json.dumps({
            "name": nested.get("name") or data.get("name") or args.get("restaurant_name"),
            "avg_rating": nested.get("avgRating") or data.get("avgRating"),
            "timings": nested.get("timings") or data.get("timings"),
            "address": nested.get("address") or data.get("address"),
            "deals": data.get("offers") or nested.get("deals") or [],
            "amenities": self._stringify_list(data.get("amenities")),
        })

    async def _tool_check_table_availability(self, args: dict, session: ConciergeSession) -> str:
        await self._ensure_dineout_location(session)

        target_date = args.get("date") or _default_saturday()
        headcount = args.get("headcount") or session.headcount

        data = await self._client.call_tool(
            DINEOUT_ENDPOINT, "get_available_slots",
            {
                "restaurantId": args["restaurant_id"], "date": target_date,
                "latitude": session.location_lat, "longitude": session.location_lng,
            },
        )
        if not data:
            return json.dumps({"error": "Slot availability unavailable right now.", "slots": []})

        # get_available_slots' response spans many days regardless of the
        # "date" argument (confirmed live, see occupancy.py's _fetch_slot_counts),
        # so this filters to the requested date explicitly rather than mixing
        # in slots from other days.
        raw_slots = (data.get("_meta") or {}).get("slots") or data.get("slots") or []
        slots = []
        for s in raw_slots:
            if s.get("dateStr") and s.get("dateStr") != target_date:
                continue
            free_deals = [d for d in (s.get("deals") or []) if d.get("isFree")]
            if not free_deals:
                continue
            slots.append({
                "display_time": s.get("displayTime"),
                "reservation_time": s.get("reservationTime"),
                "availability_count": s.get("availabilityCount"),
                "slot_id": free_deals[0].get("slotId"),
                "item_id": free_deals[0].get("itemId"),
                "deal_title": free_deals[0].get("title"),
            })

        result = {"date": target_date, "slots": slots, "restaurant_id": args["restaurant_id"], "restaurant_name": args.get("restaurant_name")}
        if headcount and headcount >= 14:
            result["note"] = "For groups of 14 or more, slot availability shown here may not reflect real capacity. Worth calling the venue directly to confirm."
        if not slots:
            result["note"] = result.get("note", "") + " No free-reservation slots found for this date."
        return json.dumps(result)

    async def _tool_book_table(self, args: dict, session: ConciergeSession) -> str:
        booking = {
            "restaurant_id": args.get("restaurant_id"),
            "restaurant_name": args.get("restaurant_name"),
            "display_time": args.get("display_time"),
            "reservation_time": args.get("reservation_time"),
            "headcount": args.get("headcount"),
            "estimated_cost": args.get("estimated_cost"),
        }

        if _staging_enabled():
            await self._ensure_dineout_location(session)
            cart = await self._client.call_tool(
                DINEOUT_ENDPOINT, "create_cart",
                {
                    "restaurantId": args["restaurant_id"], "cartType": "DEAL_TICKET_PURCHASE",
                    "latitude": session.location_lat, "longitude": session.location_lng,
                    "slotId": args["slot_id"], "itemId": args["item_id"],
                    "reservationTime": args["reservation_time"], "guestCount": args["headcount"],
                },
            )
            result = await self._client.call_tool(
                DINEOUT_ENDPOINT, "book_table",
                {
                    "restaurantId": args["restaurant_id"], "slotId": args["slot_id"], "itemId": args["item_id"],
                    "reservationTime": args["reservation_time"], "guestCount": args["headcount"],
                    "latitude": session.location_lat, "longitude": session.location_lng,
                },
            )
            if result:
                booking["status"] = result.get("status", "confirmed")
                booking["order_id"] = result.get("orderId")
                booking["confirmation_code"] = result.get("confirmationCode")
            else:
                # 5xx / failure -- check-then-retry pattern per CLAUDE.md's non-idempotent rule.
                status_check = await self._client.call_tool(
                    DINEOUT_ENDPOINT, "get_booking_status", {"orderId": booking.get("order_id", "")},
                )
                booking["status"] = (status_check or {}).get("status", "pending_confirmation")
        else:
            booking["status"] = "pending_staging"

        session.active_bookings.append(booking)
        if args.get("estimated_cost"):
            session.budget_spent += float(args["estimated_cost"])

        return json.dumps({"booking": booking, "staging_enabled": _staging_enabled()})

    async def _tool_check_my_bookings(self, args: dict, session: ConciergeSession) -> str:
        return json.dumps({"bookings": session.active_bookings})

    # ── Food tool handlers ───────────────────────────────────────────────────

    async def _tool_find_food(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})
        data = await self._client.call_tool(
            FOOD_ENDPOINT, "search_restaurants", {"addressId": address_id, "query": args.get("query", "")},
        )
        if not data:
            return json.dumps({"error": "Food search unavailable right now.", "restaurants": []})
        restaurants = self._unwrap_list(data, "restaurants")
        open_only = [r for r in restaurants if r.get("availabilityStatus", "OPEN") == "OPEN"][:5]
        return json.dumps({
            "restaurants": [
                {
                    "restaurant_id": r["id"], "name": r.get("name"), "avg_rating": r.get("avgRating"),
                    "cost_for_two": self._parse_price(r.get("costForTwo")), "delivery_time": r.get("deliveryTime"),
                    "cuisines": self._stringify_list(r.get("cuisines")),
                }
                for r in open_only
            ],
        })

    async def _tool_browse_menu(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})
        data = await self._client.call_tool(
            FOOD_ENDPOINT, "get_restaurant_menu",
            {"addressId": address_id, "restaurantId": args["restaurant_id"], "page": args.get("page", 1)},
        )
        if not data:
            return json.dumps({"error": "Menu unavailable right now."})

        # A full menu response can run to hundreds of items across many
        # categories -- unbounded, this both blows past the LLM's context
        # (the same rate-limit failure mode found earlier in the operator
        # chatbot's Instamart tool) and forces the model to narrate the whole
        # thing as prose instead of the frontend rendering it as cards. Trim
        # to a small, genuinely useful slice before it ever reaches the model.
        raw_categories = data.get("categories") or data.get("menu") or []
        trimmed = []
        for category in raw_categories[:_MAX_MENU_CATEGORIES]:
            items = []
            for item in (category.get("items") or [])[:_MAX_MENU_ITEMS_PER_CATEGORY]:
                name = item.get("name")
                price = item.get("price") or item.get("defaultPrice") or 0
                if not name or not price:
                    continue
                items.append({
                    "item_id": str(item.get("id") or ""), "name": name, "price": price,
                    "veg": item.get("isVeg"),
                })
            if items:
                trimmed.append({"category": category.get("name") or category.get("categoryName") or "Menu", "items": items})

        return json.dumps({
            "restaurant_id": args.get("restaurant_id"),
            "restaurant_name": args.get("restaurant_name"),
            "categories": trimmed,
        })

    async def _tool_add_food_to_cart(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})
        cart_items = [{"itemId": i["item_id"], "quantity": i.get("quantity", 1)} for i in args.get("items", [])]
        result = await self._client.call_tool(
            FOOD_ENDPOINT, "update_food_cart",
            {"restaurantId": args["restaurant_id"], "cartItems": cart_items, "addressId": address_id},
        )
        if not result:
            return json.dumps({"error": "Could not update the food cart right now."})
        cart = await self._client.call_tool(FOOD_ENDPOINT, "get_food_cart", {"addressId": address_id})
        bill = (cart or {}).get("bill") or {}
        response = {"cart": (cart or {}).get("items") or [], "bill": bill}
        if bill.get("total", 0) > _FOOD_ORDER_CAP_INR * 0.8:
            response["warning"] = f"Cart total is approaching the Rs.{_FOOD_ORDER_CAP_INR:.0f} per-order cap."
        return json.dumps(response)

    async def _tool_view_food_cart(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})
        cart = await self._client.call_tool(FOOD_ENDPOINT, "get_food_cart", {"addressId": address_id})
        if not cart:
            return json.dumps({"error": "Cart unavailable right now."})
        return json.dumps({"items": cart.get("items") or [], "bill": cart.get("bill") or {}})

    async def _tool_apply_best_coupon(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})
        coupons_data = await self._client.call_tool(
            FOOD_ENDPOINT, "fetch_food_coupons", {"restaurantId": args["restaurant_id"], "addressId": address_id},
        )
        if not coupons_data:
            return json.dumps({"error": "No coupon data available right now."})
        all_coupons = (coupons_data.get("bestCoupons") or []) + (coupons_data.get("moreOffers") or [])
        cod_coupons = [c for c in all_coupons if not c.get("requiresOnlinePayment", False)]
        if not cod_coupons:
            return json.dumps({"note": "No Cash-on-Delivery-compatible coupons available right now."})
        best = max(cod_coupons, key=lambda c: c.get("discountAmount") or c.get("discountPercentage") or 0)
        applied = await self._client.call_tool(
            FOOD_ENDPOINT, "apply_food_coupon", {"couponCode": best["code"], "addressId": address_id},
        )
        cart = await self._client.call_tool(FOOD_ENDPOINT, "get_food_cart", {"addressId": address_id})
        return json.dumps({
            "applied_coupon": best,
            "applied": bool(applied),
            "bill": (cart or {}).get("bill") or {},
        })

    async def _tool_place_food_order(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})
        cart = await self._client.call_tool(FOOD_ENDPOINT, "get_food_cart", {"addressId": address_id})
        bill = (cart or {}).get("bill") or {}
        total = bill.get("total", 0)
        if total > _FOOD_ORDER_CAP_INR:
            return json.dumps({
                "error": f"Cart total Rs.{total:.0f} exceeds the Rs.{_FOOD_ORDER_CAP_INR:.0f} per-order cap "
                         "(Builders Club v1, COD only). Split this into multiple smaller orders.",
            })
        result = await self._client.call_tool(FOOD_ENDPOINT, "place_food_order", {"addressId": address_id})
        if not result:
            return json.dumps({"error": "Could not place the order right now."})
        order = {"order_id": result.get("orderId"), "status": result.get("status"), "estimated_delivery": result.get("estimatedDelivery"), "total": total}
        session.active_food_orders.append(order)
        session.budget_spent += total
        return json.dumps({"order": order})

    async def _tool_track_food_order(self, args: dict, session: ConciergeSession) -> str:
        result = await self._client.call_tool(
            FOOD_ENDPOINT, "track_food_order", {"orderId": args["order_id"]} if args.get("order_id") else {},
        )
        if not result:
            return json.dumps({"error": "Tracking unavailable right now."})
        return json.dumps(result)

    async def _tool_view_past_orders(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})
        result = await self._client.call_tool(
            FOOD_ENDPOINT, "get_food_orders", {"addressId": address_id, "orderCount": args.get("count", 5)},
        )
        if not result:
            return json.dumps({"error": "Order history unavailable right now.", "orders": []})
        return json.dumps({"orders": result.get("orders") or []})

    # ── Instamart tool handlers ──────────────────────────────────────────────

    async def _tool_find_supplies(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)  # get_addresses is shared across Food+Instamart
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})

        items = list(args.get("items") or [])[:_MAX_SUPPLY_SEARCHES]
        found, not_found = [], []
        for item in items:
            data = await self._client.call_tool(
                INSTAMART_ENDPOINT, "search_products", {"addressId": address_id, "query": item},
            )
            products = self._unwrap_list(data or {}, "products") if data else []
            if not products:
                not_found.append(item)
                continue
            variant = self._best_variant(products[0].get("variants") or products[0].get("variations") or [])
            if not variant:
                not_found.append(item)
                continue
            found.append({
                "query": item,
                "name": products[0].get("name") or products[0].get("displayName"),
                "spin_id": variant["spinId"],
                "price": variant["price"],
                "unit": variant["unit"],
                "in_stock": variant["inStock"],
            })

        result = {"found": found, "source": "Swiggy Instamart (live)"}
        if not_found:
            result["not_found"] = not_found
            result["not_found_note"] = "Not available on Instamart. Try Amazon or Meesho for these."
        return json.dumps(result)

    async def _tool_add_supplies_to_cart(self, args: dict, session: ConciergeSession) -> str:
        address_id = await self._ensure_food_address(session)
        if not address_id:
            return json.dumps({"error": "Could not resolve a delivery address."})

        # update_cart REPLACES the whole cart -- merge new items into whatever
        # was already added this session rather than dropping earlier items.
        by_spin = {i["spin_id"]: i for i in session.instamart_cart}
        for item in args.get("items", []):
            by_spin[item["spin_id"]] = {
                "spin_id": item["spin_id"], "name": item.get("name"),
                "quantity": item.get("quantity", 1), "price": item.get("price"),
            }
        merged = list(by_spin.values())

        result = await self._client.call_tool(
            INSTAMART_ENDPOINT, "update_cart",
            {"selectedAddressId": address_id, "items": [{"spinId": i["spin_id"], "quantity": i["quantity"]} for i in merged]},
        )
        if not result:
            return json.dumps({"error": "Could not update the Instamart cart right now."})

        cart = await self._client.call_tool(INSTAMART_ENDPOINT, "get_cart", {})
        session.instamart_cart = merged
        return json.dumps({"cart": (cart or {}).get("items") or merged, "bill": (cart or {}).get("bill") or {}})

    async def _tool_view_supplies_cart(self, args: dict, session: ConciergeSession) -> str:
        cart = await self._client.call_tool(INSTAMART_ENDPOINT, "get_cart", {})
        if not cart:
            return json.dumps({"cart": session.instamart_cart, "note": "Live cart unavailable, showing last known items."})
        return json.dumps({"items": cart.get("items") or [], "bill": cart.get("bill") or {}, "payment_methods": cart.get("availablePaymentMethods") or []})

    async def _tool_order_supplies(self, args: dict, session: ConciergeSession) -> str:
        cart = await self._client.call_tool(INSTAMART_ENDPOINT, "get_cart", {})
        bill = (cart or {}).get("bill") or {}
        total = bill.get("total", 0)

        if _staging_enabled():
            address_id = await self._ensure_food_address(session)
            payment_methods = (cart or {}).get("availablePaymentMethods") or ["COD"]
            result = await self._client.call_tool(
                INSTAMART_ENDPOINT, "checkout", {"addressId": address_id, "paymentMethod": payment_methods[0]},
            )
            if not result:
                orders = await self._client.call_tool(INSTAMART_ENDPOINT, "get_orders", {"activeOnly": True})
                return json.dumps({"error": "Checkout is being verified, check get_orders shortly.", "recent_orders": (orders or {}).get("orders") or []})
            order = {"order_id": result.get("orderId"), "status": result.get("status"), "estimated_delivery": result.get("estimatedDelivery"), "total": result.get("total", total)}
        else:
            order = {"status": "pending_staging", "items": cart.get("items") if cart else session.instamart_cart, "total": total, "estimated_delivery_mins": "15-25"}

        session.active_instamart_orders.append(order)
        session.budget_spent += total
        return json.dumps({"order": order, "staging_enabled": _staging_enabled()})

    async def _tool_track_supplies_delivery(self, args: dict, session: ConciergeSession) -> str:
        order_id = args["order_id"]
        orders_data = await self._client.call_tool(INSTAMART_ENDPOINT, "get_orders", {"count": 20})
        matching = next((o for o in (orders_data or {}).get("orders", []) if o.get("orderId") == order_id), None)
        if not matching:
            return json.dumps({"error": "Could not find that order to track."})
        addr = matching.get("deliveryAddress") or {}
        result = await self._client.call_tool(
            INSTAMART_ENDPOINT, "track_order", {"orderId": order_id, "lat": addr.get("lat"), "lng": addr.get("lng")},
        )
        if not result:
            return json.dumps({"error": "Tracking unavailable right now."})
        return json.dumps(result)

    # ── Planning tool handlers ───────────────────────────────────────────────

    async def _tool_get_budget_summary(self, args: dict, session: ConciergeSession) -> str:
        venue_estimate = sum(b.get("estimated_cost") or 0 for b in session.active_bookings)
        food_spent = sum(o.get("total") or 0 for o in session.active_food_orders)
        supplies_spent = sum(o.get("total") or 0 for o in session.active_instamart_orders)
        return json.dumps({
            "budget_inr": session.budget_inr,
            "spent_total": session.budget_spent,
            "remaining": session.budget_remaining,
            "breakdown": {"venue_estimate": venue_estimate, "food": food_spent, "supplies": supplies_spent},
        })

    async def _tool_track_everything(self, args: dict, session: ConciergeSession) -> str:
        return json.dumps({
            "bookings": session.active_bookings,
            "food_orders": session.active_food_orders,
            "instamart_orders": session.active_instamart_orders,
        })

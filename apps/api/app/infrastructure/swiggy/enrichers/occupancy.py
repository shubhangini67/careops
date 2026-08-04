"""OccupancyEnricher — P6-S08.

Fetches live area Dineout slot availability at planning time and injects an
occupancy signal into the reservation node prompt. Area aggregates only
(P6-A20) -- no restaurant is individually named or attributed a specific
deal/occupancy figure in anything this class returns.

Flow:
  get_saved_locations() → location id (lat/lng resolved separately, see below)
  → search_restaurants_dineout(cuisine) → candidate restaurant ids (parsed from
    text -- see _get_competitors)
  → render_restaurants_dineout(ids) → structured restaurant data + precise lat/lng
  → get_available_slots(restaurantId, tonight) for up to MAX_SLOT_CALLS
  → compute HIGH/MEDIUM/LOW occupancy signal from how many dinner-hour times are
    still listed as bookable tonight (see _fetch_slot_counts)
  → cache Redis 30 min (key: enricher:occupancy:{org_id}:{date})
  → return dict or None on any failure

Three live-confirmed Dineout response-shape quirks this file works around
(none of this is Food MCP's behavior, which returns real structuredContent
directly):
  - get_saved_locations nests its payload one level deeper than expected
    ({"data": {"locations": [...]}}) and never includes lat/lng at all.
  - search_restaurants_dineout returns EMPTY structuredContent ({}) -- all
    data is in freeform text meant for an LLM to read, which explicitly
    instructs calling render_restaurants_dineout with the ids it lists next.
    A genuine two-step agentic flow, not a single structured call.
  - get_available_slots' slots live in the JSON-RPC result's _meta.slots, not
    structuredContent, and carry no numeric availabilityCount field anymore --
    only displayTime/slotGroupName/dateStr/deals[]. The occupancy signal here
    is a proxy: how many of a possible 6 dinner-hour times (19:00-21:30, 30-min
    steps) are still listed as bookable tonight, per restaurant. Fewer listed
    times reads as busier, same direction as the old availabilityCount logic.

IMPORTANT: Dineout uses lat/lng, not Food/Instamart's addressId.
"""

import json
import re
from datetime import date
from typing import Optional

import redis.asyncio as aioredis
import structlog

from app.core.constants import DEFAULT_RESTAURANT_LAT, DEFAULT_RESTAURANT_LNG
from app.core.settings import get_settings
from app.infrastructure.swiggy.client import DINEOUT_ENDPOINT, SwiggyMCPClient

# structlog, not stdlib logging — see procurement.py for why.
log = structlog.get_logger()

_CACHE_TTL        = 1800  # 30 minutes
_MAX_SLOT_CALLS   = 3     # hard rate-limit per planning run
_MAX_RENDER_IDS   = 6     # small bounded batch sent to render_restaurants_dineout
_DINNER_HOURS     = {"19:00", "19:30", "20:00", "20:30", "21:00", "21:30"}  # hhmm 24h
_MAX_DINNER_SLOTS = len(_DINNER_HOURS)
_HIGH_THRESHOLD   = 2     # avg dinner-hour times still open <= this → HIGH occupancy
_LOW_THRESHOLD    = 4     # avg dinner-hour times still open > this → LOW occupancy
_MAX_DETAIL_CALLS = 3     # hard rate-limit: max get_restaurant_details calls per run (P6-MI07)

# search_restaurants_dineout's text lines look like:
# "17. Ashz Cafe — Italian, North Indian | [object Object]★ | ₹500 for two | Kopar Khairane (ID: 662725)"
_ID_LINE_RE = re.compile(r'^\d+\.\s+(?P<name>.+?)\s+—.*\(ID:\s*(?P<id>\d+)\)', re.MULTILINE)
_COORD_RE   = re.compile(r'latitude=([\d.]+),\s*longitude=([\d.]+)')


class OccupancyEnricher:
    """Live area occupancy signal from Swiggy Dineout MCP.

    Returns None on any failure so reservation node runs without it.
    """

    def __init__(self, client: SwiggyMCPClient) -> None:
        self._client = client
        self._redis: Optional[aioredis.Redis] = None

    # ── public ──────────────────────────────────────────────────────────────

    async def enrich(self, context: dict) -> Optional[dict]:
        """Return live occupancy context or None on any failure.

        context keys used:
          org_id    int  — cache scoping
          cuisine   str  — e.g. "North Indian" (default "restaurant")

        Returns:
          {
            "occupancy_signal": "HIGH" | "MEDIUM" | "LOW",
            "tonight_busy":     bool,
            "competitors_checked": int,
            "avg_availability_count": float,
            "dineout_deals_count": int,          # area aggregate, no restaurant named
            "dineout_deals_summary": str,
            "slot_deals_found": [...],            # already time-keyed, not restaurant-named
            "prompt_text": "## Occupancy Signal\\n...",
            "fetched_at": "2026-06-30",
          }
          or None.
        """
        try:
            return await self._enrich(context)
        except Exception as exc:
            log.warning("occupancy_enricher_error", error=str(exc))
            return None

    # ── internal ─────────────────────────────────────────────────────────────

    async def _enrich(self, context: dict) -> Optional[dict]:
        org_id  = int(context.get("org_id") or 0)
        cuisine = str(context.get("cuisine") or "restaurant")
        today   = date.today().isoformat()

        cache_key = f"enricher:occupancy:{org_id}:{today}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            log.info("occupancy_enricher_cache_hit", cache_key=cache_key)
            return cached

        # Step 1 — resolve a Dineout location id (fallback lat/lng, refined in step 2)
        location = await self._get_location()
        if not location:
            return None

        lat = location["lat"]
        lng = location["lng"]
        loc_id = location["id"]

        # Step 2 — find nearby available competitors (search + render two-step flow).
        # Prefers the precise "Search coordinates" Dineout itself resolved for this
        # query over the location fallback above, when available.
        competitors, search_lat, search_lng = await self._get_competitors(cuisine, loc_id)
        if not competitors:
            return None
        lat = search_lat or lat
        lng = search_lng or lng

        # Step 3 — get tonight's slot availability for up to MAX_SLOT_CALLS
        open_slot_counts, all_slots = await self._fetch_slot_counts(competitors, today, lat, lng)
        if not open_slot_counts:
            return None

        # Step 4 — compute signal
        avg_count = sum(open_slot_counts) / len(open_slot_counts)
        signal    = self._compute_signal(avg_count)

        # Step 5 — Dineout deals (P6-MI07)
        # PART A: get_restaurant_details for amenities + deals (extra API calls, capped).
        # Raw list is named-restaurant + deal detail -- reduced to a count + area summary
        # before it reaches the result dict; the raw list itself is never returned.
        dineout_deals_raw = await self._fetch_competitor_dineout_details(competitors, lat, lng)
        # PART B: deals[] parsed from the slots we already fetched — zero extra calls.
        # Already time-keyed, not restaurant-named, so this stays as a raw list.
        slot_deals = self._extract_slot_deals(all_slots)
        dineout_deals_count, dineout_deals_summary = self._summarize_dineout_deals(dineout_deals_raw)
        # Occupancy-by-time-slot chart data — also zero extra calls, same dinner_slots reused.
        slot_availability_by_time = self._aggregate_slot_availability_by_time(all_slots, len(open_slot_counts))

        result = {
            "occupancy_signal":            signal,
            "tonight_busy":                signal == "HIGH",
            "competitors_checked":         len(open_slot_counts),
            "avg_availability_count":      round(avg_count, 2),
            "dineout_deals_count":         dineout_deals_count,
            "dineout_deals_summary":       dineout_deals_summary,
            "slot_deals_found":            slot_deals,
            "slot_availability_by_time":   slot_availability_by_time,
            "prompt_text": self._build_prompt(
                signal, len(open_slot_counts), avg_count, dineout_deals_count,
                dineout_deals_summary, slot_deals, slot_availability_by_time,
            ),
            "fetched_at":                today,
        }

        await self._cache_set(cache_key, result)
        log.info(
            "occupancy_enricher_done",
            signal=signal, competitors=len(open_slot_counts), avg_slots=round(avg_count, 1),
            dineout_deals=dineout_deals_count, slot_deals=len(slot_deals),
        )
        return result

    async def _get_location(self) -> Optional[dict]:
        """Call get_saved_locations and return the first usable location.

        get_saved_locations nests its payload one level deeper than most other
        Dineout tools -- structuredContent is {"data": {"locations": [...]}},
        not {"locations": [...]} directly (confirmed live) -- so this reads
        data["data"]["locations"], falling back to a top-level "locations" key
        in case a future response shape drops the wrapper.

        Swiggy's response also does not actually include lat/lng fields
        (confirmed live -- only id/addressLine/phoneNumber/addressCategory/
        addressTag come back), even though get_available_slots and
        get_restaurant_details require latitude/longitude. Falls back to
        DEFAULT_RESTAURANT_LAT/LNG (the same address, already used for the
        weather signal) for any saved location that has an id but no lat/lng,
        rather than treating "no lat/lng in the response" as "no saved location."
        """
        data = await self._client.call_tool(DINEOUT_ENDPOINT, "get_saved_locations", {})
        if not data:
            return None
        locations = (data.get("data") or {}).get("locations") or data.get("locations") or []
        for loc in locations:
            if not loc.get("id"):
                continue
            lat = loc.get("lat") or DEFAULT_RESTAURANT_LAT
            lng = loc.get("lng") or DEFAULT_RESTAURANT_LNG
            return {"id": str(loc["id"]), "lat": float(lat), "lng": float(lng)}
        return None

    async def _get_competitors(
        self, cuisine: str, location_id: str
    ) -> tuple[list[dict], Optional[float], Optional[float]]:
        """Search for nearby Dineout restaurants by cuisine, then resolve them to
        structured data via render_restaurants_dineout.

        search_restaurants_dineout returns empty structuredContent (confirmed
        live) -- restaurant ids/names only exist in its freeform text, which
        explicitly instructs calling render_restaurants_dineout with the ids it
        lists next ("Do NOT call search_restaurants_dineout again"). Parses ids/
        names and the "Search coordinates" hint out of that text, filters
        sponsored/ad placements the same way CompetitorEnricher does for Food
        MCP, then renders a small bounded batch to get real structured data
        (rating, costForTwo, offers) plus the precise lat/lng Dineout resolved
        for this query -- more accurate than any address-level fallback.

        Returns (restaurants, lat, lng) -- lat/lng are None if unresolvable,
        in which case the caller falls back to _get_location()'s coordinates.
        """
        search_data = await self._client.call_tool(
            DINEOUT_ENDPOINT,
            "search_restaurants_dineout",
            {"query": cuisine, "addressId": location_id, "entityType": "CUISINE"},
        )
        if not search_data:
            return [], None, None

        # Some accounts/tool versions may return structuredContent directly --
        # handle that shape too rather than assuming text is the only path.
        raw_restaurants = search_data.get("restaurants")
        if raw_restaurants:
            candidates = [
                {"id": str(r.get("id") or r.get("restaurantId") or ""), "name": str(r.get("name") or "")}
                for r in raw_restaurants
            ]
            lat = lng = None
        else:
            candidates, lat, lng = self._parse_search_text(search_data.get("text", ""))

        organic = [c for c in candidates if c["id"] and not self._is_sponsored(c["name"])]
        ids_to_render = [c["id"] for c in organic[:_MAX_RENDER_IDS]]
        if not ids_to_render:
            return [], lat, lng

        render_data = await self._client.call_tool(
            DINEOUT_ENDPOINT,
            "render_restaurants_dineout",
            {
                "restaurantIds": ids_to_render,
                "searches": [{"query": cuisine, "latitude": lat, "longitude": lng, "entityType": "CUISINE"}],
            },
        )
        if not render_data:
            return [], lat, lng

        restaurants = (render_data.get("restaurants") or [])[:_MAX_SLOT_CALLS]
        # render's own returned coordinates are authoritative when present.
        lat = render_data.get("latitude", lat)
        lng = render_data.get("longitude", lng)
        return restaurants, lat, lng

    def _parse_search_text(self, text: str) -> tuple[list[dict], Optional[float], Optional[float]]:
        """Extract restaurant id/name pairs and the "Search coordinates" hint
        out of search_restaurants_dineout's freeform text response."""
        candidates = [
            {"id": m.group("id"), "name": m.group("name").strip()}
            for m in _ID_LINE_RE.finditer(text)
        ]
        coord_m = _COORD_RE.search(text)
        lat = float(coord_m.group(1)) if coord_m else None
        lng = float(coord_m.group(2)) if coord_m else None
        return candidates, lat, lng

    def _is_sponsored(self, name: Optional[str]) -> bool:
        """True if a restaurant name is tagged as a sponsored/ad placement."""
        return bool(name) and "(ad)" in str(name).lower()

    async def _fetch_slot_counts(
        self, competitors: list[dict], tonight: str, lat: float, lng: float
    ) -> tuple[list[int], list[dict]]:
        """Fetch tonight's dinner-hour slot availability for each competitor.

        get_available_slots' slots live in the JSON-RPC result's _meta.slots,
        not structuredContent (confirmed live -- client.py's call_tool() merges
        _meta into whatever it returns), and no longer carry a numeric
        availabilityCount field. The response also spans many days regardless
        of the "date" argument, so this filters to tonight's dateStr explicitly.

        Proxy signal: how many of a possible _MAX_DINNER_SLOTS dinner-hour times
        are still listed as bookable for tonight, per restaurant -- fewer listed
        times reads as busier, same direction the old availabilityCount logic
        used (lower value = more occupied).

        Returns (open_slot_counts, dinner_slots): open_slot_counts has one entry
        per restaurant successfully queried (0-_MAX_DINNER_SLOTS), even if 0 --
        a restaurant with no tonight dinner slots listed is a real "fully
        booked" data point, not a failure. dinner_slots is the flat list of
        matching slot dicts across all restaurants, kept so
        _extract_slot_deals()/_aggregate_slot_availability_by_time() can parse
        deals/time-buckets without any extra API calls.
        """
        open_slot_counts: list[int] = []
        dinner_slots: list[dict] = []
        queried = 0

        for restaurant in competitors:
            if queried >= _MAX_SLOT_CALLS:
                break
            r_id = restaurant.get("id") or restaurant.get("restaurantId")
            if not r_id:
                continue

            data = await self._client.call_tool(
                DINEOUT_ENDPOINT,
                "get_available_slots",
                {
                    "restaurantId": str(r_id),
                    "date":         tonight,
                    "latitude":     lat,
                    "longitude":    lng,
                },
            )
            queried += 1

            if not data:
                continue

            slots = (data.get("_meta") or {}).get("slots") or data.get("slots") or []
            tonight_dinner_slots = [
                s for s in slots
                if s.get("dateStr") == tonight and self._is_dinner_slot(s.get("displayTime") or "")
            ]
            open_slot_counts.append(len(tonight_dinner_slots))
            dinner_slots.extend(tonight_dinner_slots)

        return open_slot_counts, dinner_slots

    async def _fetch_competitor_dineout_details(
        self, competitors: list[dict], lat: float, lng: float
    ) -> list[dict]:
        """Call get_restaurant_details for each competitor to get deals + amenities.

        Deals live at the top-level "offers" key (not "deals" -- confirmed
        live; "deals" only exists nested inside "restaurant"). name/timings
        are likewise nested under "restaurant", not top-level.

        Capped at MAX_DETAIL_CALLS — separate rate limit from the slot-count calls.
        """
        details = []

        for restaurant in competitors[:_MAX_DETAIL_CALLS]:
            r_id = restaurant.get("id") or restaurant.get("restaurantId")
            if not r_id:
                continue

            data = await self._client.call_tool(
                DINEOUT_ENDPOINT,
                "get_restaurant_details",
                {
                    "restaurantId": str(r_id),
                    "latitude":     lat,
                    "longitude":    lng,
                },
            )
            if not data:
                continue

            nested = data.get("restaurant") or {}
            restaurant_deals = []
            for deal in data.get("offers") or nested.get("deals") or []:
                discount = deal.get("discountPercentage") or 0
                if discount > 0 or deal.get("isFree"):
                    restaurant_deals.append({
                        "title":        str(deal.get("title") or ""),
                        "discount_pct": discount,
                        "is_free":      bool(deal.get("isFree")),
                    })

            if not restaurant_deals:
                continue

            details.append({
                "name":      str(nested.get("name") or restaurant.get("name") or ""),
                "deals":     restaurant_deals,
                "amenities": data.get("amenities") or [],
                "timings":   str(nested.get("timings") or ""),
            })

        return details

    def _summarize_dineout_deals(self, dineout_deals_raw: list[dict]) -> tuple[int, str]:
        """Reduce the raw named-restaurant deal list to a count + area-level summary --
        never a named restaurant paired with its specific deal.
        """
        count = len(dineout_deals_raw)
        if count == 0:
            return 0, "No active Dineout deals detected among nearby restaurants right now."
        return count, f"{count} nearby restaurant{'s' if count != 1 else ''} have active Dineout deals tonight."

    def _extract_slot_deals(self, slots: list[dict]) -> list[dict]:
        """Parse deals[] from already-fetched get_available_slots dinner slots.

        Zero extra API calls — this is data _fetch_slot_counts already retrieved.
        """
        slot_deals = []
        for slot in slots:
            for deal in slot.get("deals") or []:
                discount = deal.get("discountPercentage") or 0
                if discount > 0:
                    slot_deals.append({
                        "time":         slot.get("displayTime", ""),
                        "deal_title":   str(deal.get("title") or ""),
                        "discount_pct": discount,
                        "is_free":      bool(deal.get("isFree")),
                    })
        return slot_deals

    def _aggregate_slot_availability_by_time(
        self, slots: list[dict], total_restaurants: int
    ) -> list[dict]:
        """Group already-fetched dinner slots by displayTime, counting how many of
        the checked competitors still list that time as bookable tonight. Zero
        extra API calls — same dinner_slots data _fetch_slot_counts() already
        retrieved, just not collapsed into one number.

        No availabilityCount field exists in the live API (confirmed) -- this
        counts presence/absence of a listed time slot per restaurant instead,
        same direction as the main signal: fewer restaurants offering a given
        time reads as busier at that time.

        Powers the occupancy-by-time-slot chart: shows WHEN tonight gets tightest,
        not just an aggregate HIGH/MEDIUM/LOW badge.
        """
        by_time: dict[str, int] = {}
        for slot in slots:
            time_label = slot.get("displayTime") or ""
            if not time_label:
                continue
            by_time[time_label] = by_time.get(time_label, 0) + 1

        results = []
        for time_label, open_count in by_time.items():
            results.append({
                "time":             time_label,
                "avg_availability": float(open_count),
                "signal":           self._compute_time_bucket_signal(open_count, total_restaurants),
            })

        results.sort(key=self._minutes_since_midnight)
        return results

    def _compute_time_bucket_signal(self, open_count: int, total_restaurants: int) -> str:
        """Fraction-based signal for a single time bucket -- open_count/total_restaurants
        is comparable regardless of how many competitors were actually checked."""
        if total_restaurants <= 0:
            return "MEDIUM"
        ratio = open_count / total_restaurants
        if ratio <= 0.34:
            return "HIGH"
        if ratio <= 0.67:
            return "MEDIUM"
        return "LOW"

    def _minutes_since_midnight(self, entry: dict) -> int:
        """Sort key: parse a 12h displayTime like '7:30 PM' into minutes since midnight."""
        try:
            parts = entry["time"].lower().replace(".", "").strip().split()
            time_part, meridiem = parts[0], parts[1]
            hh, mm = (int(x) for x in time_part.split(":"))
            if meridiem == "pm" and hh != 12:
                hh += 12
            return hh * 60 + mm
        except Exception:
            return 9999

    def _is_dinner_slot(self, display_time: str) -> bool:
        """Check if a slot displayTime falls in dinner service hours."""
        try:
            parts = display_time.lower().replace(".", "").strip().split()
            if len(parts) < 2:
                return False
            time_part, meridiem = parts[0], parts[1]
            hh, mm = (int(x) for x in time_part.split(":"))
            if meridiem == "pm" and hh != 12:
                hh += 12
            hhmm = f"{hh:02d}:{mm:02d}"
            return hhmm in _DINNER_HOURS
        except Exception:
            return False

    def _compute_signal(self, avg_count: float) -> str:
        """avg_count is the avg number of dinner-hour times (of a possible
        _MAX_DINNER_SLOTS) still listed as bookable tonight, across checked
        competitors -- fewer open times = busier, same direction as the old
        availabilityCount-based logic this replaced."""
        if avg_count <= _HIGH_THRESHOLD:
            return "HIGH"
        if avg_count <= _LOW_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    def _build_prompt(
        self,
        signal: str,
        competitors: int,
        avg_count: float,
        dineout_deals_count: int = 0,
        dineout_deals_summary: str = "",
        slot_deals: Optional[list[dict]] = None,
        slot_availability_by_time: Optional[list[dict]] = None,
    ) -> str:
        slot_deals = slot_deals or []
        slot_availability_by_time = slot_availability_by_time or []

        signal_desc = {
            "HIGH":   "Most nearby restaurants are nearly full tonight.",
            "MEDIUM": "Nearby restaurants have moderate availability tonight.",
            "LOW":    "Nearby restaurants have ample availability tonight.",
        }[signal]

        lines = [
            "## Occupancy Signal",
            f"Area tonight: **{signal}** (based on {competitors} nearby Dineout restaurant(s), "
            f"avg {avg_count:.1f} of {_MAX_DINNER_SLOTS} dinner-hour times still bookable).",
            signal_desc,
        ]
        if signal == "HIGH":
            lines.append(
                "Recommendation: consider opening additional Dineout slots "
                "or increasing walk-in capacity for tonight."
            )

        if len(slot_availability_by_time) >= 2:
            tightest = min(slot_availability_by_time, key=lambda s: s["avg_availability"])
            lines.append("")
            lines.append("## Occupancy By Time Slot")
            for s in slot_availability_by_time:
                lines.append(f"- {s['time']}: {s['signal']} ({s['avg_availability']:.0f} of {competitors} restaurant(s) still open)")
            lines.append(f"Tightest window tonight: {tightest['time']}.")

        if dineout_deals_count or slot_deals:
            lines.append("")
            lines.append("## Dineout Deals Tonight")
            if dineout_deals_count:
                lines.append(dineout_deals_summary)
            for deal in slot_deals[:5]:
                lines.append(f"- {deal['time']}: {deal['deal_title']} ({deal['discount_pct']:.0f}% off)")
            lines.append(
                "Implication: nearby restaurants are incentivising bookings tonight. "
                "Walk-in overflow may be lower than occupancy signal suggests — "
                "demand is being captured by promotional offers."
            )

        return "\n".join(lines)

    # ── Redis helpers ─────────────────────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                get_settings().redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def _cache_get(self, key: str) -> Optional[dict]:
        try:
            r = await self._get_redis()
            raw = await r.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            log.debug("occupancy_enricher_cache_get_error", error=str(exc))
            return None

    async def _cache_set(self, key: str, value: dict) -> None:
        try:
            r = await self._get_redis()
            await r.setex(key, _CACHE_TTL, json.dumps(value, default=str))
        except Exception as exc:
            log.debug("occupancy_enricher_cache_set_error", error=str(exc))

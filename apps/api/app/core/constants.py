#Stores small app-wide constants like: service name, dependency names
#Good for avoiding hardcoded repeated strings everywhere.

SERVICE_NAME = "careops-ai-api"
DEPENDENCY_POSTGRES = "postgres"
DEPENDENCY_QDRANT = "qdrant"
DEPENDENCY_REDIS = "redis"
DEPENDENCY_LLM = "llm"

# Major Indian holidays likely to drive a restaurant demand spike (P6-MI10).
# Demo heuristic for ScenarioRecommender — not an authoritative calendar. Lunar-calendar
# festivals (Diwali, Holi, Eid) shift year to year; dates below are approximate for 2026.
# Update yearly, or replace with a calendar API if this needs to be authoritative.
INDIAN_HOLIDAYS_2026 = {
    "2026-01-01": "New Year's Day",
    "2026-01-14": "Makar Sankranti / Pongal",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-20": "Ugadi",
    "2026-03-21": "Eid al-Fitr",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Ambedkar Jayanti / Tamil New Year",
    "2026-05-01": "May Day",
    "2026-05-27": "Eid al-Adha (Bakrid)",
    "2026-08-15": "Independence Day",
    "2026-08-26": "Raksha Bandhan",
    "2026-09-04": "Janmashtami",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali",
    "2026-11-09": "Govardhan Puja",
    "2026-11-10": "Bhai Dooj",
    "2026-12-25": "Christmas",
}

# Default restaurant coordinates for WeatherService (P6-A21) when a restaurant
# profile has no stored lat/lng -- Navi Mumbai, matching the approximate area
# of SWIGGY_ADDRESS_ID. Replace with real per-restaurant coordinates once
# RestaurantProfile stores them.
DEFAULT_RESTAURANT_LAT = 19.0368
DEFAULT_RESTAURANT_LNG = 73.0158


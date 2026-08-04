"""Shared calendar context helper -- weekend/holiday lookup against
INDIAN_HOLIDAYS_2026, used by both ScenarioRecommender and demand_forecast's
signal-adjustment logic. Extracted so the lookup isn't duplicated as a second
consumer needs it (P6-A21).
"""

from datetime import date, datetime
from typing import Optional

from app.core.constants import INDIAN_HOLIDAYS_2026


def get_date_context(target_date: str) -> tuple[bool, bool, Optional[str]]:
    """Parse a YYYY-MM-DD string and return (is_weekend, is_holiday, holiday_name).

    Falls back to today's date if target_date is missing or unparseable --
    never raises.
    """
    try:
        parsed = datetime.strptime(target_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        parsed = date.today()
    is_weekend = parsed.weekday() >= 5  # Saturday=5, Sunday=6
    holiday_name = INDIAN_HOLIDAYS_2026.get(parsed.isoformat())
    return is_weekend, holiday_name is not None, holiday_name

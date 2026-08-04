"""Unit tests for app.core.calendar_utils.get_date_context (P6-A21)."""

from app.core.calendar_utils import get_date_context


def test_known_holiday_detected():
    is_weekend, is_holiday, holiday_name = get_date_context("2026-08-15")
    assert is_holiday is True
    assert holiday_name == "Independence Day"


def test_regular_weekday_not_holiday():
    # 2026-07-15 is a Wednesday, not in INDIAN_HOLIDAYS_2026
    is_weekend, is_holiday, holiday_name = get_date_context("2026-07-15")
    assert is_weekend is False
    assert is_holiday is False
    assert holiday_name is None


def test_saturday_detected_as_weekend():
    # 2026-07-18 is a Saturday
    is_weekend, is_holiday, holiday_name = get_date_context("2026-07-18")
    assert is_weekend is True


def test_sunday_detected_as_weekend():
    # 2026-07-19 is a Sunday
    is_weekend, is_holiday, holiday_name = get_date_context("2026-07-19")
    assert is_weekend is True


def test_invalid_date_string_falls_back_without_raising():
    is_weekend, is_holiday, holiday_name = get_date_context("not-a-date")
    assert isinstance(is_weekend, bool)
    assert isinstance(is_holiday, bool)


def test_none_falls_back_without_raising():
    is_weekend, is_holiday, holiday_name = get_date_context(None)
    assert isinstance(is_weekend, bool)
    assert isinstance(is_holiday, bool)

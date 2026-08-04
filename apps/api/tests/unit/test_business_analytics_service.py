"""Unit tests for BusinessAnalyticsService -- the shared logic extracted from
business.py so both the Today dashboard and the planning pipeline compute
margin-aware dish ranking, complaint category counts, and peak hours
identically instead of the pipeline reasoning over a disconnected view.

Uses SQLite in-memory DB (MenuItem/Order/Feedback have no JSONB columns).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Expense, ExpenseCategory, ExpenseRecurrence, Feedback, MenuItem, Order, SentimentType
from app.domain.services.business_analytics_service import BusinessAnalyticsService


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    MenuItem.__table__.create(bind=eng)
    Order.__table__.create(bind=eng)
    Feedback.__table__.create(bind=eng)
    Expense.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(Expense).delete()
        session.query(Feedback).delete()
        session.query(Order).delete()
        session.query(MenuItem).delete()
        session.commit()


def _menu_item(db, name, category, price, cost_price):
    item = MenuItem(name=name, category=category, price=price, cost_price=cost_price)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _order(db, item, quantity, total_price, days_ago=1, hour=19):
    when = datetime.utcnow() - timedelta(days=days_ago)
    when = when.replace(hour=hour, minute=0, second=0, microsecond=0)
    o = Order(menu_item_id=item.id, quantity=quantity, total_price=total_price, ordered_at=when)
    db.add(o)
    db.commit()


def _feedback(db, text, sentiment=SentimentType.negative, days_ago=1):
    fb = Feedback(raw_text=text, sentiment=sentiment, created_at=datetime.utcnow() - timedelta(days=days_ago))
    db.add(fb)
    db.commit()


def _expense(db, category, amount, recurrence, days_ago_start, days_ago_end=None, note=None):
    start = datetime.utcnow() - timedelta(days=days_ago_start)
    end = (datetime.utcnow() - timedelta(days=days_ago_end)) if days_ago_end is not None else None
    e = Expense(category=category, amount=amount, recurrence=recurrence, effective_date=start, end_date=end, note=note, org_id=1)
    db.add(e)
    db.commit()


# ── get_dish_performance ─────────────────────────────────────────────────────

def test_dish_performance_computes_margin_and_sorts_by_revenue(db):
    high = _menu_item(db, "Margherita", "pizza", price=300.0, cost_price=100.0)   # 66.7% margin
    low  = _menu_item(db, "Four Cheese", "pizza", price=300.0, cost_price=250.0)  # 16.7% margin
    _order(db, high, quantity=2, total_price=600.0, days_ago=1)
    _order(db, low, quantity=5, total_price=1500.0, days_ago=1)  # higher revenue, lower margin

    analytics = BusinessAnalyticsService(db)
    dishes = analytics.get_dish_performance(days=14)

    assert dishes[0]["name"] == "Four Cheese"  # sorted by revenue first
    assert dishes[0]["revenue"] == 1500.0
    assert dishes[0]["margin_pct"] == pytest.approx(16.7, abs=0.1)
    assert dishes[1]["name"] == "Margherita"
    assert dishes[1]["margin_pct"] == pytest.approx(66.7, abs=0.1)


def test_dish_performance_margin_none_when_cost_price_missing(db):
    item = _menu_item(db, "Mystery Dish", "sides", price=100.0, cost_price=None)
    _order(db, item, quantity=1, total_price=100.0, days_ago=1)

    analytics = BusinessAnalyticsService(db)
    dishes = analytics.get_dish_performance(days=14)
    assert dishes[0]["margin_pct"] is None


def test_dish_performance_excludes_orders_outside_window(db):
    item = _menu_item(db, "Old Dish", "sides", price=100.0, cost_price=50.0)
    _order(db, item, quantity=1, total_price=100.0, days_ago=30)

    analytics = BusinessAnalyticsService(db)
    dishes = analytics.get_dish_performance(days=14)
    assert dishes == []


# ── get_complaints_by_category ───────────────────────────────────────────────

def test_complaints_by_category_groups_by_keyword_and_sorts_by_count(db):
    _feedback(db, "We waited over 40 minutes for our order", days_ago=2)
    _feedback(db, "Service was slow tonight", days_ago=3)
    _feedback(db, "Clinical assessment felt rushed", days_ago=1)
    _feedback(db, "Great care, loved it!", sentiment=SentimentType.positive, days_ago=1)

    analytics = BusinessAnalyticsService(db)
    result = analytics.get_complaints_by_category(days=28)

    assert result[0] == {"category": "Wait Time", "count": 2}
    assert {"category": "Care Quality", "count": 1} in result
    # positive feedback never counted
    assert sum(r["count"] for r in result) == 3


def test_complaints_by_category_excludes_outside_window(db):
    _feedback(db, "Waited forever", days_ago=40)
    analytics = BusinessAnalyticsService(db)
    assert analytics.get_complaints_by_category(days=28) == []


# ── get_peak_hours ───────────────────────────────────────────────────────────

def test_peak_hours_returns_24_entries_with_correct_averages(db):
    item = _menu_item(db, "Anything", "sides", price=100.0, cost_price=50.0)
    _order(db, item, quantity=1, total_price=100.0, days_ago=1, hour=19)
    _order(db, item, quantity=1, total_price=100.0, days_ago=2, hour=19)

    analytics = BusinessAnalyticsService(db)
    # days=3 here (not 2) deliberately gives a full calendar day of buffer beyond
    # the furthest order (days_ago=2): trend_start's calendar day is always
    # strictly earlier than day_ago=2's, regardless of what wall-clock hour the
    # test happens to run at. Using days=2 made this test flaky -- it failed
    # whenever the suite ran after 19:00 UTC, since trend_start would then fall
    # later in the day than the fixed hour=19 order timestamp on its boundary day.
    result = analytics.get_peak_hours(days=3)

    assert len(result) == 24
    hour_19 = next(h for h in result if h["hour"] == 19)
    assert hour_19["avg_orders"] == 0.7  # 2 orders / 3 days, rounded to 1 decimal
    hour_10 = next(h for h in result if h["hour"] == 10)
    assert hour_10["avg_orders"] == 0.0


# ── get_daily_expense_total ───────────────────────────────────────────────────

def test_daily_expense_prorates_monthly_recurring_cost(db):
    _expense(db, ExpenseCategory.rent, 30000.0, ExpenseRecurrence.monthly, days_ago_start=60)
    analytics = BusinessAnalyticsService(db)
    total = analytics.get_daily_expense_total(datetime.utcnow())
    assert total == 1000.0  # 30000 / 30


def test_daily_expense_prorates_weekly_recurring_cost(db):
    _expense(db, ExpenseCategory.marketing, 700.0, ExpenseRecurrence.weekly, days_ago_start=30)
    analytics = BusinessAnalyticsService(db)
    total = analytics.get_daily_expense_total(datetime.utcnow())
    assert total == 100.0  # 700 / 7


def test_daily_expense_one_time_only_counts_on_its_own_date(db):
    _expense(db, ExpenseCategory.other, 5000.0, ExpenseRecurrence.one_time, days_ago_start=3)
    analytics = BusinessAnalyticsService(db)
    assert analytics.get_daily_expense_total(datetime.utcnow() - timedelta(days=3)) == 5000.0
    assert analytics.get_daily_expense_total(datetime.utcnow() - timedelta(days=2)) == 0.0
    assert analytics.get_daily_expense_total(datetime.utcnow()) == 0.0


def test_daily_expense_ended_recurring_cost_excluded_after_end_date(db):
    _expense(db, ExpenseCategory.utilities, 3000.0, ExpenseRecurrence.monthly, days_ago_start=60, days_ago_end=10)
    analytics = BusinessAnalyticsService(db)
    # still within the active window (10 days ago the expense ended, so 15 days ago it was active)
    assert analytics.get_daily_expense_total(datetime.utcnow() - timedelta(days=15)) == 100.0
    # after end_date -- no longer counted
    assert analytics.get_daily_expense_total(datetime.utcnow() - timedelta(days=5)) == 0.0


def test_daily_expense_sums_multiple_active_expenses(db):
    _expense(db, ExpenseCategory.rent, 30000.0, ExpenseRecurrence.monthly, days_ago_start=60)
    _expense(db, ExpenseCategory.utilities, 700.0, ExpenseRecurrence.weekly, days_ago_start=60)
    analytics = BusinessAnalyticsService(db)
    total = analytics.get_daily_expense_total(datetime.utcnow())
    assert total == 1100.0  # 1000 + 100


# ── get_positive_sentiment_pct ────────────────────────────────────────────────

def test_positive_sentiment_pct_computes_correctly(db):
    _feedback(db, "Loved it", sentiment=SentimentType.positive, days_ago=1)
    _feedback(db, "Great service", sentiment=SentimentType.positive, days_ago=2)
    _feedback(db, "Too slow", sentiment=SentimentType.negative, days_ago=1)
    _feedback(db, "Meh", sentiment=SentimentType.neutral, days_ago=1)

    analytics = BusinessAnalyticsService(db)
    assert analytics.get_positive_sentiment_pct(days=28) == 50.0  # 2 of 4


def test_positive_sentiment_pct_returns_none_when_no_feedback(db):
    analytics = BusinessAnalyticsService(db)
    assert analytics.get_positive_sentiment_pct(days=28) is None


# ── compute_health_score ──────────────────────────────────────────────────────

def test_health_score_weights_margin_and_sentiment(db):
    analytics = BusinessAnalyticsService(db)
    # 30% net margin (benchmark) + 100% positive sentiment -> full marks on both
    assert analytics.compute_health_score(net_margin_pct=30.0, positive_sentiment_pct=100.0) == 100
    # 0% margin, 0% sentiment -> 0
    assert analytics.compute_health_score(net_margin_pct=0.0, positive_sentiment_pct=0.0) == 0
    # 15% margin (half of benchmark) + 50% sentiment -> 0.7*50 + 0.3*50 = 50
    assert analytics.compute_health_score(net_margin_pct=15.0, positive_sentiment_pct=50.0) == 50


def test_health_score_defaults_sentiment_to_neutral_when_missing(db):
    analytics = BusinessAnalyticsService(db)
    # 30% margin, no sentiment data -> 0.7*100 + 0.3*50 = 85
    assert analytics.compute_health_score(net_margin_pct=30.0, positive_sentiment_pct=None) == 85


def test_health_score_defaults_margin_to_zero_when_missing(db):
    analytics = BusinessAnalyticsService(db)
    # no margin data (no revenue) is treated as a bad sign, not neutral
    assert analytics.compute_health_score(net_margin_pct=None, positive_sentiment_pct=100.0) == 30


def test_health_score_caps_margin_component_above_benchmark(db):
    analytics = BusinessAnalyticsService(db)
    # 60% margin (2x benchmark) should cap at 100, not exceed it
    assert analytics.compute_health_score(net_margin_pct=60.0, positive_sentiment_pct=0.0) == 70

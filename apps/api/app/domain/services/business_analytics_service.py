"""Shared analytics queries used by both GET /business/performance (the Today
dashboard) and the planning pipeline (menu_intelligence, complaint_intelligence,
reservation). Extracted so both consumers compute margin-aware dish ranking,
complaint category counts, and real peak-hours identically instead of the
pipeline reasoning over a completely disconnected view of the same data.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.scenarios import list_scenarios
from app.infrastructure.db.models import (
    Expense, ExpenseRecurrence, Feedback, Inventory, MenuItem, Order,
    PlanningRun, Reservation, ReservationStatus, SentimentType,
)

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

# Keyword buckets checked in order -- first match wins. Tuned against the
# actual seeded complaint text (see scripts/seed_demo_data.py).
_COMPLAINT_CATEGORIES: list[tuple[str, list[str]]] = [
    ("Wait Time", ["wait", "waited", "waiting", "slow", "queue", "took over", "minutes", "took forever", "forever", "long", "delayed", "backlog", "late"]),
    ("Care Quality", ["rushed", "incomplete", "undersalted", "redone", "chaos", "clinical", "care", "assessment"]),
    ("Stock & Availability", ["ran out", "out of", "unavailable", "stockout", "low", "supply"]),
    ("Documentation", ["chart", "instructions", "summary", "incomplete", "missing"]),
    ("Access & Value", ["wheelchair", "co-pay", "expensive", "fee", "parking"]),
    ("Environment", ["noisy", "noise", "crowded", "seating", "overwhelmed"]),
]


def _categorize(text: str) -> str:
    lowered = text.lower()
    for category, keywords in _COMPLAINT_CATEGORIES:
        if any(kw in lowered for kw in keywords):
            return category
    return "Other"


class BusinessAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def get_dish_performance(self, days: int = 14) -> list[dict]:
        """Revenue, quantity, and margin_pct per dish over the trend window,
        sorted by revenue descending. margin_pct is None when cost_price isn't set."""
        trend_start = datetime.utcnow() - timedelta(days=days)
        rows = (
            self.db.query(
                MenuItem.name, MenuItem.category, MenuItem.price, MenuItem.cost_price,
                func.sum(Order.total_price).label("revenue"),
                func.sum(Order.quantity).label("quantity"),
            )
            .join(Order, Order.menu_item_id == MenuItem.id)
            .filter(Order.ordered_at >= trend_start)
            .group_by(MenuItem.id, MenuItem.name, MenuItem.category, MenuItem.price, MenuItem.cost_price)
            .all()
        )
        dishes = []
        for row in rows:
            margin = None
            if row.cost_price is not None and row.price:
                margin = round((row.price - row.cost_price) / row.price * 100, 1)
            dishes.append({
                "name": row.name, "category": row.category,
                "revenue": round(float(row.revenue or 0), 2), "quantity": int(row.quantity or 0),
                "margin_pct": margin,
            })
        dishes.sort(key=lambda d: d["revenue"], reverse=True)
        return dishes

    def get_complaints_by_category(self, days: int = 28) -> list[dict]:
        window = datetime.utcnow() - timedelta(days=days)
        rows = (
            self.db.query(Feedback.raw_text)
            .filter(Feedback.sentiment == SentimentType.negative, Feedback.created_at >= window)
            .all()
        )
        counts: dict[str, int] = defaultdict(int)
        for (text,) in rows:
            counts[_categorize(text)] += 1
        return [
            {"category": cat, "count": n}
            for cat, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        ]

    def get_daily_expense_total(self, target_date: datetime) -> float:
        """Prorate one-time and recurring expenses into a single daily-equivalent
        figure for target_date -- e.g. Rs.50,000/month rent -> ~Rs.1,667/day.
        Monthly uses a flat /30 divisor (demo-scale precision, matches the rest
        of this codebase's simplifications, e.g. reservation capacity math)."""
        target_day = target_date.date()
        expenses = (
            self.db.query(Expense)
            .filter(
                func.date(Expense.effective_date) <= target_day,
                (Expense.end_date.is_(None)) | (func.date(Expense.end_date) >= target_day),
            )
            .all()
        )
        total = 0.0
        for e in expenses:
            if e.recurrence == ExpenseRecurrence.one_time:
                if e.effective_date.date() == target_day:
                    total += e.amount
            elif e.recurrence == ExpenseRecurrence.daily:
                total += e.amount
            elif e.recurrence == ExpenseRecurrence.weekly:
                total += e.amount / 7
            elif e.recurrence == ExpenseRecurrence.monthly:
                total += e.amount / 30
        return round(total, 2)

    def get_total_expenses_for_period(self, days: int) -> float:
        """Sum of get_daily_expense_total() across the trailing `days` days."""
        total = 0.0
        for i in range(days):
            day = datetime.utcnow() - timedelta(days=i)
            total += self.get_daily_expense_total(day)
        return round(total, 2)

    def get_net_margin_pct(self, days: int = 14) -> float | None:
        """Period net margin % -- (gross profit - expenses) / revenue -- the
        same reconciliation GET /business/performance computes inline from its
        already-fetched daily trend. Extracted so other consumers (e.g.
        BriefingService) reach the real number instead of a placeholder."""
        trend_start = datetime.utcnow() - timedelta(days=days)
        row = (
            self.db.query(
                func.sum(Order.total_price).label("revenue"),
                func.sum(Order.quantity * func.coalesce(MenuItem.cost_price, 0)).label("cost"),
            )
            .join(MenuItem, Order.menu_item_id == MenuItem.id)
            .filter(Order.ordered_at >= trend_start)
            .first()
        )
        revenue = float(row.revenue or 0) if row else 0.0
        cost = float(row.cost or 0) if row else 0.0
        gross_profit = revenue - cost
        net_profit = gross_profit - self.get_total_expenses_for_period(days)
        return round(net_profit / revenue * 100, 1) if revenue > 0 else None

    def get_positive_sentiment_pct(self, days: int = 28) -> float | None:
        """Share of feedback rows in the window that are positive. None when
        there's no feedback at all, so callers can distinguish "no data" from 0%."""
        window = datetime.utcnow() - timedelta(days=days)
        rows = self.db.query(Feedback.sentiment).filter(Feedback.created_at >= window).all()
        if not rows:
            return None
        positive = sum(1 for (s,) in rows if s == SentimentType.positive)
        return round(positive / len(rows) * 100, 1)

    def compute_health_score(self, net_margin_pct: float | None, positive_sentiment_pct: float | None) -> int:
        """Deterministic composite score, 0-100. Weighted 70% net margin (normalized
        against a 30%-net-margin benchmark for a healthy restaurant), 30% guest
        sentiment. Missing sentiment data defaults to a neutral 50, missing margin
        data defaults to 0 (no revenue data is itself a bad sign, not neutral)."""
        margin_component = 0.0
        if net_margin_pct is not None:
            margin_component = max(0.0, min(100.0, (net_margin_pct / 30.0) * 100))
        sentiment_component = positive_sentiment_pct if positive_sentiment_pct is not None else 50.0
        return round(0.7 * margin_component + 0.3 * sentiment_component)

    def get_forecast_accuracy(self, days: int = 30) -> dict:
        """Reconcile past planning runs' predicted_orders against what actually
        happened that day (real Order rows), for runs whose target_date has
        already passed. Reads recommendations["forecast"]["data"]["predicted_orders"]
        -- the exact same path aggregator.py's critic summary already reads --
        no second forecasting path, just a reconciliation against real orders.
        Returns {"points": [...], "accuracy_pct": float | None}. None means no
        past run has both a forecast and enough elapsed time to reconcile yet.
        """
        window_start = datetime.utcnow() - timedelta(days=days)
        today = datetime.utcnow().date()
        runs = (
            self.db.query(PlanningRun)
            .filter(PlanningRun.generated_at >= window_start, PlanningRun.target_date.isnot(None))
            .all()
        )

        points = []
        for run in runs:
            try:
                target = datetime.strptime(run.target_date, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            if target >= today:
                continue  # only reconcile dates that have actually happened
            forecast = (run.recommendations or {}).get("forecast") or {}
            predicted = (forecast.get("data") or {}).get("predicted_orders")
            if predicted is None:
                continue
            actual = (
                self.db.query(func.count(Order.id))
                .filter(func.date(Order.ordered_at) == target)
                .scalar() or 0
            )
            if actual == 0:
                continue
            points.append({
                "date": target.isoformat(),
                "scenario": run.scenario,
                "predicted_orders": round(float(predicted), 1),
                "actual_orders": actual,
                "error_pct": round(abs(predicted - actual) / actual * 100, 1),
            })

        points.sort(key=lambda p: p["date"])
        if not points:
            return {"points": [], "accuracy_pct": None}
        mean_error_pct = sum(p["error_pct"] for p in points) / len(points)
        return {"points": points[-10:], "accuracy_pct": round(max(0.0, 100 - mean_error_pct), 1)}

    def get_upcoming_risks(self, capacity: int = 70) -> list[dict]:
        """Forward-looking risk list assembled purely from data other consumers
        already compute -- InventoryService.compute_alerts() (same call
        GET /data-health already makes) for shortages, and the same per-scenario
        upcoming-occupancy pattern runs.py's _scenario_coverage uses for
        reservations (reimplemented here, not imported, since routes -> domain
        is the correct dependency direction, not the reverse). No LLM call --
        deterministic templated text, cheap enough to compute on every
        dashboard load.
        """
        from app.domain.services.inventory_service import InventoryService

        risks: list[dict] = []

        inventory_items = self.db.query(Inventory).all()
        alerts = InventoryService(db=self.db, llm=None).compute_alerts(inventory_items)
        for alert in alerts["shortage_alerts"]:
            if alert["severity"] != "critical":
                continue
            risks.append({
                "kind": "inventory",
                "severity": "critical",
                "text": (
                    f"{_to_supply_label(alert['ingredient'])} below reorder threshold "
                    f"({alert['quantity_in_stock']}{alert['unit']} / {alert['reorder_threshold']}{alert['unit']}) "
                    "-- reorder before next shift handoff."
                ),
            })

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        for scenario in list_scenarios():
            days_ahead = (scenario["default_weekday"] - today.weekday()) % 7
            days_ahead = days_ahead or 7
            target = today + timedelta(days=days_ahead)
            rows = self.db.query(Reservation).filter(
                Reservation.reserved_at >= target,
                Reservation.reserved_at <= target.replace(hour=23, minute=59, second=59),
                Reservation.status.in_([ReservationStatus.confirmed, ReservationStatus.waitlist]),
            ).all()
            guests = sum(r.guest_count for r in rows)
            occupancy_pct = round((guests / capacity) * 100, 1) if capacity else 0.0
            if occupancy_pct >= 90:
                risks.append({
                    "kind": "occupancy",
                    "severity": "warning",
                    "text": (
                        f"{scenario['label']} ({target.strftime('%Y-%m-%d')}) forecasted at "
                        f"{occupancy_pct}% bed utilization -- waitlist likely."
                    ),
                })

        return risks

    def get_peak_hours(self, days: int = 14) -> list[dict]:
        """Average orders per hour-of-day over the trend window, from real order
        timestamps -- not the static configured service-hours string."""
        trend_start = datetime.utcnow() - timedelta(days=days)
        hour_col = func.extract("hour", Order.ordered_at)
        rows = (
            self.db.query(hour_col.label("hour"), func.count(Order.id).label("cnt"))
            .filter(Order.ordered_at >= trend_start)
            .group_by(hour_col)
            .all()
        )
        hour_counts = {int(h): cnt for h, cnt in rows}
        return [
            {"hour": h, "avg_orders": round(hour_counts.get(h, 0) / days, 1)}
            for h in range(24)
        ]

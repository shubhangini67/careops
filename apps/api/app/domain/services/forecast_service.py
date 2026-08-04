from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
from prophet import Prophet

from app.infrastructure.db.models import Order
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.prompt_utils import PromptUtils
from app.infrastructure.forecasting.prophet_forecaster import ProphetForecaster

# Holiday demand multiplier (P6-A21) -- applied to Prophet's raw predicted_orders
# when the target date is a known public holiday (INDIAN_HOLIDAYS_2026). Flat and
# conservative rather than per-holiday-tiered: Prophet's 90-day training window
# is unlikely to contain an equivalent holiday spike, so without this adjustment
# a genuinely unusual day gets forecast like an ordinary one. Documented constant,
# not a silent guess -- see _apply_signal_adjustments for how it's surfaced.
_HOLIDAY_DEMAND_MULTIPLIER = 1.4


class ForecastService:
    """Analyses historical order data to forecast Friday demand."""

    def get_friday_order_history(self, target_date: datetime | None = None) -> list[dict]:
        """Backward-compatible wrapper for older Friday-specific callers/tests."""
        return self.get_service_day_order_history(target_date)

    def get_top_friday_items(self, target_date: datetime | None = None) -> list[dict]:
        """Backward-compatible wrapper for older Friday-specific callers/tests."""
        return self.get_top_service_day_items(target_date)

    def __init__(self, db: Session, llm: BaseLLMProvider):
        self.db = db
        self.llm = llm

    def get_service_day_order_history(self, target_date: datetime | None = None) -> list[dict]:
        """Get order counts for the last 4 matching weekdays for the target date."""
        results = []
        service_day = self._get_target_date(target_date)
        today = datetime.now()
        weekday = service_day.weekday()

        probe = today
        found = 0
        while found < 4:
            probe -= timedelta(days=1)
            if probe.weekday() != weekday:
                continue

            start = probe.replace(hour=0, minute=0, second=0)
            end = probe.replace(hour=23, minute=59, second=59)

            count = self.db.query(func.count(Order.id)).filter(
                Order.ordered_at >= start,
                Order.ordered_at <= end
            ).scalar()

            peak_count = self.db.query(func.count(Order.id)).filter(
                Order.ordered_at >= probe.replace(hour=18, minute=0, second=0),
                Order.ordered_at <= probe.replace(hour=22, minute=59, second=59)
            ).scalar()

            results.append({
                "date": probe.strftime("%Y-%m-%d"),
                "total_orders": count,
                "peak_orders_6pm_to_11pm": peak_count,
            })
            found += 1

        return results

    def get_daily_order_history(self, days_back: int = 90) -> pd.DataFrame:
        """Get daily order counts for time series forecasting."""
        results = []
        today = datetime.now()

        for day_offset in range(days_back, 0, -1):
            current_date = today - timedelta(days=day_offset)
            start = current_date.replace(hour=0, minute=0, second=0)
            end = current_date.replace(hour=23, minute=59, second=59)

            # Total orders for the day
            total_count = self.db.query(func.count(Order.id)).filter(
                Order.ordered_at >= start,
                Order.ordered_at <= end
            ).scalar()

            # Peak orders (6pm-11pm)
            peak_count = self.db.query(func.count(Order.id)).filter(
                Order.ordered_at >= current_date.replace(hour=18, minute=0, second=0),
                Order.ordered_at <= current_date.replace(hour=22, minute=59, second=59)
            ).scalar()

            results.append({
                "ds": current_date.date(),  # Prophet expects 'ds' column for dates
                "y": total_count,  # Prophet expects 'y' column for values
                "peak_orders": peak_count,
                "is_friday": current_date.weekday() == 4
            })

        return pd.DataFrame(results)

    def get_top_service_day_items(self, target_date: datetime | None = None) -> list[dict]:
        """Get the most ordered menu items on matching weekdays for the target date."""
        from app.infrastructure.db.models import MenuItem

        service_day = self._get_target_date(target_date)
        weekday = service_day.weekday()
        today = datetime.now()
        matching_dates = []

        probe = today
        while len(matching_dates) < 4:
            probe -= timedelta(days=1)
            if probe.weekday() == weekday:
                matching_dates.append(probe)

        item_counts = {}
        for service_date in matching_dates:
            start = service_date.replace(hour=0, minute=0, second=0)
            end = service_date.replace(hour=23, minute=59, second=59)

            orders = self.db.query(Order).filter(
                Order.ordered_at >= start,
                Order.ordered_at <= end
            ).all()

            for order in orders:
                item_counts[order.menu_item_id] = item_counts.get(order.menu_item_id, 0) + order.quantity

        # Get top 5 items
        top_ids = sorted(item_counts, key=item_counts.get, reverse=True)[:5]
        top_items = []
        for item_id in top_ids:
            item = self.db.query(MenuItem).filter(MenuItem.id == item_id).first()
            if item:
                top_items.append({
                    "item": item.name,
                    "category": item.category,
                    "total_ordered": item_counts[item_id]
                })

        return top_items

    def calculate_baseline_forecast(self, target_date: datetime | None = None) -> dict:
        """Calculate predicted demand for target Friday using baseline method."""
        history = self.get_friday_order_history(target_date)
        if not history:
            return {"predicted_orders": 0, "confidence": "low"}

        avg_orders = sum(h["total_orders"] for h in history) / len(history)
        avg_peak = sum(h["peak_orders_6pm_to_11pm"] for h in history) / len(history)

        target_service_date = self._get_target_date(target_date)
        service_day_label = target_service_date.strftime("%A")

        return {
            "history": history,
            "avg_friday_orders": round(avg_orders, 1),
            "avg_same_day_orders": round(avg_orders, 1),
            "avg_peak_orders": round(avg_peak, 1),
            "predicted_orders": round(avg_orders * 1.05, 1),  # 5% growth assumption
            "predicted_peak_orders": round(avg_peak * 1.05, 1),
            "top_items": self.get_top_friday_items(target_date),
            "method": "baseline",
            "target_date": target_service_date.strftime("%Y-%m-%d"),
            "service_day_label": service_day_label,
        }



    def calculate_prophet_forecast(self, target_date: datetime | None = None) -> dict:
        """Calculate predicted demand for target Friday using Prophet."""
        try:
            df = self.get_daily_order_history(days_back=90)

            target_service_date = self._get_target_date(target_date)
            forecaster = ProphetForecaster()
            prediction = forecaster.fit_and_predict(df, target_service_date)

            # Historical Friday context for the response
            service_day_history = self.get_friday_order_history(target_date)
            avg_friday_orders = (
                sum(h["total_orders"] for h in service_day_history) / len(service_day_history)
                if service_day_history else 0
            )
            avg_peak_orders = (
                sum(h["peak_orders_6pm_to_11pm"] for h in service_day_history) / len(service_day_history)
                if service_day_history else 0
            )

            predicted_peak_orders = round(
                prediction["yhat"] * prediction["peak_ratio_used"], 1
            )
            service_day_label = target_service_date.strftime("%A")

            return {
                "history": service_day_history,
                "avg_friday_orders": round(avg_friday_orders, 1),
                "avg_same_day_orders": round(avg_friday_orders, 1),
                "avg_peak_orders": round(avg_peak_orders, 1),
                "predicted_orders": round(prediction["yhat"], 1),
                "predicted_orders_lower": round(prediction["yhat_lower"], 1),
                "predicted_orders_upper": round(prediction["yhat_upper"], 1),
                "predicted_peak_orders": predicted_peak_orders,
                "top_items": self.get_top_friday_items(target_date),
                "method": "prophet",
                "confidence": "high" if len(df) >= 60 else "medium",
                "target_date": target_service_date.strftime("%Y-%m-%d"),
                "service_day_label": service_day_label,
            }

        except Exception as e:
            print(f"Prophet forecasting failed: {e}, falling back to baseline")
            return self.calculate_baseline_forecast(target_date)





    def _get_target_date(self, target_date: datetime | None = None) -> datetime:
        """Get the explicitly requested service date, or the next Friday by default."""
        if target_date:
            return target_date
        today = datetime.now()
        days_ahead = (4 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    def calculate_forecast(self, target_date: datetime | None = None) -> dict:
        """Calculate predicted demand for target Friday using Prophet (with baseline fallback)."""
        return self.calculate_prophet_forecast(target_date)

    def _apply_signal_adjustments(
        self,
        forecast: dict,
        weather_signal: Optional[dict] = None,
        is_holiday: bool = False,
        holiday_name: Optional[str] = None,
    ) -> dict:
        """Apply a deterministic multiplier to Prophet's raw predicted_orders/
        predicted_peak_orders (P6-A21). Prophet is a purely historical model --
        it cannot know about a forward-looking, one-off signal its 90-day
        training window never saw (a holiday, a rain forecast). Without this,
        weather/holiday only ever reach the LLM as narrative text the
        recommendation step may or may not act on; this makes them move the
        actual predicted number.

        Transparent by construction -- predicted_orders_pre_adjustment,
        adjustment_multiplier, and adjustment_reasons are all preserved, so
        nothing here is a silent change to what Prophet said.
        """
        multiplier = 1.0
        reasons: list[str] = []

        if is_holiday:
            multiplier *= _HOLIDAY_DEMAND_MULTIPLIER
            reasons.append(f"holiday ({holiday_name or 'public holiday'}): x{_HOLIDAY_DEMAND_MULTIPLIER}")

        if weather_signal and weather_signal.get("demand_multiplier"):
            weather_multiplier = float(weather_signal["demand_multiplier"])
            if weather_multiplier != 1.0:
                multiplier *= weather_multiplier
                reasons.append(
                    f"weather ({weather_signal.get('condition', 'unknown')}): x{weather_multiplier}"
                )

        if multiplier == 1.0:
            return forecast

        pre_adjustment_orders = forecast.get("predicted_orders", 0) or 0
        pre_adjustment_peak = forecast.get("predicted_peak_orders", 0) or 0

        forecast = {
            **forecast,
            "predicted_orders_pre_adjustment": pre_adjustment_orders,
            "predicted_peak_orders_pre_adjustment": pre_adjustment_peak,
            "predicted_orders": round(pre_adjustment_orders * multiplier, 1),
            "predicted_peak_orders": round(pre_adjustment_peak * multiplier, 1),
            "adjustment_multiplier": round(multiplier, 3),
            "adjustment_reasons": reasons,
        }
        return forecast

    async def analyse_and_recommend(
        self,
        target_date: datetime | None = None,
        org_capacity: int | None = None,
        weather_signal: Optional[dict] = None,
        is_holiday: bool = False,
        holiday_name: Optional[str] = None,
        trends_signal: Optional[dict] = None,
        compliance_alerts_signal: Optional[dict] = None,
    ) -> dict:
        """Use Gemini to analyse forecast data and generate recommendation."""

        forecast = self.calculate_forecast(target_date)
        forecast = self._apply_signal_adjustments(forecast, weather_signal, is_holiday, holiday_name)

        predicted = forecast.get("predicted_orders", 0)
        capacity_line = ""
        if org_capacity:
            if predicted and float(predicted) > org_capacity:
                capacity_line = (
                    f"\n- Restaurant seating capacity: {org_capacity} seats "
                    f"(Prophet predicted {predicted} orders — demand exceeds seating capacity. "
                    f"Frame staffing as 'plan for a full house of {org_capacity}', never reference the demand number as a diner count)"
                )
            else:
                capacity_line = f"\n- Restaurant seating capacity: {org_capacity} seats"

        signal_line = ""
        if forecast.get("adjustment_reasons"):
            signal_line = (
                f"\n- Demand adjusted x{forecast['adjustment_multiplier']} from "
                f"{forecast['predicted_orders_pre_adjustment']} baseline due to: "
                f"{'; '.join(forecast['adjustment_reasons'])}"
            )
        if weather_signal and weather_signal.get("signal"):
            signal_line += f"\n- Weather: {weather_signal['signal']}"
        # P6-A22/A23: narrative-only context, neither shifts the predicted number --
        # unlike weather/holiday, trends/regulatory news aren't demand multipliers.
        if trends_signal and trends_signal.get("digest"):
            signal_line += f"\n- Industry trends: {trends_signal['digest']}"
        if compliance_alerts_signal and compliance_alerts_signal.get("notices"):
            notice_titles = "; ".join(n["title"] for n in compliance_alerts_signal["notices"][:3])
            signal_line += f"\n- Recent FSSAI notices: {notice_titles}"

        service_day_label = forecast.get("service_day_label", "service day")
        prompt = PromptUtils.format_recommendation_prompt(
            context=f"""
Demand forecast for the target {service_day_label} service (using {forecast.get('method', 'baseline')} method):
- Average orders over last 4 matching service days: {forecast['avg_friday_orders']}
- Average peak orders (6pm-11pm): {forecast['avg_peak_orders']}
- Predicted orders for the target service: {forecast['predicted_orders']}
{f"- Prediction range: {forecast.get('predicted_orders_lower', 'N/A')} - {forecast.get('predicted_orders_upper', 'N/A')}" if forecast.get('predicted_orders_lower') else ""}
- Predicted peak orders: {forecast['predicted_peak_orders']}
- Forecast confidence: {forecast.get('confidence', 'medium')}
- Top ordered items on matching service days: {forecast['top_items']}{capacity_line}{signal_line}
""",
            task="Based on this demand forecast, recommend specific staffing and preparation actions for the target service window."
        )

        recommendation = await self.llm.complete_json(
            prompt=prompt,
            system_prompt=PromptUtils.SYSTEM_DEMAND_FORECAST_AGENT
        )

        return {
            "service": "forecast",
            "data": forecast,
            "recommendation": recommendation
        }

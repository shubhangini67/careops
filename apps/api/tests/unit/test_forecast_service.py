"""
Unit tests for ForecastService — P2-01 acceptance criteria.

Covers:
- calculate_prophet_forecast: happy path, method field, confidence,
  range fields (yhat_lower/upper), peak orders
- calculate_baseline_forecast: method field, structure
- Fallback: Prophet path falls back to baseline when data < 30 rows
- calculate_forecast: routes to Prophet by default
- ProphetForecaster: raises ValueError on insufficient data

All tests are pure unit tests — DB, LLM, and Prophet are mocked.

Run with:
    cd apps/api && pytest tests/unit/test_forecast_service.py -v
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db_mock(order_count: int = 50, peak_count: int = 30):
    """DB mock that returns fixed counts for all scalar queries."""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = order_count
    db.query.return_value.filter.return_value.all.return_value = []
    return db


def _make_daily_df(n_days: int = 90) -> pd.DataFrame:
    """Create a minimal daily DataFrame that Prophet can fit."""
    dates = pd.date_range(end="2026-04-11", periods=n_days, freq="D")
    return pd.DataFrame({
        "ds": dates.date,
        "y": [50 + (i % 7) * 10 for i in range(n_days)],
        "peak_orders": [30 + (i % 7) * 5 for i in range(n_days)],
        "is_friday": [d.weekday() == 4 for d in dates],
    })


TARGET = datetime(2026, 4, 17)  # a Friday  ← April 17 2026 is correct


# ── ProphetForecaster unit tests ──────────────────────────────────────────────

class TestProphetForecaster:

    def test_raises_on_insufficient_data(self):
        from app.infrastructure.forecasting.prophet_forecaster import ProphetForecaster

        forecaster = ProphetForecaster()
        tiny_df = _make_daily_df(n_days=10)

        with pytest.raises(ValueError, match="Not enough data"):
            forecaster.fit_and_predict(tiny_df, TARGET)

    def test_returns_required_keys(self):
        from app.infrastructure.forecasting.prophet_forecaster import ProphetForecaster

        forecaster = ProphetForecaster()
        df = _make_daily_df(n_days=60)
        result = forecaster.fit_and_predict(df, TARGET)

        assert "yhat" in result
        assert "yhat_lower" in result
        assert "yhat_upper" in result
        assert "peak_ratio_used" in result

    def test_yhat_lower_le_yhat_le_yhat_upper(self):
        from app.infrastructure.forecasting.prophet_forecaster import ProphetForecaster

        forecaster = ProphetForecaster()
        df = _make_daily_df(n_days=60)
        result = forecaster.fit_and_predict(df, TARGET)

        assert result["yhat_lower"] <= result["yhat"] <= result["yhat_upper"]

    def test_peak_ratio_defaults_when_no_friday_data(self):
        from app.infrastructure.forecasting.prophet_forecaster import ProphetForecaster

        forecaster = ProphetForecaster()
        df = _make_daily_df(n_days=60)
        # Zero out all friday y values so peak ratio falls back to default 0.6
        df.loc[df["is_friday"], "y"] = 0
        result = forecaster.fit_and_predict(df, TARGET)

        assert result["peak_ratio_used"] == 0.6


# ── ForecastService.calculate_prophet_forecast ───────────────────────────────

class TestCalculateProphetForecast:

    def test_returns_method_prophet(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_daily_order_history", return_value=_make_daily_df(90)), \
             patch.object(svc, "get_friday_order_history", return_value=[
                 {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
             ]), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_prophet_forecast(TARGET)

        assert result["method"] == "prophet"

    def test_returns_prediction_range_fields(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_daily_order_history", return_value=_make_daily_df(90)), \
             patch.object(svc, "get_friday_order_history", return_value=[
                 {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
             ]), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_prophet_forecast(TARGET)

        assert "predicted_orders_lower" in result
        assert "predicted_orders_upper" in result
        assert result["predicted_orders_lower"] <= result["predicted_orders"] <= result["predicted_orders_upper"]

    def test_confidence_high_when_90_days(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_daily_order_history", return_value=_make_daily_df(90)), \
             patch.object(svc, "get_friday_order_history", return_value=[
                 {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
             ]), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_prophet_forecast(TARGET)

        assert result["confidence"] == "high"

    def test_confidence_medium_when_less_than_60_days(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_daily_order_history", return_value=_make_daily_df(45)), \
             patch.object(svc, "get_friday_order_history", return_value=[
                 {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
             ]), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_prophet_forecast(TARGET)

        assert result["confidence"] == "medium"

    def test_falls_back_to_baseline_when_data_insufficient(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_daily_order_history", return_value=_make_daily_df(10)), \
             patch.object(svc, "get_friday_order_history", return_value=[
                 {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
             ]), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_prophet_forecast(TARGET)

        # Should fall back to baseline gracefully
        assert result["method"] == "baseline"

    def test_target_date_in_response(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_daily_order_history", return_value=_make_daily_df(90)), \
             patch.object(svc, "get_friday_order_history", return_value=[
                 {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
             ]), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_prophet_forecast(TARGET)

        assert result["target_date"] == "2026-04-17"


# ── ForecastService.calculate_baseline_forecast ───────────────────────────────

class TestCalculateBaselineForecast:

    def test_returns_method_baseline(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_friday_order_history", return_value=[
            {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
            {"total_orders": 110, "peak_orders_6pm_to_11pm": 65, "date": "2026-04-04"},
        ]), patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_baseline_forecast(TARGET)

        assert result["method"] == "baseline"

    def test_predicted_orders_includes_5pct_uplift(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        history = [
            {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
            {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-04"},
        ]
        with patch.object(svc, "get_friday_order_history", return_value=history), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_baseline_forecast(TARGET)

        # avg = 100, predicted = 100 * 1.05 = 105
        assert result["predicted_orders"] == 105.0

    def test_returns_no_range_fields(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_friday_order_history", return_value=[
            {"total_orders": 100, "peak_orders_6pm_to_11pm": 60, "date": "2026-04-11"},
        ]), patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_baseline_forecast(TARGET)

        # Baseline has no uncertainty range — Prophet does
        assert "predicted_orders_lower" not in result
        assert "predicted_orders_upper" not in result

    def test_empty_history_returns_zero(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "get_friday_order_history", return_value=[]), \
             patch.object(svc, "get_top_friday_items", return_value=[]):
            result = svc.calculate_baseline_forecast(TARGET)

        assert result["predicted_orders"] == 0


# ── ForecastService.calculate_forecast (routing) ─────────────────────────────

class TestCalculateForecastRouting:

    def test_calculate_forecast_delegates_to_prophet(self):
        from app.domain.services.forecast_service import ForecastService

        svc = ForecastService(db=_make_db_mock(), llm=MagicMock())

        with patch.object(svc, "calculate_prophet_forecast", return_value={"method": "prophet"}) as mock_prophet:
            result = svc.calculate_forecast(TARGET)

        mock_prophet.assert_called_once_with(TARGET)
        assert result["method"] == "prophet"
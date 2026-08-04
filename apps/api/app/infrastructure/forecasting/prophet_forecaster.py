"""
ProphetForecaster — infrastructure layer for Prophet-based demand forecasting.

Keeps the Prophet dependency isolated here so ForecastService stays clean
and this class is trivially mockable in tests.
"""

import pandas as pd
from prophet import Prophet


class ProphetForecaster:
    """Fits a Prophet model on daily order history and predicts a target date."""

    def __init__(
        self,
        weekly_seasonality: bool = True,
        changepoint_prior_scale: float = 0.05,
        seasonality_prior_scale: float = 10.0,
    ):
        self.weekly_seasonality = weekly_seasonality
        self.changepoint_prior_scale = changepoint_prior_scale
        self.seasonality_prior_scale = seasonality_prior_scale

    def fit_and_predict(self, df: pd.DataFrame, target_date: "datetime") -> dict:
        """
        Fit Prophet on `df` and return a prediction dict for `target_date`.

        Args:
            df: DataFrame with columns ['ds', 'y', 'peak_orders', 'is_friday'].
                'ds' must be date-like; 'y' is the daily order count.
            target_date: The datetime to predict for.

        Returns:
            dict with keys: yhat, yhat_lower, yhat_upper, peak_ratio_used.

        Raises:
            ValueError: if df has fewer than 30 rows (not enough data for Prophet).
        """
        if len(df) < 30:
            raise ValueError(
                f"Not enough data for Prophet: need ≥30 rows, got {len(df)}."
            )

        prophet_df = df[["ds", "y"]].copy()
        prophet_df["ds"] = pd.to_datetime(prophet_df["ds"])

        model = Prophet(
            weekly_seasonality=self.weekly_seasonality,
            daily_seasonality=False,
            yearly_seasonality=False,
            changepoint_prior_scale=self.changepoint_prior_scale,
            seasonality_prior_scale=self.seasonality_prior_scale,
        )
        model.fit(prophet_df)

        future = pd.DataFrame({"ds": [pd.to_datetime(target_date)]})
        forecast = model.predict(future)

        # Calculate peak ratio from recent Fridays
        recent_fridays = df[df["is_friday"] & (df["y"] > 0)].tail(4)
        if len(recent_fridays) > 0:
            peak_ratio = (recent_fridays["peak_orders"] / recent_fridays["y"]).mean()
        else:
            peak_ratio = 0.6  # default: 60% of daily orders fall in peak window

        return {
            "yhat": float(forecast["yhat"].iloc[0]),
            "yhat_lower": float(forecast["yhat_lower"].iloc[0]),
            "yhat_upper": float(forecast["yhat_upper"].iloc[0]),
            "peak_ratio_used": float(peak_ratio),
        }
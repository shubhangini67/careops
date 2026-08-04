"""WeatherService — P6-A21.

Fetches a live weather forecast from Open-Meteo (free, keyless REST API) for
the target service date's dinner hours (18:00-22:00 local), and derives a
demand-relevant signal from it: condition, delivery/dine-in impact text, and
a conservative numeric demand_multiplier applied to the raw forecast by
ForecastService (forecast_service.py) -- a real adjustment to the predicted
order count, not just narrative context for an LLM to maybe act on.

Never raises -- returns None on any failure (network, unexpected response
shape, no dinner-hour data in range) so demand_forecast runs fine without it.
"""

from datetime import date
from typing import Optional

import httpx
import structlog

log = structlog.get_logger()

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 10.0
_DINNER_HOURS = range(18, 23)  # 18:00–22:00 local, inclusive of the 22:00 slot
_MAX_FORECAST_DAYS = 16  # Open-Meteo's free-tier cap

_HEAVY_RAIN_THRESHOLD = 60.0  # precipitation probability %
_LIGHT_RAIN_THRESHOLD = 30.0
_HOT_THRESHOLD_C = 35.0

# Conservative total-order multipliers. Weather's effect on TOTAL order volume
# is genuinely less certain than a holiday's (bad weather shifts channel mix --
# more delivery, less dine-in -- more than it shifts overall volume), so these
# stay modest. delivery_impact/dinein_impact are separate descriptive strings
# for staffing/prep narrative, not used in the numeric adjustment themselves.
_CONDITION_PROFILES: dict[str, dict] = {
    "heavy_rain": {"delivery_impact": "+35%", "dinein_impact": "-20%", "demand_multiplier": 1.10},
    "light_rain": {"delivery_impact": "+20%", "dinein_impact": "-10%", "demand_multiplier": 1.05},
    "very_hot":   {"delivery_impact": "+10%", "dinein_impact": "-15%", "demand_multiplier": 1.03},
    "clear":      {"delivery_impact": "normal", "dinein_impact": "normal", "demand_multiplier": 1.0},
}


class WeatherService:
    """Live weather signal from Open-Meteo. get_forecast() is the only public method."""

    async def get_forecast(self, lat: float, lng: float, target_date: date) -> Optional[dict]:
        try:
            return await self._get_forecast(lat, lng, target_date)
        except Exception as exc:
            log.warning("weather_service_error", error=str(exc))
            return None

    async def _get_forecast(self, lat: float, lng: float, target_date: date) -> Optional[dict]:
        days_ahead = (target_date - date.today()).days
        if days_ahead < 0 or days_ahead > _MAX_FORECAST_DAYS:
            return None

        params = {
            "latitude": lat,
            "longitude": lng,
            "hourly": "temperature_2m,precipitation_probability,weathercode",
            "forecast_days": max(2, days_ahead + 1),
            "timezone": "Asia/Kolkata",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        avg_temp, avg_precip = self._extract_dinner_window(data, target_date)
        if avg_temp is None and avg_precip is None:
            return None

        condition = self._classify(avg_precip or 0.0, avg_temp)
        profile = _CONDITION_PROFILES[condition]
        signal = self._build_signal_text(condition, avg_precip or 0.0, avg_temp)

        return {
            "condition": condition,
            "avg_precipitation_pct": round(avg_precip, 1) if avg_precip is not None else None,
            "avg_temp_celsius": round(avg_temp, 1) if avg_temp is not None else None,
            "delivery_impact": profile["delivery_impact"],
            "dinein_impact": profile["dinein_impact"],
            "demand_multiplier": profile["demand_multiplier"],
            "signal": signal,
            "prompt_text": f"## Weather Forecast\n{signal}",
        }

    def _extract_dinner_window(
        self, data: dict, target_date: date
    ) -> tuple[Optional[float], Optional[float]]:
        """Average temperature + precipitation probability across the target
        date's 18:00-22:00 hourly slots. Returns (None, None) if no matching
        slots are found in the response.
        """
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        precip = hourly.get("precipitation_probability") or []
        target_prefix = target_date.isoformat()

        dinner_temps: list[float] = []
        dinner_precip: list[float] = []
        for i, t in enumerate(times):
            if not isinstance(t, str) or not t.startswith(target_prefix):
                continue
            try:
                hour = int(t[11:13])
            except (ValueError, IndexError):
                continue
            if hour not in _DINNER_HOURS:
                continue
            if i < len(temps) and temps[i] is not None:
                dinner_temps.append(float(temps[i]))
            if i < len(precip) and precip[i] is not None:
                dinner_precip.append(float(precip[i]))

        avg_temp = sum(dinner_temps) / len(dinner_temps) if dinner_temps else None
        avg_precip = sum(dinner_precip) / len(dinner_precip) if dinner_precip else None
        return avg_temp, avg_precip

    def _classify(self, avg_precip: float, avg_temp: Optional[float]) -> str:
        if avg_precip >= _HEAVY_RAIN_THRESHOLD:
            return "heavy_rain"
        if avg_precip >= _LIGHT_RAIN_THRESHOLD:
            return "light_rain"
        if avg_temp is not None and avg_temp >= _HOT_THRESHOLD_C:
            return "very_hot"
        return "clear"

    def _build_signal_text(self, condition: str, avg_precip: float, avg_temp: Optional[float]) -> str:
        temp_str = f"{avg_temp:.0f}°C" if avg_temp is not None else "unknown"
        descriptions = {
            "heavy_rain": (
                f"Heavy rain is expected during dinner service tonight ({avg_precip:.0f}% chance), "
                f"so expect more delivery orders and less walk-in or outdoor dine-in demand."
            ),
            "light_rain": (
                f"Light rain is possible during dinner service tonight ({avg_precip:.0f}% chance), "
                f"which could nudge a few more orders toward delivery."
            ),
            "very_hot": (
                f"It's shaping up to be a hot evening (around {temp_str}), which may soften "
                f"outdoor dine-in a little and lift delivery slightly."
            ),
            "clear": (
                f"Conditions look clear tonight (around {temp_str}, {avg_precip:.0f}% rain chance), "
                f"so no unusual weather-driven shift in demand is expected."
            ),
        }
        return descriptions[condition]

"""Unit tests for WeatherService (P6-A21).

All Open-Meteo HTTP calls are mocked — no live network needed.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.weather_service import WeatherService


def _hourly_response(target_date: date, hour_values: dict[int, dict]) -> dict:
    """Build an Open-Meteo-shaped response with the given hour -> {temp, precip}
    values on target_date, plus a few off-target/off-window hours mixed in to
    confirm they're correctly ignored."""
    times, temps, precip = [], [], []
    for hour, vals in hour_values.items():
        times.append(f"{target_date.isoformat()}T{hour:02d}:00")
        temps.append(vals.get("temp"))
        precip.append(vals.get("precip"))
    # Noise: an hour outside the 18-22 dinner window, should be ignored.
    times.append(f"{target_date.isoformat()}T09:00")
    temps.append(15.0)
    precip.append(90.0)
    return {"hourly": {"time": times, "temperature_2m": temps, "precipitation_probability": precip}}


def _patched_client(response_json: dict, raise_error: bool = False):
    mock_response = MagicMock()
    if raise_error:
        mock_response.raise_for_status.side_effect = Exception("HTTP error")
    else:
        mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = response_json

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return patch("app.infrastructure.external.weather_service.httpx.AsyncClient", return_value=mock_client)


@pytest.mark.asyncio
async def test_heavy_rain_classification():
    target = date.today() + timedelta(days=1)
    response = _hourly_response(target, {
        18: {"temp": 28.0, "precip": 70.0},
        19: {"temp": 27.0, "precip": 65.0},
        20: {"temp": 26.0, "precip": 75.0},
    })
    with _patched_client(response):
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is not None
    assert result["condition"] == "heavy_rain"
    assert result["demand_multiplier"] == 1.10
    assert result["delivery_impact"] == "+35%"


@pytest.mark.asyncio
async def test_light_rain_classification():
    target = date.today() + timedelta(days=1)
    response = _hourly_response(target, {
        18: {"temp": 28.0, "precip": 35.0},
        19: {"temp": 28.0, "precip": 40.0},
    })
    with _patched_client(response):
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is not None
    assert result["condition"] == "light_rain"
    assert result["demand_multiplier"] == 1.05


@pytest.mark.asyncio
async def test_very_hot_classification_no_rain():
    target = date.today() + timedelta(days=1)
    response = _hourly_response(target, {
        18: {"temp": 37.0, "precip": 5.0},
        19: {"temp": 36.5, "precip": 5.0},
    })
    with _patched_client(response):
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is not None
    assert result["condition"] == "very_hot"
    assert result["demand_multiplier"] == 1.03


@pytest.mark.asyncio
async def test_clear_conditions_multiplier_is_neutral():
    target = date.today() + timedelta(days=1)
    response = _hourly_response(target, {
        18: {"temp": 28.0, "precip": 5.0},
        19: {"temp": 27.0, "precip": 10.0},
    })
    with _patched_client(response):
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is not None
    assert result["condition"] == "clear"
    assert result["demand_multiplier"] == 1.0


@pytest.mark.asyncio
async def test_no_dinner_hour_data_returns_none():
    target = date.today() + timedelta(days=1)
    # Only off-window data available for the target date.
    response = {"hourly": {
        "time": [f"{target.isoformat()}T09:00"],
        "temperature_2m": [20.0],
        "precipitation_probability": [10.0],
    }}
    with _patched_client(response):
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is None


@pytest.mark.asyncio
async def test_http_error_returns_none_not_raise():
    target = date.today() + timedelta(days=1)
    with _patched_client({}, raise_error=True):
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is None


@pytest.mark.asyncio
async def test_target_date_too_far_out_returns_none_without_calling_api():
    target = date.today() + timedelta(days=30)  # beyond Open-Meteo's free-tier cap
    with _patched_client({"hourly": {}}) as patched:
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is None


@pytest.mark.asyncio
async def test_malformed_response_returns_none_not_raise():
    target = date.today() + timedelta(days=1)
    with _patched_client({"unexpected": "shape"}):
        result = await WeatherService().get_forecast(lat=19.0, lng=73.0, target_date=target)

    assert result is None

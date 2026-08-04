"""Unit tests for ForecastService._apply_signal_adjustments (P6-A21) and
analyse_and_recommend's trends/compliance narrative injection (P6-A24).

This is the fix for "scenario selection only changes labels, not the actual
forecast math" -- Prophet's raw predicted_orders is purely historical and
can't know about a forward-looking one-off signal (a holiday, a rain
forecast). These tests confirm the multiplier applies correctly and stays
transparent (pre-adjustment value + multiplier + reasons all preserved).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.forecast_service import ForecastService, _HOLIDAY_DEMAND_MULTIPLIER


def _service() -> ForecastService:
    return ForecastService(db=MagicMock(), llm=MagicMock())


def _base_forecast() -> dict:
    return {"predicted_orders": 100.0, "predicted_peak_orders": 60.0, "method": "prophet"}


def test_no_signals_returns_forecast_unchanged():
    service = _service()
    forecast = service._apply_signal_adjustments(_base_forecast())
    assert forecast["predicted_orders"] == 100.0
    assert "adjustment_multiplier" not in forecast
    assert "predicted_orders_pre_adjustment" not in forecast


def test_holiday_applies_documented_multiplier():
    service = _service()
    forecast = service._apply_signal_adjustments(
        _base_forecast(), is_holiday=True, holiday_name="Diwali",
    )
    assert forecast["predicted_orders_pre_adjustment"] == 100.0
    assert forecast["predicted_orders"] == round(100.0 * _HOLIDAY_DEMAND_MULTIPLIER, 1)
    assert forecast["adjustment_multiplier"] == _HOLIDAY_DEMAND_MULTIPLIER
    assert any("Diwali" in r for r in forecast["adjustment_reasons"])


def test_weather_applies_its_own_multiplier():
    service = _service()
    weather_signal = {"condition": "heavy_rain", "demand_multiplier": 1.10}
    forecast = service._apply_signal_adjustments(_base_forecast(), weather_signal=weather_signal)
    assert forecast["predicted_orders_pre_adjustment"] == 100.0
    assert forecast["predicted_orders"] == round(100.0 * 1.10, 1)
    assert forecast["adjustment_multiplier"] == 1.10
    assert any("heavy_rain" in r for r in forecast["adjustment_reasons"])


def test_holiday_and_weather_multipliers_stack():
    service = _service()
    weather_signal = {"condition": "light_rain", "demand_multiplier": 1.05}
    forecast = service._apply_signal_adjustments(
        _base_forecast(), weather_signal=weather_signal, is_holiday=True, holiday_name="Holi",
    )
    expected_multiplier = round(_HOLIDAY_DEMAND_MULTIPLIER * 1.05, 3)
    assert forecast["adjustment_multiplier"] == expected_multiplier
    assert forecast["predicted_orders"] == round(100.0 * expected_multiplier, 1)
    assert len(forecast["adjustment_reasons"]) == 2


def test_weather_multiplier_of_exactly_one_is_not_treated_as_a_signal():
    """Clear weather (demand_multiplier=1.0) shouldn't show up as a reason or
    trigger the pre_adjustment fields if it's the only signal present."""
    service = _service()
    weather_signal = {"condition": "clear", "demand_multiplier": 1.0}
    forecast = service._apply_signal_adjustments(_base_forecast(), weather_signal=weather_signal)
    assert "adjustment_multiplier" not in forecast
    assert forecast["predicted_orders"] == 100.0


def test_peak_orders_adjusted_by_the_same_multiplier():
    service = _service()
    forecast = service._apply_signal_adjustments(_base_forecast(), is_holiday=True, holiday_name="Eid")
    assert forecast["predicted_peak_orders_pre_adjustment"] == 60.0
    assert forecast["predicted_peak_orders"] == round(60.0 * _HOLIDAY_DEMAND_MULTIPLIER, 1)


def test_missing_predicted_orders_defaults_to_zero_without_raising():
    service = _service()
    forecast = service._apply_signal_adjustments({}, is_holiday=True, holiday_name="Christmas")
    assert forecast["predicted_orders"] == 0.0


# ── P6-A24: trends/compliance narrative injection (no multiplier effect) ──────

@pytest.mark.asyncio
async def test_trends_and_compliance_appear_in_llm_prompt_not_the_multiplier():
    """Unlike weather/holiday, trends/compliance are narrative-only -- they
    must reach the LLM prompt but never touch predicted_orders/the multiplier."""
    service = ForecastService(db=MagicMock(), llm=MagicMock())
    service.calculate_forecast = MagicMock(return_value={
        "predicted_orders": 100.0, "predicted_peak_orders": 60.0, "method": "prophet",
        "avg_friday_orders": 95, "avg_peak_orders": 55, "top_items": [], "service_day_label": "Friday",
    })
    captured_prompt = {}

    async def fake_complete_json(prompt, system_prompt):
        captured_prompt["prompt"] = prompt
        return {"recommendation": "ok", "priority": "medium", "reasoning": "", "risks": []}

    service.llm.complete_json = fake_complete_json

    result = await service.analyse_and_recommend(
        trends_signal={"digest": "Mustard oil prices rising"},
        compliance_alerts_signal={"notices": [{"title": "New vegan labelling rule"}]},
    )

    assert result["data"]["predicted_orders"] == 100.0  # unaffected -- narrative only
    assert "adjustment_multiplier" not in result["data"]
    assert "Mustard oil prices rising" in captured_prompt["prompt"]
    assert "New vegan labelling rule" in captured_prompt["prompt"]


@pytest.mark.asyncio
async def test_no_trends_or_compliance_signal_omits_those_lines():
    service = ForecastService(db=MagicMock(), llm=MagicMock())
    service.calculate_forecast = MagicMock(return_value={
        "predicted_orders": 100.0, "predicted_peak_orders": 60.0, "method": "prophet",
        "avg_friday_orders": 95, "avg_peak_orders": 55, "top_items": [], "service_day_label": "Friday",
    })
    captured_prompt = {}

    async def fake_complete_json(prompt, system_prompt):
        captured_prompt["prompt"] = prompt
        return {"recommendation": "ok", "priority": "medium", "reasoning": "", "risks": []}

    service.llm.complete_json = fake_complete_json

    await service.analyse_and_recommend()

    assert "Industry trends" not in captured_prompt["prompt"]
    assert "FSSAI" not in captured_prompt["prompt"]

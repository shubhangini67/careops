"""Unit tests for LiveScenarioComposer -- backs the "Run for today" instant
path. All DB, Swiggy, and LLM calls are mocked -- no live infra needed.

The core regression this file guards against: ScenarioRecommender's fallback
(and its LLM path, live-verified) recommends "low_stock_weekend" purely off
shortage count, regardless of actual day-of-week -- see
test_scenario_recommender.py::test_recommends_low_stock_weekend_when_many_shortages,
which literally asserts that as expected behavior for ScenarioRecommender.
LiveScenarioComposer exists specifically because that's wrong for the
"right now" case; these tests confirm it never reproduces that bug.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.live_scenario_composer import LiveScenarioComposer


def _composer(llm_response=None, llm_side_effect=None, shortage_count=0):
    db = MagicMock()
    swiggy_client = MagicMock()
    swiggy_client.is_available.return_value = False  # skip market-context branch entirely
    llm = MagicMock()
    llm.complete_json = (
        AsyncMock(side_effect=llm_side_effect)
        if llm_side_effect
        else AsyncMock(return_value=llm_response or {})
    )

    composer = LiveScenarioComposer(db=db, swiggy_client=swiggy_client, llm=llm)
    composer._shortage_count = AsyncMock(return_value=shortage_count)
    composer._get_weather_signal = AsyncMock(return_value=None)
    return composer


@pytest.mark.asyncio
async def test_fallback_never_mislabels_a_weekday_as_a_weekend():
    """The exact bug found live: heavy shortages on a plain Wednesday must
    never produce a label containing "weekend" -- unlike ScenarioRecommender's
    fallback, which does exactly that."""
    composer = _composer(llm_side_effect=RuntimeError("LLM down"), shortage_count=5)
    with patch("app.domain.services.live_scenario_composer.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await composer.compose(org_id=1, target_date="2026-07-08")  # a Wednesday

    label = result["profile"]["label"]
    assert "weekend" not in label.lower()
    assert "wednesday" in label.lower()
    assert result["profile"]["id"] == "live-composed"


@pytest.mark.asyncio
async def test_fallback_reflects_actual_weekend_when_true():
    composer = _composer(llm_side_effect=RuntimeError("LLM down"), shortage_count=0)
    with patch("app.domain.services.live_scenario_composer.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await composer.compose(org_id=1, target_date="2026-07-11")  # a Saturday

    assert "saturday" in result["profile"]["label"].lower()


@pytest.mark.asyncio
async def test_fallback_uses_holiday_name_not_weekday_or_weekend():
    composer = _composer(llm_side_effect=RuntimeError("LLM down"), shortage_count=0)
    with patch("app.domain.services.live_scenario_composer.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await composer.compose(org_id=1, target_date="2026-11-08")  # Diwali

    label = result["profile"]["label"].lower()
    assert "weekend" not in label
    assert "diwali" in label or "holiday" in label


@pytest.mark.asyncio
async def test_llm_success_path_returns_composed_profile():
    composer = _composer(llm_response={
        "label": "Wednesday Dinner Service",
        "service_window": "18:00-22:00",
        "operational_focus": "Light rain expected; manage the 3 ingredient shortages carefully.",
        "reason": "Weekday evening with shortages and rain, not a special event.",
        "confidence": "high",
    })
    with patch("app.domain.services.live_scenario_composer.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await composer.compose(org_id=1, target_date="2026-07-08")

    assert result["profile"]["label"] == "Wednesday Dinner Service"
    assert result["profile"]["service_window"] == "18:00-22:00"
    assert result["confidence"] == "high"
    assert result["profile"]["id"] == "live-composed"


@pytest.mark.asyncio
async def test_falls_back_on_malformed_llm_service_window():
    composer = _composer(llm_response={
        "label": "Something",
        "service_window": "not-a-time-range",
        "operational_focus": "focus",
    })
    with patch("app.domain.services.live_scenario_composer.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await composer.compose(org_id=1, target_date="2026-07-08")

    # Falls back to the deterministic, signal-grounded profile instead of
    # propagating the malformed LLM output.
    assert result["confidence"] == "low"
    assert "weekend" not in result["profile"]["label"].lower()


@pytest.mark.asyncio
async def test_never_raises_when_run_service_itself_fails():
    composer = _composer(llm_response={"label": "x", "service_window": "18:00-22:00", "operational_focus": "y"})
    with patch("app.domain.services.live_scenario_composer.RunService") as mock_run_service:
        mock_run_service.side_effect = RuntimeError("DB down")
        result = await composer.compose(org_id=1, target_date="2026-07-08")

    assert "profile" in result
    assert result["profile"]["label"]


class TestFallbackTimeBuckets:
    """_fallback() is called directly here (same pattern the existing
    ScenarioRecommender tests use for private helpers) to pin down the
    time-of-day -> service-window mapping without needing to mock
    datetime.now()."""

    def setup_method(self):
        db = MagicMock()
        swiggy_client = MagicMock()
        llm = MagicMock()
        self.composer = LiveScenarioComposer(db=db, swiggy_client=swiggy_client, llm=llm)

    def test_morning_maps_to_full_day(self):
        result = self.composer._fallback("2026-07-08", is_weekend=False, current_time_str="09:30")
        assert result["profile"]["service_window"] == "11:00-22:00"

    def test_midday_maps_to_lunch(self):
        result = self.composer._fallback("2026-07-08", is_weekend=False, current_time_str="13:00")
        assert result["profile"]["service_window"] == "12:00-15:00"
        assert "lunch" in result["profile"]["label"].lower()

    def test_evening_maps_to_dinner(self):
        result = self.composer._fallback("2026-07-08", is_weekend=False, current_time_str="19:45")
        assert result["profile"]["service_window"] == "18:00-22:00"
        assert "dinner" in result["profile"]["label"].lower()

"""Unit tests for ScenarioRecommender (P6-MI10).

All DB, Swiggy, and LLM calls are mocked — no live infra needed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.scenario_recommender import ScenarioRecommender


def _recommender(llm_response=None, llm_side_effect=None, shortage_count=0):
    db = MagicMock()
    swiggy_client = MagicMock()
    swiggy_client.is_available.return_value = False  # skip market-context branch entirely
    llm = MagicMock()
    llm.complete_json = (
        AsyncMock(side_effect=llm_side_effect)
        if llm_side_effect
        else AsyncMock(return_value=llm_response or {})
    )

    recommender = ScenarioRecommender(db=db, swiggy_client=swiggy_client, llm=llm)
    recommender._shortage_count = AsyncMock(return_value=shortage_count)
    return recommender


@pytest.mark.asyncio
async def test_recommends_holiday_spike_on_known_holiday():
    recommender = _recommender(
        llm_response={"recommended_scenario": "holiday_spike", "reason": "Diwali tonight", "confidence": "high"},
    )
    with patch("app.domain.services.scenario_recommender.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await recommender.recommend(org_id=1, target_date="2026-11-08")  # Diwali

    assert result["recommended_scenario"] == "holiday_spike"
    assert "holiday_detected" in result["signals_used"]
    assert result["confidence"] == "high"


@pytest.mark.asyncio
async def test_recommends_low_stock_weekend_when_many_shortages():
    """LLM returns an invalid scenario id -- fallback logic kicks in and should
    pick low_stock_weekend given the high shortage count."""
    recommender = _recommender(
        llm_response={"recommended_scenario": "not_a_real_scenario"},
        shortage_count=5,
    )
    with patch("app.domain.services.scenario_recommender.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await recommender.recommend(org_id=1, target_date="2026-07-08")  # a regular Wednesday

    assert result["recommended_scenario"] == "low_stock_weekend"
    assert "shortage_count:5" in result["signals_used"]


@pytest.mark.asyncio
async def test_recommends_friday_rush_on_high_occupancy_weekend():
    recommender = _recommender(
        llm_response={
            "recommended_scenario": "friday_rush",
            "reason": "Weekend with elevated dinner demand",
            "confidence": "medium",
        },
    )
    with patch("app.domain.services.scenario_recommender.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await recommender.recommend(org_id=1, target_date="2026-07-11")  # a Saturday

    assert result["recommended_scenario"] == "friday_rush"
    assert "weekend_detected" in result["signals_used"]


@pytest.mark.asyncio
async def test_falls_back_gracefully_when_llm_raises():
    recommender = _recommender(llm_side_effect=RuntimeError("LLM down"))
    with patch("app.domain.services.scenario_recommender.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await recommender.recommend(org_id=1, target_date="2026-07-08")

    assert result["recommended_scenario"] in {
        "friday_rush", "weekday_lunch", "holiday_spike", "low_stock_weekend",
    }
    assert result["confidence"] == "low"


@pytest.mark.asyncio
async def test_fallback_picks_weekday_lunch_for_regular_weekday_no_shortages():
    recommender = _recommender(llm_side_effect=RuntimeError("LLM down"), shortage_count=0)
    with patch("app.domain.services.scenario_recommender.RunService") as mock_run_service:
        mock_run_service.return_value.list_runs.return_value = []
        result = await recommender.recommend(org_id=1, target_date="2026-07-08")  # Wednesday

    assert result["recommended_scenario"] == "weekday_lunch"


@pytest.mark.asyncio
async def test_never_raises_when_run_service_itself_fails():
    recommender = _recommender(llm_response={"recommended_scenario": "friday_rush"})
    with patch("app.domain.services.scenario_recommender.RunService") as mock_run_service:
        mock_run_service.side_effect = RuntimeError("DB down")
        result = await recommender.recommend(org_id=1, target_date="2026-07-08")

    assert result["recommended_scenario"] in {
        "friday_rush", "weekday_lunch", "holiday_spike", "low_stock_weekend",
    }

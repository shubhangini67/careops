"""Unit tests for live_signals_node -- the new first-node extraction of
weather/holiday, industry trends, and regulatory-alert fetching that used
to live inline inside demand_forecast_node.

Run with:
    cd apps/api && pytest tests/unit/test_live_signals_node.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestLiveSignalsNode:

    @pytest.mark.asyncio
    async def test_short_circuits_on_error(self, errored_state):
        from app.orchestration.nodes.live_signals import live_signals_node

        result = await live_signals_node(errored_state)
        assert result["error"] == "Upstream failure"
        assert result["weather_signal"] is None

    @pytest.mark.asyncio
    async def test_simulation_mode_never_fetches(self, sim_state):
        """Matches demand_forecast_node's pre-extraction behavior -- simulation
        mode must never make real external calls (Open-Meteo/RSS/FSSAI)."""
        from app.orchestration.nodes.live_signals import live_signals_node

        with patch("app.orchestration.nodes.live_signals.WeatherService") as MockWeather, patch(
            "app.orchestration.nodes.live_signals.TrendsService"
        ) as MockTrends, patch(
            "app.orchestration.nodes.live_signals.ComplianceAlertsService"
        ) as MockCompliance:
            result = await live_signals_node(sim_state)

        MockWeather.assert_not_called()
        MockTrends.assert_not_called()
        MockCompliance.assert_not_called()
        assert result["weather_signal"] is None
        assert result["trends_signal"] is None
        assert result["compliance_alerts_signal"] is None

    @pytest.mark.asyncio
    async def test_fetches_all_three_signals_and_holiday_context(self, base_state):
        from app.orchestration.nodes.live_signals import live_signals_node

        weather = {"condition": "clear", "prompt_text": "## Weather\nClear"}
        trends = {"digest": "- Mustard prices up", "prompt_text": "## Industry Trends\n- Mustard prices up"}
        compliance = {"notices": [{"title": "Vegan labelling rule"}], "prompt_text": "## Regulatory Alerts (FSSAI)\n- Vegan labelling rule"}

        with patch("app.orchestration.nodes.live_signals.WeatherService") as MockWeather, patch(
            "app.orchestration.nodes.live_signals.TrendsService"
        ) as MockTrends, patch(
            "app.orchestration.nodes.live_signals.ComplianceAlertsService"
        ) as MockCompliance:
            MockWeather.return_value.get_forecast = AsyncMock(return_value=weather)
            MockTrends.return_value.get_digest = AsyncMock(return_value=trends)
            MockCompliance.return_value.get_alerts = AsyncMock(return_value=compliance)
            result = await live_signals_node(base_state)

        assert result["weather_signal"] == weather
        assert result["trends_signal"] == trends
        assert result["compliance_alerts_signal"] == compliance
        # base_state's target_date (2026-04-11) is a Saturday, not a configured
        # holiday -- just confirm the shape, not a specific value.
        assert "is_holiday" in result["holiday_context"]
        assert "holiday_name" in result["holiday_context"]

    @pytest.mark.asyncio
    async def test_no_target_date_skips_weather_but_still_fetches_trends_and_compliance(self):
        """Weather needs a target_date (dinner-window extraction); trends and
        compliance don't depend on it at all."""
        from app.orchestration.nodes.live_signals import live_signals_node
        from app.orchestration.state import make_initial_state

        state = make_initial_state("friday_rush", target_date=None, simulation_mode=False)
        trends = {"digest": "trend", "prompt_text": "text"}
        compliance = {"notices": [], "prompt_text": "text"}

        with patch("app.orchestration.nodes.live_signals.WeatherService") as MockWeather, patch(
            "app.orchestration.nodes.live_signals.TrendsService"
        ) as MockTrends, patch(
            "app.orchestration.nodes.live_signals.ComplianceAlertsService"
        ) as MockCompliance:
            MockTrends.return_value.get_digest = AsyncMock(return_value=trends)
            MockCompliance.return_value.get_alerts = AsyncMock(return_value=compliance)
            result = await live_signals_node(state)

        MockWeather.assert_not_called()
        assert result["weather_signal"] is None
        assert result["trends_signal"] == trends
        assert result["compliance_alerts_signal"] == compliance

    @pytest.mark.asyncio
    async def test_fails_open_on_unexpected_exception(self, base_state):
        """Even though WeatherService/TrendsService/ComplianceAlertsService are
        each independently fail-open internally, this node must never let an
        unexpected exception propagate and take down the whole graph run."""
        from app.orchestration.nodes.live_signals import live_signals_node

        with patch(
            "app.orchestration.nodes.live_signals.WeatherService",
            side_effect=RuntimeError("boom"),
        ):
            result = await live_signals_node(base_state)

        assert result["weather_signal"] is None
        assert result["trends_signal"] is None
        assert result["compliance_alerts_signal"] is None
        assert result["holiday_context"] is None
        assert result.get("error") is None  # node-level failure, not a state-level error

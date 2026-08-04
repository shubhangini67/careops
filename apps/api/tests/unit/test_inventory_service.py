"""
Unit tests for InventoryService — P2-02 acceptance criteria.

Covers:
- compute_alerts: shortage detection, overstock detection, severity escalation
  on high demand, severity escalation on spoilage_risk, demand_ratio calculation
- analyse_and_recommend: calls LLM, returns correct structure
- inventory_node: simulation mode, production mode, error handling, debug trace

All tests are pure unit tests — no real DB or LLM.

Run with:
    cd apps/api && pytest tests/unit/test_inventory_service.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_item(
    name="Mozzarella",
    unit="kg",
    stock=3.0,
    threshold=8.0,
    spoilage=False,
):
    item = MagicMock()
    item.ingredient_name   = name
    item.unit              = unit
    item.quantity_in_stock = stock
    item.reorder_threshold = threshold
    item.spoilage_risk     = spoilage
    return item


def _make_db(items: list):
    db = MagicMock()
    db.query.return_value.all.return_value = items
    return db


def _make_llm(response: dict | None = None):
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value=response or {
        "restock_actions":        ["Order 10kg Mozzarella"],
        "waste_reduction_actions": [],
        "priority":               "high",
        "reasoning":              "Critical shortage.",
        "risks":                  ["Cannot fulfil orders"],
    })
    return llm


async def _analyse(svc, forecast_data=None, scenario_profile=None, procurement_context=None):
    """Compose compute_shortage_data + generate_recommendation, mirroring the
    old combined analyse_and_recommend() call shape for these tests. The two
    are deliberately separate now — see inventory_node.py — so a caller can
    fetch procurement prices for the real shortage list in between."""
    shortage_data = await svc.compute_shortage_data(
        forecast_data=forecast_data, scenario_profile=scenario_profile,
    )
    return await svc.generate_recommendation(shortage_data, procurement_context=procurement_context)


# ── InventoryService.compute_alerts ──────────────────────────────────────────

class TestComputeAlerts:

    def test_shortage_detected_below_threshold(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=3.0, threshold=8.0)]
        result = svc.compute_alerts(items)

        assert len(result["shortage_alerts"]) == 1
        assert result["shortage_alerts"][0]["ingredient"] == "Mozzarella"
        assert result["shortage_alerts"][0]["shortfall"] == 5.0

    def test_no_alert_when_stock_above_threshold(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=10.0, threshold=8.0)]
        result = svc.compute_alerts(items)

        assert result["shortage_alerts"]  == []
        assert result["overstock_alerts"] == []

    def test_overstock_detected_above_multiplier(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        # threshold=8, multiplier=3 → overstock if stock > 24
        items = [_make_item(stock=30.0, threshold=8.0)]
        result = svc.compute_alerts(items)

        assert len(result["overstock_alerts"]) == 1
        assert result["overstock_alerts"][0]["excess"] == round(30.0 - 8.0 * 3.0, 2)

    def test_shortage_severity_warning_on_normal_demand(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=3.0, threshold=8.0, spoilage=False)]
        result = svc.compute_alerts(items, demand_ratio=1.0)

        assert result["shortage_alerts"][0]["severity"] == "warning"

    def test_shortage_severity_critical_on_high_demand(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=3.0, threshold=8.0, spoilage=False)]
        result = svc.compute_alerts(items, demand_ratio=1.2)  # above 1.15 threshold

        assert result["shortage_alerts"][0]["severity"] == "critical"

    def test_shortage_severity_critical_on_spoilage_risk(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=3.0, threshold=8.0, spoilage=True)]
        result = svc.compute_alerts(items, demand_ratio=1.0)

        assert result["shortage_alerts"][0]["severity"] == "critical"

    def test_overstock_severity_warning_when_spoilage(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=30.0, threshold=8.0, spoilage=True)]
        result = svc.compute_alerts(items)

        assert result["overstock_alerts"][0]["severity"] == "warning"

    def test_overstock_severity_info_without_spoilage(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=30.0, threshold=8.0, spoilage=False)]
        result = svc.compute_alerts(items)

        assert result["overstock_alerts"][0]["severity"] == "info"

    def test_high_demand_flag_set_correctly(self):
        from app.domain.services.inventory_service import InventoryService

        svc = InventoryService(db=_make_db([]), llm=_make_llm())

        assert svc.compute_alerts([], demand_ratio=1.15)["high_demand_week"] is True
        assert svc.compute_alerts([], demand_ratio=1.14)["high_demand_week"] is False

    def test_total_items_checked(self):
        from app.domain.services.inventory_service import InventoryService

        svc   = InventoryService(db=_make_db([]), llm=_make_llm())
        items = [_make_item(stock=10.0, threshold=8.0) for _ in range(5)]
        result = svc.compute_alerts(items)

        assert result["total_items_checked"] == 5

    def test_scenario_projection_makes_low_stock_weekend_harsher_than_weekday_lunch(self):
        from app.domain.services.inventory_service import InventoryService

        mozzarella = _make_item(name="Mozzarella Cheese", stock=3.5, threshold=8.0, spoilage=True)
        svc = InventoryService(db=_make_db([]), llm=_make_llm())

        lunch_projection = svc.project_stock_for_scenario(
            [mozzarella],
            scenario_profile={"id": "weekday_lunch"},
            demand_ratio=1.0,
        )[0]
        low_stock_projection = svc.project_stock_for_scenario(
            [mozzarella],
            scenario_profile={"id": "low_stock_weekend"},
            demand_ratio=1.0,
        )[0]

        assert low_stock_projection.quantity_in_stock < lunch_projection.quantity_in_stock
        assert "weekend" in low_stock_projection.scenario_adjustment_reason.lower()


# ── InventoryService.analyse_and_recommend ───────────────────────────────────

class TestAnalyseAndRecommend:

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self):
        from app.domain.services.inventory_service import InventoryService

        items = [_make_item(stock=3.0, threshold=8.0)]
        svc   = InventoryService(db=_make_db(items), llm=_make_llm())
        result = await _analyse(svc)

        assert result["service"] == "inventory"
        assert "data" in result
        assert "recommendation" in result

    @pytest.mark.asyncio
    async def test_demand_ratio_derived_from_forecast(self):
        from app.domain.services.inventory_service import InventoryService

        items = [_make_item(stock=3.0, threshold=8.0, spoilage=False)]
        svc   = InventoryService(db=_make_db(items), llm=_make_llm())

        forecast_data = {"predicted_orders": 130.0, "avg_friday_orders": 100.0}
        result = await _analyse(svc, forecast_data=forecast_data)

        # ratio = 1.3 → high demand → severity should be critical
        assert result["data"]["shortage_alerts"][0]["severity"] == "critical"
        assert result["data"]["demand_ratio"] == 1.3

    @pytest.mark.asyncio
    async def test_graceful_when_no_forecast(self):
        from app.domain.services.inventory_service import InventoryService

        svc    = InventoryService(db=_make_db([]), llm=_make_llm())
        result = await _analyse(svc, forecast_data=None)

        assert result["service"] == "inventory"
        assert result["data"]["demand_ratio"] == 1.0

    @pytest.mark.asyncio
    async def test_llm_called_once(self):
        from app.domain.services.inventory_service import InventoryService

        llm  = _make_llm()
        svc  = InventoryService(db=_make_db([]), llm=llm)
        await _analyse(svc)

        llm.complete_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_prompt_includes_actionable_restock_caps(self):
        from app.domain.services.inventory_service import InventoryService

        item = _make_item(stock=3.0, threshold=8.0, spoilage=True)
        llm = _make_llm()
        svc = InventoryService(db=_make_db([item]), llm=llm)

        await _analyse(svc, 
            forecast_data={"predicted_orders": 130.0, "avg_friday_orders": 100.0}
        )

        prompt = llm.complete_json.await_args.kwargs["prompt"]
        assert "recommended_restock=6.87" in prompt
        assert "max_actionable_restock=20.61" in prompt
        assert "Prioritize critical shortages first" in prompt

    @pytest.mark.asyncio
    async def test_returned_restock_actions_are_capped_even_if_llm_overorders(self):
        from app.domain.services.inventory_service import InventoryService

        garlic = _make_item(name="Garlic", unit="kg", stock=0.8, threshold=1.5, spoilage=True)
        basil = _make_item(name="Fresh Basil", unit="kg", stock=0.4, threshold=1.0, spoilage=True)
        llm = _make_llm(
            response={
                "restock_actions": [
                    "Order 20kg Garlic immediately",
                    "Order 15kg Fresh Basil immediately",
                ],
                "waste_reduction_actions": [],
                "priority": "high",
                "reasoning": "Model tried to over-order.",
                "risks": ["Stockout risk"],
            }
        )
        svc = InventoryService(db=_make_db([garlic, basil]), llm=llm)

        result = await _analyse(svc, 
            forecast_data={"predicted_orders": 130.0, "avg_friday_orders": 100.0}
        )

        actions = result["recommendation"]["restock_actions"]
        assert (
            "Order 1.05kg Garlic immediately "
            "(covers 1.05kg shortfall; current stock 0.45kg)."
        ) in actions
        assert (
            "Order 0.83kg Fresh Basil immediately "
            "(covers 0.83kg shortfall; current stock 0.17kg)."
        ) in actions
        assert all("20kg" not in action and "15kg" not in action for action in actions)

    @pytest.mark.asyncio
    async def test_guardrailed_restock_actions_keep_swiggy_price_citation(self):
        """Regression guard: build_capped_restock_actions() used to discard
        the LLM's price citation entirely, since it rebuilt restock_actions
        from shortage_alerts alone with no access to procurement_context —
        so even a correct prompt/LLM output could never survive the guardrail
        merge that runs afterward."""
        from app.domain.services.inventory_service import InventoryService

        mozzarella = _make_item(name="Mozzarella", unit="kg", stock=0.41, threshold=8.0, spoilage=True)
        svc = InventoryService(db=_make_db([mozzarella]), llm=_make_llm())

        procurement_context = {
            "procurement_options": [
                {"ingredient": "Mozzarella", "unit": "140 g", "price": 93.0, "spinId": "spin_1", "inStock": True},
            ],
        }
        result = await _analyse(svc, procurement_context=procurement_context)

        actions = result["recommendation"]["restock_actions"]
        assert any("Mozzarella" in a and "Swiggy Instamart" in a and "Rs.93" in a for a in actions), actions

    def test_inventory_language_normalization_rewrites_non_friday_text(self):
        from app.domain.services.inventory_service import InventoryService

        svc = InventoryService(db=_make_db([]), llm=_make_llm())
        normalized = svc.normalize_scenario_language(
            {
                "reasoning": "Restock before Friday rush to meet Friday's demand.",
                "risks": ["Friday service may stock out."],
            },
            scenario_label="Low-Stock Weekend",
        )

        assert "Friday" not in normalized["reasoning"]
        assert "Low-Stock Weekend" in normalized["reasoning"]
        assert "Friday" not in normalized["risks"][0]


# ── inventory_node ────────────────────────────────────────────────────────────

class TestInventoryNode:

    @pytest.mark.asyncio
    async def test_simulation_mode_returns_deterministic_output(self, sim_state, mock_db_factory, mock_llm):
        from app.orchestration.nodes.inventory import inventory_node

        result = await inventory_node(sim_state, db_factory=mock_db_factory, llm=mock_llm)

        output = result["inventory_output"]
        assert output["service"] == "inventory"
        assert len(output["data"]["shortage_alerts"]) == 1
        assert output["data"]["shortage_alerts"][0]["ingredient"] == "Mozzarella"
        mock_llm.complete_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_short_circuits_on_error(self, errored_state, mock_db_factory, mock_llm):
        from app.orchestration.nodes.inventory import inventory_node

        result = await inventory_node(errored_state, db_factory=mock_db_factory, llm=mock_llm)
        assert result.get("inventory_output") is None
        assert result["error"] == "Upstream failure"

    @pytest.mark.asyncio
    async def test_production_mode_calls_inventory_service(self, base_state, mock_db_factory, mock_llm):
        from app.orchestration.nodes.inventory import inventory_node

        mock_result = {
            "service": "inventory",
            "data":    {"shortage_alerts": [], "overstock_alerts": []},
            "recommendation": {"action": "All good."},
        }

        with patch(
            "app.orchestration.nodes.inventory.InventoryService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.compute_shortage_data = AsyncMock(return_value={"actionable_shortages": []})
            mock_svc.generate_recommendation = AsyncMock(return_value=mock_result)
            result = await inventory_node(base_state, db_factory=mock_db_factory, llm=mock_llm)

        assert result["inventory_output"]["service"] == "inventory"

    @pytest.mark.asyncio
    async def test_forecast_data_passed_to_service(self, base_state, mock_db_factory, mock_llm):
        from app.orchestration.nodes.inventory import inventory_node

        state_with_forecast = {
            **base_state,
            "forecast_output": {
                "service": "forecast",
                "data": {"predicted_orders": 130.0, "avg_friday_orders": 100.0},
                "recommendation": {},
            },
        }

        with patch(
            "app.orchestration.nodes.inventory.InventoryService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.compute_shortage_data = AsyncMock(return_value={"actionable_shortages": []})
            mock_svc.generate_recommendation = AsyncMock(return_value={
                "service": "inventory", "data": {}, "recommendation": {}
            })
            await inventory_node(state_with_forecast, db_factory=mock_db_factory, llm=mock_llm)

        mock_svc.compute_shortage_data.assert_called_once_with(
            forecast_data={"predicted_orders": 130.0, "avg_friday_orders": 100.0},
            scenario_profile=None,
        )
        # No procurement context available (no swiggy_client passed in this test).
        mock_svc.generate_recommendation.assert_called_once_with(
            {"actionable_shortages": []},
            procurement_context=None,
        )

    @pytest.mark.asyncio
    async def test_exception_captured_in_output(self, base_state, mock_db_factory, mock_llm):
        from app.orchestration.nodes.inventory import inventory_node

        with patch(
            "app.orchestration.nodes.inventory.InventoryService"
        ) as MockService:
            MockService.return_value.compute_shortage_data = AsyncMock(
                side_effect=Exception("DB timeout")
            )
            result = await inventory_node(base_state, db_factory=mock_db_factory, llm=mock_llm)

        output = result["inventory_output"]
        assert output["service"] == "inventory"
        assert "DB timeout" in output["error"]
        assert output["data"] is None

    @pytest.mark.asyncio
    async def test_procurement_prices_reach_the_llm_prompt_same_run(self, base_state, mock_db, mock_db_factory, mock_llm):
        """Regression guard for the ordering bug: ProcurementEnricher used to
        run AFTER the LLM recommendation call, so live Instamart prices could
        never appear in that same run's restock_actions text. Uses the real
        InventoryService (not mocked) end to end through inventory_node, with
        only ProcurementEnricher and the Swiggy client mocked, and asserts the
        live price actually lands in the prompt sent to the LLM."""
        from app.orchestration.nodes.inventory import inventory_node

        mock_db.query.return_value.all.return_value = [
            _make_item(name="Mozzarella", stock=3.0, threshold=8.0, spoilage=True),
        ]

        mock_swiggy_client = MagicMock()
        mock_swiggy_client.is_available.return_value = True

        with patch("app.orchestration.nodes.inventory.ProcurementEnricher") as MockEnricher:
            MockEnricher.return_value.enrich = AsyncMock(return_value={
                "procurement_options": [
                    {"ingredient": "mozzarella", "spinId": "spin_1", "price": 93.0, "unit": "140 g", "inStock": True},
                ],
                "prompt_text": "## Live Procurement Options (Instamart)\n- Mozzarella: Rs.93/140 g (in stock)",
            })
            await inventory_node(
                base_state, db_factory=mock_db_factory, llm=mock_llm, swiggy_client=mock_swiggy_client,
            )

        prompt = mock_llm.complete_json.await_args.kwargs["prompt"]
        assert "Rs.93/140 g" in prompt, (
            "live procurement prices must reach the LLM prompt in the same run "
            "that fetched them, not just get stored in state for later consumers"
        )

    @pytest.mark.asyncio
    async def test_debug_trace_appended(self, mock_db_factory, mock_llm):
        from app.orchestration.nodes.inventory import inventory_node
        from app.orchestration.state import make_initial_state

        state = make_initial_state("friday_rush", simulation_mode=True, debug=True)
        state["execution_trace"] = []

        result = await inventory_node(state, db_factory=mock_db_factory, llm=mock_llm)
        assert "inventory" in result["execution_trace"]

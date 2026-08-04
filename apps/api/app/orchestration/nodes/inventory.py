"""
Inventory & Waste Agent node — P2-02.

Replaces the Phase 1 stub with a real InventoryService call.
Cross-references stock levels against the demand forecast to surface
shortage and overstock alerts, then asks the LLM for operational actions.

Writes to state['inventory_output'].
"""

from typing import Callable

from app.orchestration.state import OrchestratorState
from app.domain.services.inventory_service import InventoryService
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.swiggy.client import SwiggyMCPClient
from app.infrastructure.swiggy.enrichers.procurement import ProcurementEnricher


async def inventory_node(
    state: OrchestratorState,
    db_factory: Callable,
    llm: BaseLLMProvider,
    swiggy_client: SwiggyMCPClient | None = None,
) -> OrchestratorState:
    """
    Detects stock pressure and waste risk using real inventory data.
    Writes to state['inventory_output'].

    Uses db_factory (not a shared Session) so the sync DB query inside
    InventoryService.compute_shortage_data() runs in asyncio.to_thread()
    without blocking other parallel fan-out nodes.
    """
    if state.get("error"):
        return state

    llm = (state.get("llm_registry") or {}).get("fast") or llm

    if state.get("debug") and state.get("execution_trace") is not None:
        state["execution_trace"].append("inventory")

    session = db_factory()
    try:
        if state.get("simulation_mode", False):
            sim_output = {
                "service": "inventory",
                "data": {
                    "total_items_checked": 10,
                    "shortage_alerts": [
                        {
                            "ingredient":        "Mozzarella",
                            "unit":              "kg",
                            "quantity_in_stock": 3.5,
                            "reorder_threshold": 8.0,
                            "shortfall":         4.5,
                            "spoilage_risk":     True,
                            "severity":          "critical",
                        }
                    ],
                    "overstock_alerts": [],
                    "high_demand_week": True,
                    "demand_ratio":     1.2,
                },
                "recommendation": {
                    "restock_actions":       ["Order 10kg Mozzarella immediately"],
                    "waste_reduction_actions": [],
                    "priority":              "high",
                    "reasoning":             "Critical shortage on high-demand week.",
                    "risks":                 ["Unable to fulfil pizza orders during peak hours"],
                },
            }
            sim_data = sim_output["data"]
            return {
                **state,
                "inventory_output": sim_output,
                "inventory_assumptions": {
                    "items_flagged_low": [
                        a["ingredient"] for a in (sim_data.get("shortage_alerts") or [])
                        if isinstance(a, dict) and a.get("ingredient")
                    ],
                    "items_flagged_overstock": [
                        a["ingredient"] for a in (sim_data.get("overstock_alerts") or [])
                        if isinstance(a, dict) and a.get("ingredient")
                    ],
                },
            }

        # Pull forecast data from state to compute demand ratio
        forecast_data = None
        forecast_output = state.get("forecast_output")
        if forecast_output and isinstance(forecast_output, dict):
            forecast_data = forecast_output.get("data")

        service = InventoryService(db=session, llm=llm)

        # Step 1 — compute the real shortage list first, no LLM call yet.
        shortage_data = await service.compute_shortage_data(
            forecast_data=forecast_data,
            scenario_profile=state.get("scenario_profile"),
        )
        shortage_names = [
            a["ingredient"] for a in shortage_data["actionable_shortages"]
            if isinstance(a, dict) and a.get("ingredient")
        ]

        # Step 2 — fetch live Instamart prices for exactly those shortages,
        # BEFORE generating the recommendation. Must happen in this order:
        # the recommendation prompt is what's supposed to cite these prices
        # (e.g. "order 5kg tomatoes via Instamart at Rs.24/kg"), so the prices
        # have to exist before that prompt is built, not after.
        procurement_ctx = None
        if swiggy_client and swiggy_client.is_available() and shortage_names:
            enricher = ProcurementEnricher(swiggy_client)
            procurement_ctx = await enricher.enrich({
                "org_id":         state.get("org_id") or 0,
                "shortage_items": shortage_names,
            })

        # Step 3 — now generate the recommendation, with procurement prices in hand.
        result = await service.generate_recommendation(
            shortage_data,
            procurement_context=procurement_ctx,
        )
        data = result.get("data") or {}

        return {
            **state,
            "inventory_output": result,
            "swiggy_procurement_options": procurement_ctx,
            "inventory_assumptions": {
                "items_flagged_low":      shortage_names,
                "items_flagged_overstock": [
                    a["ingredient"] for a in (data.get("overstock_alerts") or [])
                    if isinstance(a, dict) and a.get("ingredient")
                ],
            },
        }

    except Exception as exc:
        return {
            **state,
            "inventory_output": {
                "service": "inventory",
                "error":   str(exc),
                "data":    None,
                "recommendation": None,
            },
            "inventory_assumptions": None,
        }
    finally:
        session.close()

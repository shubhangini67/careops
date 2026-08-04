from datetime import datetime
import re

from sqlalchemy.orm import Session

from app.domain.services.business_analytics_service import BusinessAnalyticsService
from app.domain.services.complaint_service import ComplaintService
from app.domain.services.forecast_service import ForecastService
from app.domain.services.inventory_service import InventoryService
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.prompt_utils import PromptUtils


class MenuService:
    """Builds menu insights from demand, complaints, inventory pressure, and scenario context."""

    def __init__(self, db: Session, llm: BaseLLMProvider):
        self.db = db
        self.llm = llm

    def get_top_items(self, target_date: datetime | None = None) -> list[dict]:
        forecast_service = ForecastService(db=self.db, llm=self.llm)
        if hasattr(forecast_service, "get_top_service_day_items"):
            return forecast_service.get_top_service_day_items(target_date)
        return forecast_service.get_top_friday_items()

    def normalize_scenario_language(
        self,
        payload: dict | list | str | None,
        scenario_label: str,
    ):
        if scenario_label == "Service":
            return payload

        if isinstance(payload, dict):
            return {
                key: self.normalize_scenario_language(value, scenario_label)
                for key, value in payload.items()
            }
        if isinstance(payload, list):
            return [self.normalize_scenario_language(value, scenario_label) for value in payload]
        if not isinstance(payload, str):
            return payload

        replacements = [
            (r"\bFriday rush\b", scenario_label),
            (r"\bFriday service\b", f"{scenario_label} service"),
            (r"\bFriday promotion\b", f"{scenario_label} promotion"),
            (r"\bon Friday\b", f"during {scenario_label}"),
            (r"\bFriday\b", scenario_label),
        ]

        normalized = payload
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized

    async def analyse_and_recommend(
        self,
        target_date: datetime | None = None,
        forecast_data: dict | None = None,
        complaint_data: dict | None = None,
        inventory_data: dict | None = None,
        competitor_context: dict | None = None,
        prior_feedback: str | None = None,
        reservation_data: dict | None = None,
        market_intel_data: dict | None = None,
        dineout_data: dict | None = None,
        operational_focus: str | None = None,
    ) -> dict:
        top_items = self.get_top_items(target_date)

        if complaint_data is None:
            complaint_service = ComplaintService(db=self.db, llm=self.llm)
            complaint_data = complaint_service.get_complaint_summary(days=28)

        if inventory_data is None:
            inventory_service = InventoryService(db=self.db, llm=self.llm)
            demand_ratio = 1.0
            if forecast_data:
                predicted = forecast_data.get("predicted_orders", 0)
                avg = forecast_data.get("avg_friday_orders", 0)
                if avg:
                    demand_ratio = predicted / avg
            inventory_data = inventory_service.compute_alerts(
                inventory_service.get_all_stock(),
                demand_ratio=demand_ratio,
            )

        shortage_alerts = (inventory_data or {}).get("shortage_alerts") or []
        overstock_alerts = (inventory_data or {}).get("overstock_alerts") or []
        complaint_themes = (complaint_data or {}).get("unique_complaints") or []
        scenario_label = (
            (inventory_data or {}).get("scenario_label")
            or (complaint_data or {}).get("scenario_label")
            or (forecast_data or {}).get("scenario_label")
            or "Service"
        )
        service_window = (
            (inventory_data or {}).get("service_window")
            or (complaint_data or {}).get("service_window")
            or (forecast_data or {}).get("service_window")
            or "target service window"
        )
        scenario_watchouts = (complaint_data or {}).get("scenario_watchouts") or []

        # Capacity awareness — genuinely computed from reservation's own occupancy
        # figure (same 90% threshold EvaluationSanityChecker's Diff 2 checks), not
        # a placeholder. Without this, menu_intelligence has no way to know whether
        # tonight is near-full-house and always claimed capacity was fine by default.
        occupancy_pct = (reservation_data or {}).get("occupancy_pct")
        capacity_constrained = occupancy_pct is not None and occupancy_pct > 90

        data = {
            "top_items": top_items,
            "forecast_snapshot": {
                "predicted_orders": (forecast_data or {}).get("predicted_orders"),
                "predicted_peak_orders": (forecast_data or {}).get("predicted_peak_orders"),
                "avg_friday_orders": (forecast_data or {}).get("avg_friday_orders"),
                "target_date": (forecast_data or {}).get("target_date"),
            },
            "complaint_themes": complaint_themes[:5],
            "shortage_ingredients": [
                alert.get("ingredient")
                for alert in shortage_alerts
                if isinstance(alert, dict) and alert.get("ingredient")
            ],
            "overstock_ingredients": [
                alert.get("ingredient")
                for alert in overstock_alerts
                if isinstance(alert, dict) and alert.get("ingredient")
            ],
            "scenario_label": scenario_label,
            "service_window": service_window,
            "scenario_watchouts": scenario_watchouts[:3],
            "peak_occupancy_pct": occupancy_pct,
            "capacity_constrained": capacity_constrained,
            "note": "Phase 3 menu insights combine demand, complaints, inventory, and scenario context.",
        }

        top_item_lines = "\n".join(
            f"  - {item.get('item')} ({item.get('category')}): ordered {item.get('total_ordered')} times"
            for item in top_items
        ) or "  None"

        shortage_lines = "\n".join(
            f"  - {alert.get('ingredient')}: severity={alert.get('severity')}, shortfall={alert.get('shortfall')}, spoilage_risk={alert.get('spoilage_risk')}"
            for alert in shortage_alerts
            if isinstance(alert, dict)
        ) or "  None"

        overstock_lines = "\n".join(
            f"  - {alert.get('ingredient')}: excess={alert.get('excess')}, spoilage_risk={alert.get('spoilage_risk')}"
            for alert in overstock_alerts
            if isinstance(alert, dict)
        ) or "  None"

        complaint_lines = "\n".join(f"  - {theme}" for theme in complaint_themes[:5]) or "  None"
        watchout_lines = "\n".join(f"  - {item}" for item in scenario_watchouts[:3]) or "  None"

        service_day_label = (forecast_data or {}).get("service_day_label", "service")
        critical_blocked = [
            alert.get("ingredient")
            for alert in shortage_alerts
            if isinstance(alert, dict) and alert.get("severity") == "critical" and alert.get("ingredient")
        ]
        blocked_lines = "\n".join(f"  - {ing}" for ing in critical_blocked) or "  None"

        # P6-A24: prefer the unified "Area & Live Signals" text (competitor +
        # occupancy + weather/holiday + industry trends + regulatory alerts,
        # assembled in MarketIntelService) -- falls back to the raw competitor
        # prompt_text alone if live_signals_text is somehow absent (e.g. an
        # older cached market_intel_output).
        market_context = (
            (market_intel_data or {}).get("live_signals_text")
            or (competitor_context or {}).get("prompt_text")
            or ""
        )

        capacity_lines = []
        if occupancy_pct is not None:
            capacity_lines.append(
                f"  - Reservation occupancy: {occupancy_pct}% of capacity"
                f"{' — CONSTRAINED (near-full house, throughput protection required)' if capacity_constrained else ''}"
            )
        area_occupancy = (market_intel_data or {}).get("area_occupancy")
        if area_occupancy:
            busy_note = " (tonight busy)" if (market_intel_data or {}).get("tonight_busy") else ""
            capacity_lines.append(f"  - Area occupancy (Swiggy): {area_occupancy}{busy_note}")
        low_dineout_slots = (dineout_data or {}).get("low_availability_slots")
        if low_dineout_slots:
            capacity_lines.append(f"  - Your Dineout slots tonight: {low_dineout_slots} low-availability")
        capacity_context = "\n".join(capacity_lines)

        # Margin-aware dish performance -- forecasted top_items above only know what's
        # POPULAR, not what's PROFITABLE. Without this, a plan can push a high-demand,
        # low-margin dish while a similarly-popular, higher-margin alternative sits unused.
        analytics_service = BusinessAnalyticsService(self.db)
        dish_performance = analytics_service.get_dish_performance(days=14)
        margin_lines = "\n".join(
            f"  - {d['name']} ({d['category']}): Rs.{d['revenue']:.0f} revenue, "
            f"{d['margin_pct']:.0f}% margin" if d["margin_pct"] is not None
            else f"  - {d['name']} ({d['category']}): Rs.{d['revenue']:.0f} revenue, margin unknown"
            for d in dish_performance[:10]
        )

        prompt = PromptUtils.format_menu_prompt(
            scenario_label=scenario_label,
            service_day_label=service_day_label,
            service_window=service_window,
            forecast_data=forecast_data or {},
            top_item_lines=top_item_lines,
            complaint_lines=complaint_lines,
            watchout_lines=watchout_lines,
            shortage_lines=shortage_lines,
            overstock_lines=overstock_lines,
            blocked_lines=blocked_lines,
            market_context=market_context,
            prior_feedback=prior_feedback or "",
            capacity_context=capacity_context,
            margin_context=margin_lines,
            operational_focus=operational_focus or "",
        )

        recommendation = await self.llm.complete_json(
            prompt=prompt,
            system_prompt=PromptUtils.SYSTEM_MENU_AGENT,
        )
        recommendation = self.normalize_scenario_language(
            recommendation,
            scenario_label=scenario_label,
        )

        return {
            "service": "menu",
            "data": data,
            "recommendation": recommendation,
        }

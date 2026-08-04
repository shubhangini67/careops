import re
from typing import Any


class CostAwareScoringService:
    """Scores operational tradeoffs for a planning bundle using deterministic heuristics."""

    def evaluate_bundle(self, bundle: dict[str, Any] | None) -> dict[str, Any]:
        bundle = bundle or {}
        agents = bundle.get("agents") or {}

        forecast_data = (agents.get("forecast") or {}).get("data") or {}
        reservation_data = (agents.get("reservation") or {}).get("data") or {}
        inventory_data = (agents.get("inventory") or {}).get("data") or {}
        menu_rec = (agents.get("menu") or {}).get("recommendation") or {}
        forecast_rec = (agents.get("forecast") or {}).get("recommendation") or {}
        reservation_rec = (agents.get("reservation") or {}).get("recommendation") or {}
        inventory_rec = (agents.get("inventory") or {}).get("recommendation") or {}

        predicted_orders = float(forecast_data.get("predicted_orders") or 0)
        # Use the same-day average if available; fall back to avg_friday_orders.
        # If demand_ratio < 1.0 it means a lower-volume service (e.g. weekday lunch)
        # which is normal — floor at 1.0 so off-peak scenarios aren't penalised.
        avg_orders = float(
            forecast_data.get("avg_same_day_orders")
            or forecast_data.get("avg_friday_orders")
            or 0
        )
        raw_demand_ratio = round((predicted_orders / avg_orders), 2) if avg_orders > 0 else 1.0
        demand_ratio = max(raw_demand_ratio, 1.0)

        occupancy_pct = float(reservation_data.get("occupancy_pct") or 0)
        waitlist_count = int(reservation_data.get("waitlist_count") or 0)

        shortage_alerts = inventory_data.get("shortage_alerts") or []
        overstock_alerts = inventory_data.get("overstock_alerts") or []
        critical_shortages = sum(
            1 for alert in shortage_alerts if alert.get("severity") == "critical"
        )

        staffing_units = self._extract_percent_or_count(forecast_rec)
        prep_complexity = self._estimate_prep_complexity(forecast_rec, menu_rec)

        pressure_components = {
            "prep_burden": self._clamp(
                0.25
                + max(0.0, demand_ratio - 1.0) * 0.6
                + staffing_units * 0.02
                + prep_complexity * 0.08
            ),
            "staffing_burden": self._clamp(
                0.1
                + staffing_units * 0.03
                + (0.15 if occupancy_pct >= 90 else 0.0)
            ),
            "stock_risk": self._clamp(
                0.1
                + critical_shortages * 0.12
                + max(0, len(shortage_alerts) - critical_shortages) * 0.05
                + len(overstock_alerts) * 0.03
            ),
            "reservation_pressure": self._clamp(
                (occupancy_pct / 100) * 0.75 + min(waitlist_count, 5) * 0.05
            ),
        }

        cost_pressure_score = round(sum(pressure_components.values()) / len(pressure_components), 2)

        benefit_components = {
            "demand_alignment": self._clamp(0.35 + max(0.0, demand_ratio - 1.0) * 0.55),
            "inventory_protection": self._clamp(0.35 + min(critical_shortages, 5) * 0.1),
            "service_protection": self._clamp((occupancy_pct / 100) * 0.55 + min(waitlist_count, 4) * 0.06),
        }
        benefit_score = round(sum(benefit_components.values()) / len(benefit_components), 2)
        tradeoff_score = round(self._clamp(benefit_score - (cost_pressure_score - 0.45)), 2)

        tradeoff_notes: list[str] = []
        if pressure_components["prep_burden"] >= 0.75:
            tradeoff_notes.append("Prep burden is high for this service window.")
        if pressure_components["reservation_pressure"] >= 0.75:
            tradeoff_notes.append("Reservation pressure leaves limited slack for risky changes.")
        if pressure_components["stock_risk"] >= 0.75:
            tradeoff_notes.append("Inventory risk is elevated; execution depends on tight restocking.")
        if staffing_units >= 10:
            tradeoff_notes.append("Large staffing changes may be difficult to execute on short notice.")
        if not tradeoff_notes:
            tradeoff_notes.append("Operational tradeoffs look manageable for this service window.")

        recommended_focus: list[str] = []
        if critical_shortages:
            recommended_focus.append("Prioritize critical shortage actions before secondary optimizations.")
        if occupancy_pct >= 90 or waitlist_count >= 3:
            recommended_focus.append("Protect seating flow and table turns during the peak window.")
        if pressure_components["prep_burden"] >= 0.7:
            recommended_focus.append("Favor low-complexity prep changes over broad execution changes.")
        if not recommended_focus:
            recommended_focus.append("Keep execution focused on the highest-confidence operational wins.")

        return {
            "cost_pressure_score": cost_pressure_score,
            "benefit_score": benefit_score,
            "tradeoff_score": tradeoff_score,
            "pressure_components": pressure_components,
            "benefit_components": benefit_components,
            "tradeoff_notes": tradeoff_notes,
            "recommended_focus": recommended_focus,
            "signals": {
                "demand_ratio": raw_demand_ratio,
                "occupancy_pct": occupancy_pct,
                "waitlist_count": waitlist_count,
                "critical_shortages": critical_shortages,
                "shortage_alerts": len(shortage_alerts),
                "overstock_alerts": len(overstock_alerts),
                "staffing_change_hint": staffing_units,
                "prep_complexity_hint": prep_complexity,
            },
        }

    def format_report(self, report: dict[str, Any]) -> str:
        pressure = report.get("pressure_components") or {}
        signals = report.get("signals") or {}
        notes = report.get("tradeoff_notes") or []
        focus = report.get("recommended_focus") or []
        return (
            f"Cost pressure score: {report.get('cost_pressure_score', 0):.2f}\n"
            f"Benefit score: {report.get('benefit_score', 0):.2f}\n"
            f"Tradeoff score: {report.get('tradeoff_score', 0):.2f}\n"
            f"- Prep burden: {pressure.get('prep_burden', 0):.2f}\n"
            f"- Staffing burden: {pressure.get('staffing_burden', 0):.2f}\n"
            f"- Stock risk: {pressure.get('stock_risk', 0):.2f}\n"
            f"- Reservation pressure: {pressure.get('reservation_pressure', 0):.2f}\n"
            f"- Demand ratio: {signals.get('demand_ratio', 1.0)}\n"
            f"- Occupancy: {signals.get('occupancy_pct', 0)}%\n"
            f"- Waitlist count: {signals.get('waitlist_count', 0)}\n"
            f"- Critical shortages: {signals.get('critical_shortages', 0)}\n"
            f"Tradeoff notes: {' | '.join(notes)}\n"
            f"Recommended focus: {' | '.join(focus)}"
        )

    def _extract_percent_or_count(self, recommendation: Any) -> int:
        text = str(recommendation)
        staffing_matches = re.findall(
            r"(?:increase|add|extra|additional|increase\s+staff(?:ing)?\s+by)\s+(\d+(?:\.\d+)?)\s*%",
            text, re.I
        )
        if staffing_matches:
            return min(round(max(float(m) for m in staffing_matches)), 30)

        count_matches = re.findall(r"(?:increase|add|extra|additional)\s+(?:staff(?:ing)?\s+by\s+)?(\d+)", text, re.I)
        if count_matches:
            return min(max(int(m) for m in count_matches), 30)
        return 0

    def _estimate_prep_complexity(self, forecast_rec: Any, menu_rec: Any) -> int:
        complexity = 0
        joined = f"{forecast_rec} {menu_rec}".lower()
        for token in ("prep", "prepare", "ingredients", "dough", "batch", "temporary seating", "specials"):
            if token in joined:
                complexity += 1
        return complexity

    def _clamp(self, value: float) -> float:
        return max(0.0, min(round(value, 2), 1.0))

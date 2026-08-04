import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SanityIssue:
    code: str
    severity: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


class EvaluationSanityChecker:
    """Deterministic checks that complement the LLM critic."""

    MAX_CAPACITY = 70  # overridden per-instance when org capacity is known
    MAX_ADDITIONAL_STAFF = 20
    MAX_PRICE_CHANGE_PCT = 30
    SHORT_TERM_WORDS = {
        "24 hour",
        "24-hour",
        "today",
        "tonight",
        "by friday",
        "before friday",
        "by 5pm",
        "by 6pm",
        "same day",
        "immediate",
        "immediately",
        "shift",
    }
    LONG_TERM_WORDS = {
        "next month",
        "monthly",
        "quarter",
        "renovate",
        "renovation",
        "hire permanent",
        "supplier contract",
        "menu redesign",
        "brand campaign",
    }

    def __init__(self, capacity: int = 70) -> None:
        self.MAX_CAPACITY = capacity

    def check_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        issues: list[SanityIssue] = []
        issues.extend(self._check_top_level_schema(bundle))

        agents = bundle.get("agents")
        if isinstance(agents, dict):
            issues.extend(self._check_agent_schema(agents))
            issues.extend(self._check_capacity_and_staffing(bundle))
            issues.extend(self._check_inventory_quantities(agents.get("inventory") or {}))
            issues.extend(self._check_24h_feasibility(agents))

        assumptions = bundle.get("assumptions") or {}
        stale_assumptions = (
            self._diff_assumptions(assumptions, agents or {})
            if isinstance(assumptions, dict)
            else []
        )

        return {
            "passed": not any(issue.severity == "error" for issue in issues),
            "issues": [issue.as_dict() for issue in issues],
            "summary": self._summarize(issues),
            "stale_assumptions": stale_assumptions,
        }

    def format_report(self, report: dict[str, Any]) -> str:
        if not report.get("issues"):
            return "Automated sanity checks passed with no issues."

        lines = ["Automated sanity checks found:"]
        for issue in report["issues"]:
            lines.append(
                f"- [{issue['severity']}] {issue['code']}: {issue['message']}"
            )
        return "\n".join(lines)

    def format_stale_assumptions(self, stale_assumptions: list[dict]) -> str:
        if not stale_assumptions:
            return "No stale assumption conflicts detected."
        lines = ["The following assumptions made by domain agents were found to be stale or contradicted by other agents' outputs:"]
        for item in stale_assumptions:
            lines.append(f"- [{item['node']}] {item['conflict']}")
        return "\n".join(lines)

    def _diff_assumptions(
        self,
        assumptions: dict[str, Any],
        agents: dict[str, Any],
    ) -> list[dict]:
        """
        Cross-diff assumptions written by each domain node against facts from other nodes.

        Each returned dict describes one stale assumption: which node made it, the key,
        the assumed value, the actual value observed elsewhere, and a human-readable conflict.
        Nodes that failed (assumptions is None) are gracefully skipped.
        """
        stale: list[dict] = []

        menu_a           = assumptions.get("menu")            or {}
        inventory_a      = assumptions.get("inventory")       or {}
        reservation_a    = assumptions.get("reservation")     or {}
        complaint_a      = assumptions.get("complaint")       or {}
        market_intel_a   = assumptions.get("market_intel")    or {}
        dineout_manager_a = assumptions.get("dineout_manager") or {}

        # Diff 1 removed: MenuService self-queries InventoryService when inventory_data is None
        # (parallel execution means inventory_output is never in state when menu runs).
        # Both nodes hit the same DB with the same demand_ratio, so they always agree on
        # shortage status. The assumed_no_active_stockouts field is no longer written.

        # Diff 2: menu assumed covers within capacity, but reservation shows >90% occupancy.
        # Menu never has access to reservation data; this assumption is always implicit.
        if menu_a.get("assumed_covers_within_capacity") is True:
            occ = reservation_a.get("assumed_peak_occupancy_pct")
            if occ is not None and occ > 90:
                stale.append({
                    "node": "menu_intelligence",
                    "assumption_key": "assumed_covers_within_capacity",
                    "assumed_value": True,
                    "actual_value": occ,
                    "conflict": (
                        f"menu_intelligence assumed covers within capacity, but reservation node "
                        f"shows {occ}% occupancy — menu recommendations must account for "
                        f"kitchen throughput limits under near-full house"
                    ),
                })

        # Diff 3: reservation planned for high occupancy but demand forecast confidence is low.
        # High-occupancy planning on a weak forecast is operationally risky.
        occ = reservation_a.get("assumed_peak_occupancy_pct")
        if occ is not None and occ > 85:
            forecast_data = (agents.get("forecast") or {}).get("data") or {}
            confidence = forecast_data.get("confidence")
            confidence_band = forecast_data.get("confidence_band")
            low_confidence = (
                (isinstance(confidence, (int, float)) and confidence < 0.6)
                or (isinstance(confidence_band, str) and confidence_band.lower() in ("low", "poor", "weak"))
            )
            if low_confidence:
                stale.append({
                    "node": "reservation",
                    "assumption_key": "assumed_peak_occupancy_pct",
                    "assumed_value": occ,
                    "actual_value": confidence if confidence is not None else confidence_band,
                    "conflict": (
                        f"reservation node planned for {occ}% occupancy, but demand forecast "
                        f"confidence is low — high-occupancy operational planning on a weak "
                        f"forecast signal overstates certainty"
                    ),
                })

        # Diff 4: complaint node classified volume as low but negative feedback is borderline elevated.
        # Uses a secondary threshold (25%) below the node's own flag threshold (30%)
        # to catch the gray zone before it becomes a bigger issue.
        if complaint_a.get("assumed_high_complaint_volume") is False:
            negative_pct = float(complaint_a.get("assumed_negative_pct") or 0)
            if negative_pct > 25.0:
                stale.append({
                    "node": "complaint_intelligence",
                    "assumption_key": "assumed_high_complaint_volume",
                    "assumed_value": False,
                    "actual_value": negative_pct,
                    "conflict": (
                        f"complaint_intelligence classified complaint volume as low, but "
                        f"negative feedback is {negative_pct:.1f}% — borderline elevated "
                        f"complaint risk that may compound under high occupancy"
                    ),
                })

        # Diff 5 (P6-S13): market_intel found pricing alerts vs menu_intel planning to push items.
        # market_intel_node detects our items priced above Swiggy area average. If menu_intel
        # is simultaneously planning to highlight/push those same items, we risk lower conversion
        # because customers can find cheaper options nearby on Swiggy.
        pricing_alerts_count = int(market_intel_a.get("pricing_alerts_count") or 0)
        items_assumed_available = menu_a.get("items_assumed_available") or []
        if (
            market_intel_a.get("swiggy_available") is True
            and pricing_alerts_count > 0
            and items_assumed_available
        ):
            stale.append({
                "node": "menu_intelligence",
                "assumption_key": "items_assumed_available",
                "assumed_value": items_assumed_available,
                "actual_value": pricing_alerts_count,
                "conflict": (
                    f"menu_intelligence is planning to push {len(items_assumed_available)} item(s) "
                    f"({', '.join(str(i) for i in items_assumed_available[:3])}) but "
                    f"market_intel found {pricing_alerts_count} Swiggy pricing alert(s) — "
                    f"verify that highlighted items are competitively priced vs area average "
                    f"before driving volume"
                ),
            })

        # Diff 6 (P6-S13): dineout_manager flagged own slots low + reservation predicts high occupancy.
        # When both internal reservations and Dineout bookings signal a near-full house tonight,
        # the operational risk compounds — one channel being full is manageable, both is a hard cap.
        dineout_slots_low = dineout_manager_a.get("assumed_dineout_slots_low")
        peak_occ = reservation_a.get("assumed_peak_occupancy_pct")
        if (
            dineout_manager_a.get("own_slots_checked") is True
            and dineout_slots_low is True
            and peak_occ is not None
            and peak_occ > 80
        ):
            stale.append({
                "node": "dineout_manager",
                "assumption_key": "assumed_dineout_slots_low",
                "assumed_value": True,
                "actual_value": peak_occ,
                "conflict": (
                    f"dineout_manager found your Dineout slots are nearly full tonight "
                    f"AND reservation node predicts {peak_occ}% internal occupancy — "
                    f"compound demand signal: both channels at capacity, ensure full-house "
                    f"staffing and consider whether to open additional Dineout slots now"
                ),
            })

        # Diff 7 (P6-MI08): competitor Dineout deals may absorb demand flagged as HIGH occupancy.
        # tonight_busy comes from OUR area occupancy signal (competitors nearly full). But if those
        # same competitors are running deals/promos tonight, some of that "full" demand is being
        # captured by discounted bookings rather than organic overflow — the walk-in surge implied
        # by tonight_busy=True may not materialise at our door the way a plan built on it assumes.
        tonight_busy = market_intel_a.get("tonight_busy")
        dineout_deals_count = int(market_intel_a.get("dineout_deals_count") or 0)
        if tonight_busy is True and dineout_deals_count >= 2:
            stale.append({
                "node": "market_intel",
                "assumption_key": "tonight_busy",
                "assumed_value": True,
                "actual_value": dineout_deals_count,
                "conflict": (
                    f"market_intel flagged tonight_busy=True (HIGH area occupancy), but "
                    f"{dineout_deals_count} competitor Dineout deal(s)/promo(s) are live tonight — "
                    f"demand may be absorbed by competitor bookings before reaching your restaurant. "
                    f"Revise walk-in overflow estimate down 15-20%."
                ),
            })

        return stale

    def _check_top_level_schema(self, bundle: dict[str, Any]) -> list[SanityIssue]:
        issues = []
        if not isinstance(bundle, dict):
            return [
                SanityIssue(
                    "schema.bundle_type",
                    "error",
                    "Aggregated recommendation must be a JSON object.",
                )
            ]

        for key in ("scenario", "target_date", "agents", "summary_for_critic"):
            if key not in bundle:
                issues.append(
                    SanityIssue("schema.missing_key", "error", f"Missing '{key}'.")
                )

        if "agents" in bundle and not isinstance(bundle["agents"], dict):
            issues.append(
                SanityIssue("schema.agents_type", "error", "'agents' must be an object.")
            )
        return issues

    def _check_agent_schema(self, agents: dict[str, Any]) -> list[SanityIssue]:
        issues = []
        for name in ("forecast", "reservation", "complaint", "menu", "inventory"):
            agent = agents.get(name)
            if agent is None:
                issues.append(
                    SanityIssue(
                        "schema.missing_agent",
                        "warning",
                        f"Missing '{name}' agent block.",
                    )
                )
                continue
            if not isinstance(agent, dict):
                issues.append(
                    SanityIssue(
                        "schema.agent_type",
                        "error",
                        f"Agent block '{name}' must be an object.",
                    )
                )
                continue
            for key in ("data", "recommendation"):
                if key not in agent:
                    issues.append(
                        SanityIssue(
                            "schema.missing_agent_key",
                            "warning",
                            f"Agent '{name}' is missing '{key}'.",
                        )
                    )
        return issues

    def _check_capacity_and_staffing(self, bundle: dict[str, Any]) -> list[SanityIssue]:
        issues = []
        text = self._flatten_text(bundle)

        if re.search(r"\b(close|shut)\s+(the\s+)?restaurant\b", text, re.I):
            issues.append(
                SanityIssue(
                    "policy.close_restaurant",
                    "error",
                    "Recommendation suggests closing the restaurant.",
                )
            )

        if re.search(r"\bcancell?ing?\s+all\s+reservations\b", text, re.I):
            issues.append(
                SanityIssue(
                    "policy.cancel_all_reservations",
                    "error",
                    "Recommendation suggests cancelling all reservations.",
                )
            )

        for match in re.finditer(r"\b(?:add|hire|schedule)\s+(\d+)\s+(?:additional\s+)?staff\b", text, re.I):
            staff_count = int(match.group(1))
            if staff_count > self.MAX_ADDITIONAL_STAFF:
                issues.append(
                    SanityIssue(
                        "policy.staffing_limit",
                        "error",
                        f"Additional staffing request of {staff_count} exceeds limit of {self.MAX_ADDITIONAL_STAFF}.",
                    )
                )

        for match in re.finditer(r"\b(\d+)\s+(?:guests|covers|seats)\b", text, re.I):
            capacity = int(match.group(1))
            if capacity > self.MAX_CAPACITY and re.search(
                r"\b(capacity|seat|reservation|booking|guests|covers)\b",
                text[max(0, match.start() - 50): match.end() + 50],
                re.I,
            ):
                issues.append(
                    SanityIssue(
                        "policy.capacity_limit",
                        "error",
                        f"Capacity-related number {capacity} exceeds restaurant capacity of {self.MAX_CAPACITY}.",
                    )
                )

        for match in re.finditer(r"\b(\d+)%\s+(?:price\s+)?(?:increase|decrease|discount|cut)\b", text, re.I):
            pct = int(match.group(1))
            if pct > self.MAX_PRICE_CHANGE_PCT:
                issues.append(
                    SanityIssue(
                        "policy.price_change_limit",
                        "error",
                        f"Price change of {pct}% exceeds policy limit of {self.MAX_PRICE_CHANGE_PCT}%.",
                    )
                )

        return issues

    def _check_inventory_quantities(self, inventory_agent: dict[str, Any]) -> list[SanityIssue]:
        issues = []
        data = inventory_agent.get("data") or {}
        recommendation = inventory_agent.get("recommendation") or {}
        # Only scan the operative action lists — reasoning/risks contain explanatory LLM text
        # with large numbers that are NOT operative order quantities (e.g. "10kg Garlic needed").
        # Checking those would flag correct explanations as violations.
        recommendation_text = "\n".join(
            str(a)
            for a in
            (recommendation.get("restock_actions") or []) +
            (recommendation.get("waste_reduction_actions") or [])
        )

        if not isinstance(data, dict):
            return issues

        for alert in data.get("shortage_alerts") or []:
            if not isinstance(alert, dict):
                continue
            ingredient = str(alert.get("ingredient", "")).strip()
            if not ingredient:
                continue

            current_stock = self._to_float(alert.get("quantity_in_stock"))
            shortfall = self._to_float(alert.get("shortfall"))
            max_actionable = self._to_float(alert.get("max_actionable_restock_qty"))
            if max_actionable is None and current_stock is not None and shortfall is not None:
                max_actionable = shortfall * 3

            if max_actionable is None:
                continue

            for qty in self._quantities_near_ingredient(recommendation_text, ingredient):
                if qty > max_actionable:
                    issues.append(
                        SanityIssue(
                            "inventory.quantity_realism",
                            "error",
                            f"{ingredient} restock quantity {qty:g} exceeds max actionable {max_actionable:g}.",
                        )
                    )

        return issues

    def _check_24h_feasibility(self, agents: dict[str, Any]) -> list[SanityIssue]:
        issues = []
        text = self._flatten_text({name: agent.get("recommendation") for name, agent in agents.items() if isinstance(agent, dict)})
        lower = text.lower()

        for phrase in self.LONG_TERM_WORDS:
            if phrase in lower:
                issues.append(
                    SanityIssue(
                        "feasibility.long_term_action",
                        "error",
                        f"Recommendation includes long-term action '{phrase}' that is not feasible within 24 hours.",
                    )
                )

        inventory_text = self._flatten_text(
            (agents.get("inventory") or {}).get("recommendation") or {}
        ).lower()
        if inventory_text and any(word in inventory_text for word in ("order", "restock", "reorder")):
            if not any(word in inventory_text for word in self.SHORT_TERM_WORDS):
                issues.append(
                    SanityIssue(
                        "feasibility.inventory_timing",
                        "warning",
                        "Inventory action does not clearly state a 24-hour or pre-Friday timing.",
                    )
                )

        return issues

    def _quantities_near_ingredient(self, text: str, ingredient: str) -> list[float]:
        quantities = []
        ingredient_pattern = re.escape(ingredient)
        for line in text.splitlines():
            if not re.search(ingredient_pattern, line, re.I):
                continue
            for qty_match in re.finditer(
                r"\b(\d+(?:\.\d+)?)\s*(?:kg|kilograms?|litres?|liters?|units?|cans?)\b",
                line,
                re.I,
            ):
                quantities.append(float(qty_match.group(1)))
        return quantities

    def _flatten_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return "\n".join(self._flatten_text(v) for v in value.values())
        if isinstance(value, list):
            return "\n".join(self._flatten_text(v) for v in value)
        return str(value)

    def _to_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _summarize(self, issues: list[SanityIssue]) -> str:
        errors = sum(1 for issue in issues if issue.severity == "error")
        warnings = sum(1 for issue in issues if issue.severity == "warning")
        if errors or warnings:
            return f"{errors} error(s), {warnings} warning(s)"
        return "0 errors, 0 warnings"

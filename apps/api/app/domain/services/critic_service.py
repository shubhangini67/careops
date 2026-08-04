from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.infrastructure.db.models import DecisionLog, CriticVerdict
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.prompt_utils import PromptUtils
from app.domain.services.cost_aware_scoring import CostAwareScoringService
from app.domain.services.evaluation_sanity import EvaluationSanityChecker


class CriticService:
    """Validates AI recommendations against operational rules and logs decisions."""

    DEFAULT_DIMENSIONS = {
        "safety": 0.5,
        "feasibility": 0.5,
        "evidence": 0.5,
        "actionability": 0.5,
        "clarity": 0.5,
    }

    _RULES_TEMPLATE = """
1. Maximum restaurant capacity is {capacity} guests at any time.
2. Do not recommend closing the restaurant or cancelling all reservations.
3. Staffing recommendations must not exceed 20 additional staff members.
4. Price changes must not exceed 30% increase or decrease from current price.
5. Any recommendation involving food safety must follow standard health guidelines.
6. Inventory reorder recommendations must be for realistic quantities (not more than 3x current stock).
7. Do not recommend actions that would negatively impact already confirmed reservations.
8. All recommendations must be actionable within a 24 hour window.
9. When inventory has critical shortages, recommendations must explicitly prioritise those ingredients before non-critical actions.
10. Inventory recommendations must focus on immediate restocking needed for the next service window, not broad long-term replenishment.
"""

    def __init__(self, db: Session, llm: BaseLLMProvider, capacity: int = 70):
        self.db = db
        self.llm = llm
        self.capacity = capacity
        self.RULES = self._RULES_TEMPLATE.format(capacity=capacity)
        self.sanity_checker = EvaluationSanityChecker(capacity=capacity)
        self.cost_scoring = CostAwareScoringService()

    async def evaluate(self, agent: str, recommendation: dict, input_summary: str = None) -> dict:
        """Evaluate a recommendation and return critic verdict."""

        recommendation_text = input_summary or str(
            recommendation.get("recommendation", recommendation)
        )

        sanity_report = (
            self.sanity_checker.check_bundle(recommendation)
            if isinstance(recommendation, dict)
            else {"passed": True, "issues": [], "summary": "0 errors, 0 warnings"}
        )
        cost_analysis = (
            self.cost_scoring.evaluate_bundle(recommendation)
            if isinstance(recommendation, dict)
            else {}
        )

        stale_assumptions = sanity_report.get("stale_assumptions") or []
        prompt = PromptUtils.format_critic_prompt(
            recommendation=(
                f"{recommendation_text}\n\n"
                f"## Automated sanity checks\n"
                f"{self.sanity_checker.format_report(sanity_report)}\n\n"
                f"## Cross-agent assumption conflicts\n"
                f"{self.sanity_checker.format_stale_assumptions(stale_assumptions)}\n\n"
                f"## Cost-aware tradeoff analysis\n"
                f"{self.cost_scoring.format_report(cost_analysis)}"
            ),
            rules=self.RULES
        )

        verdict_raw = await self.llm.complete_json(
            prompt=prompt,
            system_prompt=PromptUtils.SYSTEM_CRITIC_AGENT
        )

        # Normalise verdict
        verdict_str = verdict_raw.get("verdict", "revision").lower()
        if verdict_str not in ["approved", "rejected", "revision"]:
            verdict_str = "revision"

        critic_score = float(verdict_raw.get("score", 0.5))
        critic_notes = verdict_raw.get("notes", "")
        dimension_scores = self._normalize_dimension_scores(
            verdict_raw.get("dimension_scores")
        )
        revision_reasons = self._normalize_string_list(
            verdict_raw.get("revision_reasons")
        )
        actionable_feedback = self._normalize_string_list(
            verdict_raw.get("actionable_feedback")
        )

        has_errors = any(
            issue.get("severity") == "error"
            for issue in sanity_report.get("issues", [])
        )
        has_hard_policy_error = any(
            issue.get("code", "").startswith("policy.")
            for issue in sanity_report.get("issues", [])
            if issue.get("severity") == "error"
        )
        tradeoff_score = float(cost_analysis.get("tradeoff_score", 0.5))
        cost_pressure = float(cost_analysis.get("cost_pressure_score", 0.5))

        if has_hard_policy_error:
            verdict_str = "rejected"
            critic_score = min(critic_score, 0.3)
            dimension_scores["safety"] = 0.3
            if not revision_reasons:
                revision_reasons.append(
                    "Policy violations must be resolved before this plan can be approved."
                )
        elif has_errors and verdict_str == "approved":
            verdict_str = "revision"
            critic_score = min(critic_score, 0.65)
            dimension_scores["feasibility"] = 0.65
            if not revision_reasons:
                revision_reasons.append(
                    "Automated sanity checks found operational issues that require revision."
                )
        elif (
            verdict_str == "approved"
            and tradeoff_score < 0.2
            and cost_pressure >= 0.9
        ):
            verdict_str = "revision"
            critic_score = min(critic_score, 0.68)
            dimension_scores["actionability"] = min(
                dimension_scores["actionability"], 0.68
            )
            revision_reasons.append(
                "Operational cost and benefit tradeoffs are weak for this service window."
            )

        if cost_pressure >= 0.75:
            dimension_scores["feasibility"] = min(dimension_scores["feasibility"], 0.7)
            actionable_feedback.extend(cost_analysis.get("recommended_focus", []))
            if not any("tradeoff" in reason.lower() or "operational cost" in reason.lower() for reason in revision_reasons):
                revision_reasons.append(
                    "High operational pressure means the plan should focus on the most valuable actions first."
                )

        if sanity_report.get("issues"):
            critic_notes = (
                f"{critic_notes} Automated sanity checks: "
                f"{sanity_report['summary']}."
            ).strip()
            actionable_feedback.extend(
                issue.get("message", "")
                for issue in sanity_report.get("issues", [])
                if issue.get("severity") == "error"
            )

        if stale_assumptions:
            critic_notes = (
                f"{critic_notes} Cross-agent assumption conflicts: "
                f"{len(stale_assumptions)} detected."
            ).strip()
            actionable_feedback.extend(
                item.get("conflict", "") for item in stale_assumptions
            )

        revision_reasons = self._dedupe_preserve_order(revision_reasons)
        actionable_feedback = self._dedupe_preserve_order(actionable_feedback)

        return {
            "agent": agent,
            "verdict": verdict_str,
            "score": critic_score,
            "notes": critic_notes,
            "recommendation": recommendation_text,
            "sanity_checks": sanity_report,
            "cost_analysis": cost_analysis,
            "dimension_scores": dimension_scores,
            "revision_reasons": revision_reasons,
            "actionable_feedback": actionable_feedback,
            "stale_assumptions": stale_assumptions,
        }

    async def evaluate_and_log(
        self,
        agent: str,
        recommendation: dict,
        input_summary: str = None,
        retrieved_context: str = None,
        reasoning_summary: str = None,
    ) -> dict:
        """Evaluate a recommendation and persist the decision to the database."""

        result = await self.evaluate(agent, recommendation, input_summary)

        # Map string verdict to enum
        verdict_map = {
            "approved": CriticVerdict.approved,
            "rejected": CriticVerdict.rejected,
            "revision": CriticVerdict.revision,
        }

        log = DecisionLog(
            agent=agent,
            input_summary=input_summary,
            retrieved_context=retrieved_context,
            reasoning_summary=reasoning_summary,
            action_recommended=result["recommendation"],
            critic_verdict=verdict_map.get(result["verdict"], CriticVerdict.revision),
            critic_score=result["score"],
            critic_notes=result["notes"],
            metadata_={
                "sanity_checks": result.get("sanity_checks"),
                "cost_analysis": result.get("cost_analysis"),
                "dimension_scores": result.get("dimension_scores"),
                "revision_reasons": result.get("revision_reasons", []),
                "actionable_feedback": result.get("actionable_feedback", []),
                "stale_assumptions": result.get("stale_assumptions", []),
            },
            created_at=datetime.now(timezone.utc),

        )

        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)

        result["decision_log_id"] = log.id
        return result

    def _normalize_dimension_scores(self, raw_scores: dict | None) -> dict:
        scores = dict(self.DEFAULT_DIMENSIONS)
        if not isinstance(raw_scores, dict):
            return scores

        for key in scores:
            value = raw_scores.get(key)
            try:
                if value is not None:
                    scores[key] = max(0.0, min(float(value), 1.0))
            except (TypeError, ValueError):
                continue
        return scores

    def _normalize_string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    def _dedupe_preserve_order(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

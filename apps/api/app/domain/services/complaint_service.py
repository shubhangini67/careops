from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.domain.scenarios import ScenarioDefinition
from app.domain.services.business_analytics_service import BusinessAnalyticsService
from app.infrastructure.db.models import Feedback, SentimentType
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.prompt_utils import PromptUtils


class ComplaintService:
    """Analyses customer feedback and identifies recurring complaint patterns."""

    def __init__(self, db: Session, llm: BaseLLMProvider):
        self.db = db
        self.llm = llm

    def get_recent_feedback(self, days: int = 28) -> dict:
        """Get feedback summary for the last N days."""

        since = datetime.now() - timedelta(days=days)

        all_feedback = self.db.query(Feedback).filter(
            Feedback.created_at >= since
        ).all()

        negative = [f for f in all_feedback if f.sentiment == SentimentType.negative]
        positive = [f for f in all_feedback if f.sentiment == SentimentType.positive]
        neutral  = [f for f in all_feedback if f.sentiment == SentimentType.neutral]

        return {
            "total_feedback": len(all_feedback),
            "negative_count": len(negative),
            "positive_count": len(positive),
            "neutral_count": len(neutral),
            "negative_pct": round((len(negative) / len(all_feedback)) * 100, 1) if all_feedback else 0,
            "negative_texts": [f.raw_text for f in negative],
            "positive_texts": [f.raw_text for f in positive],
        }

    def get_complaint_summary(self, days: int = 28) -> dict:
        """Get structured complaint data ready for LLM analysis."""

        feedback = self.get_recent_feedback(days)

        # Deduplicate complaint texts for cleaner LLM input
        unique_complaints = list(set(feedback["negative_texts"]))
        unique_positives  = list(set(feedback["positive_texts"]))

        # Category breakdown -- the LLM previously had to infer themes itself from raw
        # complaint text every time. This hands it the same quantified counts
        # ("Wait Time: 10 of 28 days") the Today dashboard already computes and shows.
        category_breakdown = BusinessAnalyticsService(self.db).get_complaints_by_category(days=days)

        return {
            "period_days": days,
            "total_feedback": feedback["total_feedback"],
            "sentiment_breakdown": {
                "negative": feedback["negative_count"],
                "positive": feedback["positive_count"],
                "neutral":  feedback["neutral_count"],
                "negative_pct": feedback["negative_pct"],
            },
            "unique_complaints": unique_complaints,
            "unique_positives": unique_positives,
            "category_breakdown": category_breakdown,
        }

    async def analyse_and_recommend(
        self,
        days: int = 28,
        scenario_profile: ScenarioDefinition | None = None,
        target_date: datetime | None = None,
        rag_context: dict | None = None,
    ) -> dict:
        """Analyse complaints and generate recommendation, grounded in RAG context when provided."""
        import asyncio
        summary = await asyncio.to_thread(self.get_complaint_summary, days)
        scenario_label = scenario_profile["label"] if scenario_profile else "Friday Rush"
        service_window = scenario_profile["service_window"] if scenario_profile else "18:00-22:00"
        operational_focus = (
            scenario_profile["operational_focus"]
            if scenario_profile
            else "Rush execution, table turns, and same-day quality control."
        )
        scenario_watchouts = self._scenario_watchouts((scenario_profile or {}).get("id", "friday_rush"))
        summary["scenario_label"] = scenario_label
        summary["service_window"] = service_window
        summary["scenario_watchouts"] = scenario_watchouts
        if target_date:
            summary["target_date"] = target_date.strftime("%Y-%m-%d")

        similar_complaints = (rag_context or {}).get("similar_complaints", [])
        relevant_sops      = (rag_context or {}).get("relevant_sops", [])

        rag_section = ""
        if similar_complaints or relevant_sops:
            parts = []
            if similar_complaints:
                texts = [r["text"] for r in similar_complaints if r.get("text")]
                parts.append("Similar past complaints retrieved from memory:\n" +
                             "\n".join(f"- {t}" for t in texts))
            if relevant_sops:
                texts = [r["text"] for r in relevant_sops if r.get("text")]
                parts.append("Relevant operational SOPs:\n" +
                             "\n".join(f"- {t}" for t in texts))
            rag_section = "\n\n## Retrieved context (ground your recommendations in this)\n" + "\n\n".join(parts)

        prompt = PromptUtils.format_complaint_prompt(
            scenario_label=scenario_label,
            service_window=service_window,
            operational_focus=operational_focus,
            summary=summary,
            scenario_watchouts=scenario_watchouts,
            rag_section=rag_section,
        )

        recommendation = await self.llm.complete_json(
            prompt=prompt,
            system_prompt=PromptUtils.SYSTEM_COMPLAINT_AGENT
        )

        return {
            "service": "complaint",
            "data": summary,
            "recommendation": recommendation
        }

    def _scenario_watchouts(self, scenario_id: str) -> list[str]:
        watchouts = {
            "weekday_lunch": [
                "Fast lunch pacing matters more than broad menu experimentation.",
                "Takeaway packaging, handoff speed, and cashier flow are high-sensitivity points.",
            ],
            "holiday_spike": [
                "Queue growth and delayed dispatch will be amplified under surge demand.",
                "Quality slippage under heavy volume is more damaging than small menu restraint.",
            ],
            "low_stock_weekend": [
                "Stockout disappointment and inconsistent substitutions are the main guest risk.",
                "Front-of-house communication needs to stay ahead of unavailable items.",
            ],
            "friday_rush": [
                "Wait times, pizza temperature, and table turns remain the main Friday rush risks.",
                "Peak-hour guest communication should stay tight when the kitchen is under pressure.",
            ],
        }
        # Any ad-hoc/custom or live-composed scenario (id not one of the 4 named
        # presets above) has no hardcoded watchout list of its own -- returning
        # Friday Rush's text here (the old behaviour) silently mislabeled every
        # single custom-profile run as a Friday rush, regardless of what was
        # actually asked for. Empty is honest; the real specifics for these
        # scenarios already live in operational_focus, injected separately above.
        return watchouts.get(scenario_id, [])

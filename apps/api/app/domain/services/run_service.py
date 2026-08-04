from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.db.models import PlanningRun


class RunService:
    """Persists and retrieves planning runs for audit/history views."""

    def __init__(self, db: Session):
        self.db = db

    def create_from_response(self, response: dict[str, Any], org_id: int | None = None) -> PlanningRun:
        critic = response.get("critic") or {}
        meta = response.get("meta") or {}

        run = PlanningRun(
            org_id=org_id,
            scenario=response.get("scenario") or "unknown",
            target_date=response.get("target_date"),
            status=response.get("status") or "unknown",
            critic_verdict=critic.get("verdict"),
            critic_score=critic.get("score"),
            decision_log_id=critic.get("decision_log_id"),
            final_response=response,
            recommendations=response.get("recommendations"),
            rag_context=response.get("rag_context"),
            critic=critic,
            metadata_=meta,
            generated_at=self._parse_datetime(response.get("generated_at")),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def list_runs(
        self,
        org_id: int,
        limit: int = 25,
        scenario: str | None = None,
        status: str | None = None,
        verdict: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[PlanningRun]:
        query = self.db.query(PlanningRun).filter(PlanningRun.org_id == org_id)
        if scenario:
            query = query.filter(PlanningRun.scenario == scenario)
        if status:
            query = query.filter(PlanningRun.status == status)
        if verdict:
            query = query.filter(PlanningRun.critic_verdict == verdict)
        if date_from:
            query = query.filter(PlanningRun.created_at >= date_from)
        if date_to:
            query = query.filter(PlanningRun.created_at <= date_to + " 23:59:59")
        return (
            query.order_by(PlanningRun.created_at.desc(), PlanningRun.id.desc())
            .limit(limit)
            .all()
        )

    def get_run(self, run_id: int, org_id: int) -> PlanningRun | None:
        return (
            self.db.query(PlanningRun)
            .filter(PlanningRun.id == run_id, PlanningRun.org_id == org_id)
            .first()
        )

    def to_summary(self, run: PlanningRun) -> dict[str, Any]:
        # scenario_profile.label is the real resolved title (e.g. "Anniversary
        # Dinner" for a custom run, "Friday Rush" for a preset) -- run.scenario
        # itself is just the id ("custom" for every natural-language-derived
        # run, indistinguishable from every other custom run without this).
        metadata = run.metadata_ or {}
        scenario_profile = metadata.get("scenario_profile") or {}
        scenario_label = scenario_profile.get("label")

        return {
            "id": run.id,
            "scenario": run.scenario,
            "scenario_label": scenario_label,
            "target_date": run.target_date,
            "status": run.status,
            "critic_verdict": run.critic_verdict,
            "critic_score": run.critic_score,
            "decision_log_id": run.decision_log_id,
            "generated_at": self._format_datetime(run.generated_at),
            "created_at": self._format_datetime(run.created_at),
            "total_cost_usd": metadata.get("total_cost_usd"),
            "total_tokens": metadata.get("total_tokens"),
            "total_duration_ms": metadata.get("total_duration_ms"),
            "llm_model": metadata.get("llm_model"),
            "llm_provider": metadata.get("llm_provider"),
            "cache_hit": metadata.get("cache_hit"),
            "llm_call_count": metadata.get("llm_call_count"),
            "replan_count": metadata.get("replan_count"),
            "risk_tags": self._derive_risk_tags(run.final_response or {}),
        }

    def _derive_risk_tags(self, final_response: dict[str, Any]) -> list[str]:
        """Cheap, real per-run callouts for the run-history list -- no LLM
        call, just reading fields the pipeline already computed. Same 15%
        demand-spike threshold AgentIntelligencePanel.tsx already uses for
        "busier than usual" so the two don't disagree.
        """
        tags: list[str] = []
        recs = final_response.get("recommendations") or {}
        forecast_data = (recs.get("forecast") or {}).get("data") or {}

        for reason in forecast_data.get("adjustment_reasons") or []:
            if not isinstance(reason, str):
                continue
            label = reason.split("(")[-1].split(")")[0].strip() if "(" in reason else ""
            if reason.startswith("weather") and label:
                tags.append(label.replace("_", " ").title())
            elif reason.startswith("holiday") and label:
                tags.append(label.title())

        inventory_data = (recs.get("inventory") or {}).get("data") or {}
        shortages = inventory_data.get("shortage_alerts") or []
        if any(isinstance(a, dict) and a.get("severity") == "critical" for a in shortages):
            tags.append("Inventory Alert")

        predicted = forecast_data.get("predicted_orders")
        baseline = forecast_data.get("avg_same_day_orders") or forecast_data.get("avg_friday_orders")
        if isinstance(predicted, (int, float)) and isinstance(baseline, (int, float)) and baseline > 0:
            diff_pct = (predicted - baseline) / baseline * 100
            if diff_pct >= 15:
                tags.append("High Demand")

        return tags[:3]

    def to_detail(self, run: PlanningRun) -> dict[str, Any]:
        return {
            **self.to_summary(run),
            "final_response": run.final_response,
            "recommendations": run.recommendations,
            "rag_context": run.rag_context,
            "critic": run.critic,
            "metadata": run.metadata_,
        }

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _format_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None

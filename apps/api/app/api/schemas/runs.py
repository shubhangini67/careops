from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanningRunSummary(BaseModel):
    id: int
    scenario: str
    # The real scenario title (e.g. "Anniversary Dinner", "Limited Service")
    # -- for a custom (natural-language-derived) run, `scenario` itself is
    # just the literal id "custom", never the actual descriptive name that
    # was resolved into scenario_profile.label. None only for runs recorded
    # before this field existed (no scenario_profile in their stored meta).
    scenario_label: str | None = None
    target_date: str | None = None
    status: str
    critic_verdict: str | None = None
    critic_score: float | None = None
    decision_log_id: int | None = None
    generated_at: str | None = None
    created_at: str | None = None
    # AI infrastructure observability -- read from the run's stored metadata
    # so the Observability tab can show a cost/token/duration breakdown
    # across many runs without a separate detail fetch per row.
    total_cost_usd: float | None = None
    total_tokens: int | None = None
    total_duration_ms: float | None = None
    llm_model: str | None = None
    llm_provider: str | None = None
    cache_hit: bool | None = None
    llm_call_count: int | None = None
    replan_count: int | None = None
    # Cheap per-run risk callouts derived from already-loaded final_response
    # (weather/holiday demand multipliers, critical shortages, demand spikes)
    # -- lets the run-history list surface "Heavy Rain" / "Inventory Alert"
    # style tags per row without a separate detail fetch per run.
    risk_tags: list[str] = Field(default_factory=list)


class PlanningRunDetail(PlanningRunSummary):
    final_response: dict[str, Any]
    recommendations: dict[str, Any] | None = None
    rag_context: dict[str, Any] | None = None
    critic: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class PlanningRunListResponse(BaseModel):
    runs: list[PlanningRunSummary]


class DataRange(BaseModel):
    count: int
    date_range: list[str | None] = Field(default_factory=list)


class ScenarioCoverage(BaseModel):
    scenario: str
    label: str
    date: str
    reservations: int
    guests: int
    waitlist: int
    occupancy_pct: float


class FeedbackHealth(DataRange):
    negative: int
    positive: int
    neutral: int
    negative_pct: float


class InventoryHealth(BaseModel):
    items: int
    shortage_alerts: int
    critical_shortages: int
    overstock_alerts: int


class DataHealthResponse(BaseModel):
    orders: DataRange
    reservations: DataRange
    feedback: FeedbackHealth
    inventory: InventoryHealth
    menu: dict[str, int]
    scenario_coverage: list[ScenarioCoverage]
    status: Literal["ok"] = "ok"

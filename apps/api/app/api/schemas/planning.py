"""
Request and response schemas for the planning endpoints.

Kept in a dedicated file so the route handler stays clean
and schemas can be reused by future endpoints.

Enhanced for P1-10 to support:
- Multi-date simulations
- Critic override testing
- Simulation mode for deterministic outputs
- Debug observability for LangGraph state inspection
"""

from typing import Any, Optional, Literal, Dict
from datetime import datetime

from pydantic import BaseModel, Field


PlanningScenarioId = Literal[
    "ed_surge",
    "opd_peak",
    "icu_capacity",
    "supply_shortage",
    "friday_rush",
    "weekday_lunch",
    "holiday_spike",
    "low_stock_weekend",
]


# ── Ad-hoc scenario profiles (P6-A25) ────────────────────────────────────────
# Natural-language intake alongside the 4 presets above -- presets stay
# literal-constrained by design (one-click shortcuts), this is the parallel
# free-form path. See ScenarioProfileService for how these get derived.

class ScenarioProfilePayload(BaseModel):
    """Ad-hoc scenario profile derived from natural language, carried alongside
    a non-preset `scenario` id on PlanningRunRequest. Always fully populated
    (ScenarioProfileService guarantees this) so downstream direct dict-key
    access in complaint/inventory/reservation services never KeyErrors."""

    id: str = "custom"
    label: str
    description: str = ""
    service_window: str
    operational_focus: str
    cuisine: Optional[str] = None


class ScenarioProfileRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Free-form description of tonight's service, e.g. 'we're hosting an event today, expecting large turnover'.",
    )


class ScenarioProfileResponse(BaseModel):
    profile: ScenarioProfilePayload


# ── Request ───────────────────────────────────────────────────────────────────

class FridayRushRequest(BaseModel):
    """
    Request schema for generating a Friday Rush operational plan.

    Attributes:
        target_date: Optional ISO date string. Defaults to the next Friday
                     if not provided.
        simulation_mode: Enables deterministic outputs using mock or
                         rule-based data instead of real forecasting.
        force_critic_decision: Overrides the critic's verdict for testing.
        debug: Enables verbose logs and LangGraph state inspection.
    """

    target_date: Optional[str] = Field(
        default=None,
        description=(
            "ISO date string for the target Friday, "
            "e.g. '2026-04-11'. Defaults to the next Friday."
        ),
        examples=["2026-04-11"],
    )

    simulation_mode: bool = Field(
        default=False,
        description=(
            "Runs the system in simulation mode using mock or "
            "deterministic data instead of real forecasting."
        ),
        examples=[False],
    )

    force_critic_decision: Optional[
        Literal["approved", "rejected", "revision"]
    ] = Field(
        default=None,
        description=(
            "Overrides the critic's decision for testing purposes. "
            "If provided, the critic will return this verdict."
        ),
        examples=["approved", "rejected"],
    )

    debug: bool = Field(
        default=False,
        description=(
            "Enables verbose logging and includes LangGraph state "
            "snapshots in the response meta."
        ),
        examples=[True],
    )


class PlanningRunRequest(FridayRushRequest):
    scenario: str = Field(
        default="friday_rush",
        description=(
            "Scenario preset id (friday_rush/weekday_lunch/holiday_spike/low_stock_weekend), "
            "or a custom id (e.g. 'custom') when custom_profile is supplied (P6-A25)."
        ),
    )
    custom_profile: Optional[ScenarioProfilePayload] = Field(
        default=None,
        description=(
            "Ad-hoc natural-language-derived scenario profile (P6-A25, see "
            "POST /planning/scenario-from-text). Required when scenario is not "
            "one of the 4 presets -- the 4 presets ignore this field."
        ),
    )
    restaurant_id: Optional[int] = Field(
        default=None,
        description="ID of a restaurant profile to use for this run. Overrides org-level capacity and peak_hours.",
    )


class PlanningScenarioOption(BaseModel):
    id: PlanningScenarioId
    label: str
    description: str
    default_weekday: int
    service_window: str
    operational_focus: str


class PlanningScenarioListResponse(BaseModel):
    scenarios: list[PlanningScenarioOption]


# ── Per-agent recommendation block ───────────────────────────────────────────

class AgentRecommendations(BaseModel):
    """
    Consolidated recommendations from all agents involved in the
    Friday Rush planning workflow.
    """

    forecast: Optional[Dict[str, Any]] = None
    reservation: Optional[Dict[str, Any]] = None
    complaint: Optional[Dict[str, Any]] = None
    menu: Optional[Dict[str, Any]] = None
    inventory: Optional[Dict[str, Any]] = None


class CostAnalysisResult(BaseModel):
    cost_pressure_score: float = Field(
        description="0.0 to 1.0 score where higher means more operational pressure"
    )
    benefit_score: float = Field(
        description="0.0 to 1.0 score where higher means stronger expected operational benefit"
    )
    tradeoff_score: float = Field(
        description="0.0 to 1.0 score where higher means better cost/benefit balance"
    )
    pressure_components: Dict[str, float] = Field(default_factory=dict)
    benefit_components: Dict[str, float] = Field(default_factory=dict)
    tradeoff_notes: list[str] = Field(default_factory=list)
    recommended_focus: list[str] = Field(default_factory=list)
    signals: Dict[str, Any] = Field(default_factory=dict)


# ── Critic block ──────────────────────────────────────────────────────────────

class CriticResult(BaseModel):
    """
    Represents the evaluation outcome from the Critic Agent.
    """

    verdict: str = Field(
        description="approved | rejected | revision | unknown"
    )
    score: float = Field(
        description="0.0 – 1.0 quality score"
    )
    notes: str = ""
    cost_analysis: Optional[CostAnalysisResult] = None
    dimension_scores: Optional[Dict[str, float]] = Field(
        default=None,
        description="Per-dimension critic scoring for safety, feasibility, evidence, actionability, and clarity"
    )
    revision_reasons: list[str] = Field(
        default_factory=list,
        description="Short reasons explaining what weakened the plan"
    )
    actionable_feedback: list[str] = Field(
        default_factory=list,
        description="Concrete next changes the planner should make"
    )
    decision_log_id: Optional[int] = Field(
        default=None,
        description="ID of the persisted DecisionLog row"
    )
    sanity_checks: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Automated evaluation sanity-check report"
    )
    stale_assumptions: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cross-agent assumption conflicts detected by EvaluationSanityChecker"
    )


# ── Response ──────────────────────────────────────────────────────────────────

class FridayRushResponse(BaseModel):
    """
    Response schema for the Friday Rush Planner.
    Aggregates insights from all agents along with critic feedback
    and optional RAG context.
    """

    scenario: str
    target_date: Optional[str]
    status: str = Field(
        description="ready | needs_review | blocked | unknown"
    )
    generated_at: str
    recommendations: AgentRecommendations
    rag_context: Optional[Dict[str, Any]] = None
    critic: CriticResult
    meta: Dict[str, Any] = Field(default_factory=dict)
    cache_hit: Optional[bool] = Field(
        default=None,
        description="True if this response was served from cache; False if freshly computed; None for legacy/compat responses",
    )
    # Swiggy market intelligence outputs (P6-S11/S12)
    market_intel: Optional[Dict[str, Any]] = None
    swiggy_competitor_context: Optional[Dict[str, Any]] = None
    swiggy_occupancy_context: Optional[Dict[str, Any]] = None
    swiggy_procurement_options: Optional[Dict[str, Any]] = None
    dineout_manager: Optional[Dict[str, Any]] = None
    situation_summary: Optional[str] = Field(
        default=None,
        description="Natural-language 'situation + tailored key takeaways' briefing, generated once post-critic-approval. None when the LLM call failed open.",
    )


# ── What-if simulator ─────────────────────────────────────────────────────────

class WhatIfRequest(BaseModel):
    predicted_covers: int = Field(
        ge=1, le=1000,
        description="What-if cover count to evaluate",
    )
    avg_covers: float = Field(
        gt=0,
        description="Historical baseline average covers from the existing run",
    )
    scenario: str = Field(default="friday_rush")
    service_window: str = Field(default="18:00-22:00")


class WhatIfResponse(BaseModel):
    scenario: str
    service_window: str
    predicted_covers: int
    avg_covers: float
    demand_ratio: float
    cost_pressure_score: float
    benefit_score: float
    tradeoff_score: float
    pressure_components: Dict[str, float]
    tradeoff_notes: list[str]
    recommended_focus: list[str]


# ── Scenario recommendation (P6-MI10) ────────────────────────────────────────

class ScenarioRecommendationResponse(BaseModel):
    recommended_scenario: PlanningScenarioId
    reason: str
    confidence: Literal["high", "medium", "low"]
    signals_used: list[str] = Field(default_factory=list)


# ── Live scenario composition -- the "Run for today" instant path ───────────
# Not constrained to the 4 presets (see ScenarioRecommendationResponse above)
# -- composes a fresh profile from real signals instead of picking one of a
# fixed set, so it can never produce a mismatched label like recommending
# "low_stock_weekend" on a Wednesday.

class LiveScenarioCompositionResponse(BaseModel):
    profile: ScenarioProfilePayload
    reason: str
    confidence: Literal["high", "medium", "low"]
    signals_used: list[str] = Field(default_factory=list)

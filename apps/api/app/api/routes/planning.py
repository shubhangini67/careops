"""Planning routes for reusable multi-scenario orchestration."""

import json as _json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user, get_db, get_llm, get_orchestration_deps
from app.infrastructure.db.models import Organization, RestaurantProfile
from app.api.schemas.planning import (
    FridayRushRequest,
    FridayRushResponse,
    LiveScenarioCompositionResponse,
    PlanningRunRequest,
    PlanningScenarioListResponse,
    ScenarioProfilePayload,
    ScenarioProfileRequest,
    ScenarioProfileResponse,
    ScenarioRecommendationResponse,
    WhatIfRequest,
    WhatIfResponse,
)
from app.core.exceptions import AppError
from app.domain.scenarios import list_scenarios
from app.domain.services.cost_aware_scoring import CostAwareScoringService
from app.domain.services.live_scenario_composer import LiveScenarioComposer
from app.domain.services.run_service import RunService
from app.domain.services.scenario_profile_service import ScenarioProfileService
from app.infrastructure.llm.audio_transcription import transcribe as transcribe_audio
from app.domain.services.scenario_recommender import ScenarioRecommender
from app.domain.services.workflow_trigger_service import WorkflowTriggerService
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.cache.plan_cache import build_cache_key, cache_plan, get_cached_plan
from app.infrastructure.swiggy.client import SwiggyMCPClient
from app.orchestration import run_friday_rush, run_planning_scenario, stream_planning_scenario

router = APIRouter(prefix="/planning", tags=["planning"])


@router.get(
    "/scenarios",
    response_model=PlanningScenarioListResponse,
    summary="List supported planning scenarios",
)
def get_scenarios() -> PlanningScenarioListResponse:
    return PlanningScenarioListResponse(scenarios=list_scenarios())


@router.post(
    "/scenario-from-text",
    response_model=ScenarioProfileResponse,
    summary="Derive an ad-hoc scenario profile from natural language",
    description=(
        "Converts a free-form description of tonight's service (e.g. "
        "'we're hosting an event today, expecting large turnover') into a "
        "structured scenario profile that can be passed as custom_profile "
        "on POST /planning/run or /planning/stream (P6-A25). The 4 existing "
        "presets are unaffected and remain available as one-click shortcuts."
    ),
)
async def scenario_from_text(
    body: ScenarioProfileRequest,
    llm: BaseLLMProvider = Depends(get_llm),
    current_user: dict = Depends(get_current_user),
) -> ScenarioProfileResponse:
    profile = await ScenarioProfileService(llm).derive_profile(body.text)
    return ScenarioProfileResponse(profile=ScenarioProfilePayload(**profile))


@router.post(
    "/transcribe",
    summary="Transcribe recorded voice input to text",
    description=(
        "Backs the planning modal's mic input -- transcribes a short recorded clip "
        "(e.g. audio/webm from the browser's MediaRecorder) via Groq's Whisper endpoint. "
        "Returns raw text only; the frontend shows it as an editable transcript before "
        "any plan is triggered, it is never auto-submitted."
    ),
)
async def transcribe(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    try:
        text = await transcribe_audio(audio_bytes, file.filename or "recording.webm")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc
    return {"text": text}


def _build_response(result: dict, meta: dict, fallback_scenario: str) -> FridayRushResponse:
    return FridayRushResponse(
        scenario=result.get("scenario", fallback_scenario),
        target_date=result.get("target_date"),
        status=result.get("status", "unknown"),
        generated_at=result.get("generated_at", ""),
        recommendations=result.get("recommendations", {}),
        rag_context=result.get("rag_context"),
        critic=result.get(
            "critic",
            {
                "verdict": "unknown",
                "score": 0.0,
                "notes": "No critic output available.",
                "decision_log_id": None,
            },
        ),
        meta=meta,
        market_intel=result.get("market_intel"),
        swiggy_competitor_context=result.get("swiggy_competitor_context"),
        swiggy_occupancy_context=result.get("swiggy_occupancy_context"),
        swiggy_procurement_options=result.get("swiggy_procurement_options"),
        dineout_manager=result.get("dineout_manager"),
        situation_summary=result.get("situation_summary"),
    )


def _decorate_meta(result: dict, body, scenario: str) -> dict:
    meta = result.get("meta", {})
    meta.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    meta.setdefault("scenario", scenario)
    if body.debug:
        meta.setdefault("debug", True)
        meta.setdefault("simulation_mode", body.simulation_mode)
        meta.setdefault("forced_critic_decision", body.force_critic_decision)
    return meta


@router.post(
    "/run",
    response_model=FridayRushResponse,
    summary="Run a planning scenario",
    description=(
        "Triggers the shared multi-agent orchestration for a selected scenario preset. "
        "Supports Friday rush, weekday lunch, holiday spike, and low-stock weekend framing."
    ),
)
async def run_planning(
    body: PlanningRunRequest,
    deps: dict = Depends(get_orchestration_deps),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FridayRushResponse:
    custom_profile_dict = body.custom_profile.model_dump() if body.custom_profile else None

    # Cache is bypassed for simulation runs, forced critic decisions, debug
    # mode, and custom profiles -- two different natural-language descriptions
    # could otherwise share a cache key (P6-A25).
    cacheable = (
        not body.simulation_mode
        and not body.force_critic_decision
        and not body.debug
        and not custom_profile_dict
    )

    if cacheable:
        cache_key = build_cache_key(
            org_id=current_user["org_id"],
            scenario=body.scenario,
            target_date=body.target_date,
        )
        cached = await get_cached_plan(cache_key)
        if cached:
            cached["cache_hit"] = True
            if "meta" in cached:
                cached["meta"]["total_cost_usd"] = 0.0
                cached["meta"]["cache_hit"] = True
            # Persist cache hits so every run appears in history
            try:
                run = RunService(deps["db"]).create_from_response(
                    cached,
                    org_id=current_user.get("org_id"),
                )
                cached["meta"]["planning_run_id"] = run.id
            except Exception:
                pass
            # Cache hits still represent a real plan the owner is looking at right
            # now -- workflow triggers (P6-A11) must evaluate here too, not just on
            # the non-cached path below, otherwise a shortage that first appeared
            # before this feature existed (or whose action was since dismissed)
            # would never get re-flagged as long as the plan keeps hitting cache.
            try:
                await WorkflowTriggerService(deps["db"], deps["llm"]).evaluate_and_queue(current_user["org_id"], cached)
            except Exception:
                pass
            return FridayRushResponse(**cached)

    # Pull org settings so agents use tenant-configured capacity and hours
    org = db.query(Organization).filter(Organization.id == current_user["org_id"]).first()
    org_settings = org.settings or {} if org else {}
    org_capacity        = int(org_settings.get("capacity",         70))
    org_peak_hours      = str(org_settings.get("peak_hours",       "18:00-22:00"))
    org_critic_threshold = float(org_settings.get("critic_threshold", 0.7))

    # Resolve restaurant profile if provided — scoped to the caller's org
    restaurant_profile = None
    if body.restaurant_id:
        rp = db.query(RestaurantProfile).filter(
            RestaurantProfile.id == body.restaurant_id,
            RestaurantProfile.org_id == current_user["org_id"],
        ).first()
        if rp:
            restaurant_profile = {
                "id":         rp.id,
                "name":       rp.name,
                "cuisine":    rp.cuisine,
                "capacity":   rp.capacity,
                "peak_hours": rp.peak_hours,
                "timezone":   rp.timezone,
            }

    try:
        result = await run_planning_scenario(
            deps=deps,
            scenario=body.scenario,
            target_date=body.target_date,
            simulation_mode=body.simulation_mode,
            force_critic_decision=body.force_critic_decision,
            debug=body.debug,
            org_capacity=org_capacity,
            org_peak_hours=org_peak_hours,
            restaurant_profile=restaurant_profile,
            critic_threshold=org_critic_threshold,
            org_id=current_user["org_id"],
            custom_profile=custom_profile_dict,
        )
    except AppError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Orchestration failed: {exc}",
        )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestration returned an empty response.",
        )

    meta = _decorate_meta(result, body, body.scenario)
    try:
        run = RunService(deps["db"]).create_from_response(
            {**result, "meta": meta},
            org_id=current_user.get("org_id"),
        )
        meta.setdefault("planning_run_id", run.id)
    except Exception as exc:
        meta.setdefault("run_persistence_error", str(exc))

    # Built-in workflow triggers (P6-A11) -- evaluated after every real run (not
    # cache hits, which already evaluated this on their original run). Never lets
    # a trigger-evaluation failure break the planning response itself.
    try:
        await WorkflowTriggerService(deps["db"], deps["llm"]).evaluate_and_queue(current_user["org_id"], result)
    except Exception as exc:
        meta.setdefault("workflow_trigger_error", str(exc))

    response = _build_response(result, meta, body.scenario)
    response.cache_hit = False

    if cacheable and response.critic.verdict == "approved":
        await cache_plan(cache_key, response.model_dump())

    return response


@router.post(
    "/stream",
    summary="Run a planning scenario with SSE streaming",
    description=(
        "Identical request body to /run. Streams results node-by-node via Server-Sent Events. "
        "Emits 'node_complete' events as each agent finishes, then a 'complete' event with the full response."
    ),
)
async def stream_planning(
    body: PlanningRunRequest,
    deps: dict = Depends(get_orchestration_deps),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    custom_profile_dict = body.custom_profile.model_dump() if body.custom_profile else None

    cacheable = (
        not body.simulation_mode
        and not body.force_critic_decision
        and not body.debug
        and not custom_profile_dict
    )

    org = db.query(Organization).filter(Organization.id == current_user["org_id"]).first()
    org_settings = org.settings or {} if org else {}
    org_capacity         = int(org_settings.get("capacity",         70))
    org_peak_hours       = str(org_settings.get("peak_hours",       "18:00-22:00"))
    org_critic_threshold = float(org_settings.get("critic_threshold", 0.7))

    restaurant_profile = None
    if body.restaurant_id:
        rp = db.query(RestaurantProfile).filter(
            RestaurantProfile.id == body.restaurant_id,
            RestaurantProfile.org_id == current_user["org_id"],
        ).first()
        if rp:
            restaurant_profile = {
                "id": rp.id, "name": rp.name, "cuisine": rp.cuisine,
                "capacity": rp.capacity, "peak_hours": rp.peak_hours, "timezone": rp.timezone,
            }

    cache_key = build_cache_key(
        org_id=current_user["org_id"],
        scenario=body.scenario,
        target_date=body.target_date,
    ) if cacheable else None

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {_json.dumps(data)}\n\n"

    async def event_generator():
        # Cache hit — emit all nodes instantly, then the full response
        if cacheable and cache_key:
            cached = await get_cached_plan(cache_key)
            if cached:
                for node in ["forecast", "reservation", "complaint", "menu", "inventory", "aggregator", "critic"]:
                    yield _sse("node_complete", {"node": node, "cached": True})
                cached["cache_hit"] = True
                if "meta" in cached:
                    cached["meta"]["total_cost_usd"] = 0.0
                    cached["meta"]["cache_hit"] = True
                try:
                    run = RunService(deps["db"]).create_from_response(cached, org_id=current_user.get("org_id"))
                    cached["meta"]["planning_run_id"] = run.id
                except Exception:
                    pass
                yield _sse("complete", cached)
                return

        # Full streaming run
        try:
            async for evt in stream_planning_scenario(
                deps=deps,
                scenario=body.scenario,
                target_date=body.target_date,
                simulation_mode=body.simulation_mode,
                force_critic_decision=body.force_critic_decision,
                debug=body.debug,
                org_capacity=org_capacity,
                org_peak_hours=org_peak_hours,
                restaurant_profile=restaurant_profile,
                critic_threshold=org_critic_threshold,
                org_id=current_user["org_id"],
                custom_profile=custom_profile_dict,
            ):
                if evt["event"] == "node_start":
                    yield _sse("node_start", {"node": evt["node"], "hint": evt.get("hint", "")})

                elif evt["event"] == "node_complete":
                    yield _sse("node_complete", {"node": evt["node"], "hint": evt.get("hint", "")})

                elif evt["event"] == "complete":
                    result = evt["response"]
                    meta = _decorate_meta(result, body, body.scenario)
                    try:
                        run = RunService(deps["db"]).create_from_response(
                            {**result, "meta": meta}, org_id=current_user.get("org_id")
                        )
                        meta.setdefault("planning_run_id", run.id)
                    except Exception as exc:
                        meta.setdefault("run_persistence_error", str(exc))

                    final_resp = _build_response(result, meta, body.scenario)
                    final_resp.cache_hit = False

                    if cacheable and cache_key and final_resp.critic.verdict == "approved":
                        await cache_plan(cache_key, final_resp.model_dump())

                    yield _sse("complete", final_resp.model_dump())

                elif evt["event"] == "error":
                    yield _sse("error", {"message": evt.get("message", "Unknown error")})

        except Exception as exc:
            yield _sse("error", {"message": f"Stream error: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/whatif",
    response_model=WhatIfResponse,
    summary="What-if demand simulator",
    description=(
        "Recalculates demand ratios and cost/benefit tradeoffs for a user-supplied cover count. "
        "No LLM calls — purely deterministic. Use to explore 'what if I expect X covers?' without a full run."
    ),
)
def whatif_planning(
    body: WhatIfRequest,
    current_user: dict = Depends(get_current_user),
) -> WhatIfResponse:
    bundle = {
        "agents": {
            "forecast": {
                "data": {
                    "predicted_orders":    body.predicted_covers,
                    "avg_friday_orders":   body.avg_covers,
                    "avg_same_day_orders": body.avg_covers,
                },
                "recommendation": {},
            },
            "reservation": {"data": {"occupancy_pct": 0, "waitlist_count": 0}, "recommendation": {}},
            "inventory":   {"data": {"shortage_alerts": [], "overstock_alerts": []}, "recommendation": {}},
            "menu":        {"recommendation": {}},
        }
    }

    result = CostAwareScoringService().evaluate_bundle(bundle)

    return WhatIfResponse(
        scenario=body.scenario,
        service_window=body.service_window,
        predicted_covers=body.predicted_covers,
        avg_covers=body.avg_covers,
        demand_ratio=result["signals"]["demand_ratio"],
        cost_pressure_score=result["cost_pressure_score"],
        benefit_score=result["benefit_score"],
        tradeoff_score=result["tradeoff_score"],
        pressure_components=result["pressure_components"],
        tradeoff_notes=result["tradeoff_notes"],
        recommended_focus=result["recommended_focus"],
    )


@router.get(
    "/recommend",
    response_model=ScenarioRecommendationResponse,
    summary="Recommend a planning scenario for a target date",
    description=(
        "Suggests which scenario preset (friday_rush / weekday_lunch / holiday_spike / "
        "low_stock_weekend) best fits the target date, using recent run history, live "
        "Swiggy market signals, calendar context (weekend/holiday), and current inventory "
        "shortage pressure. Used by the dashboard to show a suggestion before the owner "
        "manually picks a scenario."
    ),
)
async def recommend_scenario(
    target_date: str = Query(..., description="ISO date string, e.g. 2026-07-05"),
    db: Session = Depends(get_db),
    llm=Depends(get_llm),
    current_user: dict = Depends(get_current_user),
) -> ScenarioRecommendationResponse:
    recommender = ScenarioRecommender(db=db, swiggy_client=SwiggyMCPClient(), llm=llm)
    result = await recommender.recommend(org_id=current_user["org_id"], target_date=target_date)
    return ScenarioRecommendationResponse(**result)


@router.get(
    "/compose-live-scenario",
    response_model=LiveScenarioCompositionResponse,
    summary="Compose a fresh scenario profile from live signals for 'right now'",
    description=(
        "Backs the 'Run for today' instant path. Unlike /recommend (which picks one of "
        "the 4 fixed presets), this composes a brand new profile from what's actually "
        "true right now -- real day-of-week, current time, weather, holiday, inventory "
        "shortage count, area occupancy -- so it can never produce a mismatched label "
        "(e.g. recommending a 'weekend' preset on a Wednesday). Returns a profile shaped "
        "like POST /planning/scenario-from-text's, safe to pass as custom_profile."
    ),
)
async def compose_live_scenario(
    target_date: str = Query(..., description="ISO date string, e.g. 2026-07-15"),
    db: Session = Depends(get_db),
    llm=Depends(get_llm),
    current_user: dict = Depends(get_current_user),
) -> LiveScenarioCompositionResponse:
    composer = LiveScenarioComposer(db=db, swiggy_client=SwiggyMCPClient(), llm=llm)
    result = await composer.compose(org_id=current_user["org_id"], target_date=target_date)
    return LiveScenarioCompositionResponse(
        profile=ScenarioProfilePayload(**result["profile"]),
        reason=result["reason"],
        confidence=result["confidence"],
        signals_used=result["signals_used"],
    )


@router.post(
    "/friday-rush",
    response_model=FridayRushResponse,
    summary="Run Friday Rush planning",
    description=(
        "Triggers the full multi-agent orchestration for the Friday Night Rush scenario. "
        "This route is kept for backward compatibility; new scenario-aware clients should use /planning/run."
    ),
)
async def friday_rush(
    body: FridayRushRequest,
    deps: dict = Depends(get_orchestration_deps),
    current_user: dict = Depends(get_current_user),
) -> FridayRushResponse:
    try:
        result = await run_friday_rush(
            deps=deps,
            target_date=body.target_date,
            simulation_mode=body.simulation_mode,
            force_critic_decision=body.force_critic_decision,
            debug=body.debug,
        )
    except AppError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Orchestration failed: {exc}",
        )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestration returned an empty response.",
        )

    meta = _decorate_meta(result, body, "friday_rush")
    try:
        run = RunService(deps["db"]).create_from_response(
            {**result, "meta": meta}, org_id=current_user.get("org_id")
        )
        meta.setdefault("planning_run_id", run.id)
    except Exception as exc:
        meta.setdefault("run_persistence_error", str(exc))

    return _build_response(result, meta, "friday_rush")

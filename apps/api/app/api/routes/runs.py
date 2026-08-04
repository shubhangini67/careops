from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.infrastructure.db.models import Organization
from app.api.schemas.runs import (
    DataHealthResponse,
    DataRange,
    FeedbackHealth,
    InventoryHealth,
    PlanningRunDetail,
    PlanningRunListResponse,
    ScenarioCoverage,
)
from app.domain.scenarios import list_scenarios
from app.domain.services.inventory_service import InventoryService
from app.domain.services.run_service import RunService
from app.infrastructure.db.models import (
    Feedback,
    Inventory,
    MenuItem,
    Order,
    PlanningRun,
    Reservation,
    ReservationStatus,
    SentimentType,
)

router = APIRouter(tags=["runs"])


@router.get("/runs", response_model=PlanningRunListResponse)
def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    scenario: str | None = None,
    status: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> PlanningRunListResponse:
    service = RunService(db)
    runs = service.list_runs(
        org_id=current_user["org_id"],
        limit=limit,
        scenario=scenario,
        status=status,
        verdict=verdict,
        date_from=date_from,
        date_to=date_to,
    )
    return PlanningRunListResponse(runs=[service.to_summary(run) for run in runs])


@router.get("/runs/{run_id}", response_model=PlanningRunDetail)
def get_run(run_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)) -> PlanningRunDetail:
    service = RunService(db)
    run = service.get_run(run_id, org_id=current_user["org_id"])
    if run is None:
        raise HTTPException(status_code=404, detail="Planning run not found.")
    return PlanningRunDetail(**service.to_detail(run))


@router.get("/runs/{run_id}/export", summary="Export planning run as PDF")
def export_run_pdf(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Response:
    from app.infrastructure.pdf.report_generator import generate_run_pdf

    service = RunService(db)
    run = service.get_run(run_id, org_id=current_user["org_id"])
    if run is None:
        raise HTTPException(status_code=404, detail="Planning run not found.")

    detail = service.to_detail(run)
    pdf_bytes = generate_run_pdf(detail)

    scenario = (detail.get("scenario") or "run").replace("_", "-")
    filename = f"careops-{scenario}-{run_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/export/excel", summary="Export planning run as Excel workbook")
def export_run_excel(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Response:
    from app.infrastructure.excel.report_generator import generate_run_excel

    service = RunService(db)
    run = service.get_run(run_id, org_id=current_user["org_id"])
    if run is None:
        raise HTTPException(status_code=404, detail="Planning run not found.")

    detail = service.to_detail(run)
    xlsx_bytes = generate_run_excel(detail)

    scenario = (detail.get("scenario") or "run").replace("_", "-")
    filename = f"careops-{scenario}-{run_id}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/data-health", response_model=DataHealthResponse)
def data_health(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DataHealthResponse:
    order_min, order_max = db.query(func.min(Order.ordered_at), func.max(Order.ordered_at)).one()
    reservation_min, reservation_max = db.query(
        func.min(Reservation.reserved_at),
        func.max(Reservation.reserved_at),
    ).one()
    feedback_min, feedback_max = db.query(
        func.min(Feedback.created_at),
        func.max(Feedback.created_at),
    ).one()

    feedback_count = db.query(func.count(Feedback.id)).scalar() or 0
    negative = db.query(func.count(Feedback.id)).filter(Feedback.sentiment == SentimentType.negative).scalar() or 0
    positive = db.query(func.count(Feedback.id)).filter(Feedback.sentiment == SentimentType.positive).scalar() or 0
    neutral = db.query(func.count(Feedback.id)).filter(Feedback.sentiment == SentimentType.neutral).scalar() or 0

    # Read org capacity from settings (falls back to 70 if not set)
    org = db.query(Organization).filter(Organization.id == current_user["org_id"]).first()
    capacity = int((org.settings or {}).get("capacity", 70)) if org else 70

    inventory_items = db.query(Inventory).all()
    inventory_alerts = InventoryService(db=db, llm=None).compute_alerts(inventory_items)

    return DataHealthResponse(
        orders=DataRange(
            count=db.query(func.count(Order.id)).scalar() or 0,
            date_range=[_date(order_min), _date(order_max)],
        ),
        reservations=DataRange(
            count=db.query(func.count(Reservation.id)).scalar() or 0,
            date_range=[_date(reservation_min), _date(reservation_max)],
        ),
        feedback=FeedbackHealth(
            count=feedback_count,
            date_range=[_date(feedback_min), _date(feedback_max)],
            negative=negative,
            positive=positive,
            neutral=neutral,
            negative_pct=round((negative / feedback_count) * 100, 1) if feedback_count else 0,
        ),
        inventory=InventoryHealth(
            items=len(inventory_items),
            shortage_alerts=len(inventory_alerts["shortage_alerts"]),
            critical_shortages=sum(
                1
                for alert in inventory_alerts["shortage_alerts"]
                if alert.get("severity") == "critical"
            ),
            overstock_alerts=len(inventory_alerts["overstock_alerts"]),
        ),
        menu={"items": db.query(func.count(MenuItem.id)).scalar() or 0},
        scenario_coverage=_scenario_coverage(db, capacity=capacity),
    )


def _scenario_coverage(db: Session, capacity: int = 70) -> list[ScenarioCoverage]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    coverage = []
    for scenario in list_scenarios():
        target = _next_matching_service_date(today, scenario["default_weekday"])
        start = target.replace(hour=0, minute=0, second=0)
        end = target.replace(hour=23, minute=59, second=59)
        rows = db.query(Reservation).filter(
            Reservation.reserved_at >= start,
            Reservation.reserved_at <= end,
            Reservation.status.in_([
                ReservationStatus.confirmed,
                ReservationStatus.waitlist,
            ]),
        ).all()
        guests = sum(row.guest_count for row in rows)
        coverage.append(
            ScenarioCoverage(
                scenario=scenario["id"],
                label=scenario["label"],
                date=start.strftime("%Y-%m-%d"),
                reservations=len(rows),
                guests=guests,
                waitlist=sum(1 for row in rows if row.status == ReservationStatus.waitlist),
                occupancy_pct=round((guests / capacity) * 100, 1),
            )
        )
    return coverage


def _next_matching_service_date(today: datetime, weekday: int) -> datetime:
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _date(value) -> str | None:
    return value.date().isoformat() if value else None


@router.get("/observability/summary", summary="Observability metrics summary")
def observability_summary(
    days: int = Query(default=7, ge=1, le=90, description="Lookback window in days"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Returns key planning run metrics for the last N days — powers the frontend observability panel."""
    since = datetime.utcnow() - timedelta(days=days)
    runs: list[PlanningRun] = (
        db.query(PlanningRun)
        .filter(PlanningRun.org_id == current_user["org_id"], PlanningRun.created_at >= since)
        .order_by(PlanningRun.created_at.desc())
        .all()
    )

    total = len(runs)
    by_verdict: dict[str, int] = {}
    by_scenario: dict[str, int] = {}
    durations: list[float] = []
    scores: list[float] = []

    for r in runs:
        v = r.critic_verdict or "unknown"
        by_verdict[v] = by_verdict.get(v, 0) + 1

        s = r.scenario or "unknown"
        by_scenario[s] = by_scenario.get(s, 0) + 1

        if r.critic_score is not None:
            scores.append(float(r.critic_score))

        meta = r.metadata_ or {}
        if "total_duration_ms" in meta:
            try:
                durations.append(float(meta["total_duration_ms"]))
            except (TypeError, ValueError):
                pass

    approved     = by_verdict.get("approved", 0)
    success_rate = round(approved / total, 3) if total > 0 else None
    avg_score    = round(sum(scores) / len(scores), 3) if scores else None
    avg_duration = round(sum(durations) / len(durations)) if durations else None
    top_scenario = max(by_scenario, key=by_scenario.get) if by_scenario else None

    latest_run = runs[0].created_at.isoformat() if runs else None

    return {
        "period_days":    days,
        "total_runs":     total,
        "by_verdict":     by_verdict,
        "by_scenario":    by_scenario,
        "success_rate":   success_rate,
        "avg_critic_score": avg_score,
        "avg_duration_ms":  avg_duration,
        "top_scenario":   top_scenario,
        "latest_run_at":  latest_run,
    }

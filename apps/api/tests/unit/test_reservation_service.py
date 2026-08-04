"""Unit tests for ReservationService. No test file previously existed for this
service -- added while wiring real peak-hours (from actual order history) into
its prompt, since 'busiest_hour' alone only reflects tonight's advance-booking
clustering, not the broader historical demand pattern."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_reservation_prompt_includes_real_peak_hours():
    from app.domain.services.reservation_service import ReservationService

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value={})

    with patch("app.domain.services.reservation_service.BusinessAnalyticsService") as MockAnalytics:
        MockAnalytics.return_value.get_peak_hours.return_value = [
            {"hour": h, "avg_orders": 8.0 if h == 20 else (3.0 if h == 13 else 0.0)}
            for h in range(24)
        ]
        service = ReservationService(db=db, llm=llm)
        service.get_service_reservations = MagicMock(return_value={
            "date": "2026-07-11", "scenario_label": "Friday Rush", "service_window": "18:00-22:00",
            "total_reservations": 18, "total_guests": 69, "capacity": 70, "occupancy_pct": 98.6,
            "overbooking_risk": False, "busiest_hour": 19, "peak_hours": {19: 40}, "waitlist_count": 3,
        })

        await service.analyse_and_recommend(target_date=datetime(2026, 7, 11))

    prompt = llm.complete_json.await_args.kwargs["prompt"]
    assert "20:00 (avg 8.0 orders)" in prompt
    assert "13:00 (avg 3.0 orders)" in prompt


@pytest.mark.asyncio
async def test_reservation_prompt_handles_no_order_history_gracefully():
    from app.domain.services.reservation_service import ReservationService

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value={})

    with patch("app.domain.services.reservation_service.BusinessAnalyticsService") as MockAnalytics:
        MockAnalytics.return_value.get_peak_hours.return_value = [
            {"hour": h, "avg_orders": 0.0} for h in range(24)
        ]
        service = ReservationService(db=db, llm=llm)
        service.get_service_reservations = MagicMock(return_value={
            "date": "2026-07-11", "scenario_label": "Friday Rush", "service_window": "18:00-22:00",
            "total_reservations": 0, "total_guests": 0, "capacity": 70, "occupancy_pct": 0.0,
            "overbooking_risk": False, "busiest_hour": None, "peak_hours": {}, "waitlist_count": 0,
        })

        # Should not raise
        await service.analyse_and_recommend(target_date=datetime(2026, 7, 11))

    prompt = llm.complete_json.await_args.kwargs["prompt"]
    assert "not enough order history yet" in prompt

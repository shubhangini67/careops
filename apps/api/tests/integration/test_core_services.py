import pytest
import asyncio
import sys
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.llm.gemini import GeminiProvider
from app.domain.services.reservation_service import ReservationService
from app.domain.services.forecast_service import ForecastService
from app.domain.services.complaint_service import ComplaintService
from app.domain.services.critic_service import CriticService

# ── Setup ──────────────────────────────────────────────
DATABASE_URL = "postgresql://careops:careopspass@localhost:5432/careops"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def llm():
    return GeminiProvider()


# ── Reservation Service ────────────────────────────────

@pytest.mark.asyncio
async def test_reservation_data(db):
    """Test reservation data retrieval — no LLM call."""
    service = ReservationService(db, llm=None)

    # Use a past Friday from our seed data
    target_friday = datetime.now() - timedelta(weeks=1)
    while target_friday.weekday() != 4:
        target_friday -= timedelta(days=1)

    data = service.get_friday_reservations(target_friday)
    print(f"\nReservation data: {data}")

    assert "total_reservations" in data
    assert "total_guests" in data
    assert "occupancy_pct" in data
    assert data["capacity"] == 70


@pytest.mark.asyncio
async def test_reservation_recommend(db, llm):
    """Test reservation analysis with Gemini recommendation."""
    service = ReservationService(db, llm=llm)

    target_friday = datetime.now() - timedelta(weeks=1)
    while target_friday.weekday() != 4:
        target_friday -= timedelta(days=1)

    result = await service.analyse_and_recommend(target_friday)
    print(f"\nReservation recommendation: {result['recommendation']}")

    assert result["service"] == "reservation"
    assert "recommendation" in result
    assert "data" in result


# ── Forecast Service ───────────────────────────────────

@pytest.mark.asyncio
async def test_forecast_data(db):
    """Test forecast calculation — no LLM call."""
    service = ForecastService(db, llm=None)
    forecast = service.calculate_forecast()
    print(f"\nForecast: {forecast}")

    assert "avg_friday_orders" in forecast
    assert "predicted_orders" in forecast
    assert "top_items" in forecast
    assert len(forecast["history"]) > 0


@pytest.mark.asyncio
async def test_forecast_recommend(db, llm):
    """Test forecast analysis with Gemini recommendation."""
    service = ForecastService(db, llm=llm)
    result = await service.analyse_and_recommend()
    print(f"\nForecast recommendation: {result['recommendation']}")

    assert result["service"] == "forecast"
    assert "recommendation" in result


# ── Complaint Service ──────────────────────────────────

@pytest.mark.asyncio
async def test_complaint_data(db):
    """Test complaint data retrieval — no LLM call."""
    service = ComplaintService(db, llm=None)
    summary = service.get_complaint_summary()
    print(f"\nComplaint summary: {summary}")

    assert "total_feedback" in summary
    assert "sentiment_breakdown" in summary
    assert "unique_complaints" in summary


@pytest.mark.asyncio
async def test_complaint_recommend(db, llm):
    """Test complaint analysis with Gemini recommendation."""
    service = ComplaintService(db, llm=llm)
    result = await service.analyse_and_recommend()
    print(f"\nComplaint recommendation: {result['recommendation']}")

    assert result["service"] == "complaint"
    assert "recommendation" in result


# ── Critic Service ─────────────────────────────────────

@pytest.mark.asyncio
async def test_critic_evaluate(db, llm):
    """Test critic evaluation of a recommendation."""
    service = CriticService(db, llm=llm)

    sample_recommendation = {
        "recommendation": "Add 2 kitchen staff for Friday 6-10pm shift and pre-prepare top 3 pizza bases by 5pm.",
        "priority": "high",
        "reasoning": "Forecast predicts 55 orders during peak hours, current staffing handles 40.",
        "risks": ["Additional labour cost", "Requires advance scheduling"]
    }

    result = await service.evaluate(
        agent="demand_forecast_agent",
        recommendation=sample_recommendation,
        input_summary="Forecast predicts 55 orders on Friday peak hours."
    )
    print(f"\nCritic verdict: {result}")

    assert "verdict" in result
    assert result["verdict"] in ["approved", "rejected", "revision"]
    assert "score" in result
    assert 0.0 <= result["score"] <= 1.0


@pytest.mark.asyncio
async def test_critic_evaluate_and_log(db, llm):
    """Test critic evaluation with decision log persistence."""
    service = CriticService(db, llm=llm)

    sample_recommendation = {
        "recommendation": "Close online reservations for Friday 7-9pm. Enable waitlist only.",
        "priority": "high",
        "reasoning": "Current bookings at 97% capacity.",
        "risks": ["May reduce walk-in revenue"]
    }

    result = await service.evaluate_and_log(
        agent="reservation_agent",
        recommendation=sample_recommendation,
        input_summary="Friday 7pm slot at 97% capacity.",
        reasoning_summary="Overbooking risk detected."
    )
    print(f"\nCritic log result: {result}")

    assert "decision_log_id" in result
    assert result["decision_log_id"] is not None
import os
import sys
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.domain.services.reservation_service import ReservationService
from app.domain.services.forecast_service import ForecastService
from app.domain.services.complaint_service import ComplaintService
from app.domain.services.critic_service import CriticService
from app.orchestration.service import OrchestrationService


DATABASE_URL = "postgresql://careops:careopspass@localhost:5432/careops"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class FakeLLMProvider:
    async def complete_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        if system_prompt and "critic" in system_prompt.lower():
            return {
                "verdict": "approved",
                "score": 0.91,
                "notes": "Looks operationally safe."
            }

        return {
            "summary": "Stub recommendation generated for test.",
            "actions": [
                "Add 2 extra staff during peak hours",
                "Pre-prep top menu items",
                "Monitor complaint-prone areas"
            ],
            "priority": "high"
        }


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def fake_llm():
    return FakeLLMProvider()


@pytest.mark.asyncio
async def test_langgraph_friday_rush_flow(db, fake_llm):
    reservation_service = ReservationService(db=db, llm=fake_llm)
    forecast_service = ForecastService(db=db, llm=fake_llm)
    complaint_service = ComplaintService(db=db, llm=fake_llm)
    critic_service = CriticService(db=db, llm=fake_llm)

    orchestration_service = OrchestrationService(
        reservation_service=reservation_service,
        forecast_service=forecast_service,
        complaint_service=complaint_service,
        critic_service=critic_service,
    )

    target_friday = datetime.now() - timedelta(weeks=1)
    while target_friday.weekday() != 4:
        target_friday -= timedelta(days=1)

    result = await orchestration_service.run_friday_rush_planning(target_friday)

    print("\nFinal orchestration output:", result)

    assert result["scenario"] == "friday_rush_planning"
    assert result["status"] in ["success", "failed"]

    assert "reservation" in result
    assert "forecast" in result
    assert "complaints" in result
    assert "critic" in result

    assert result["reservation"]["service"] == "reservation"
    assert result["forecast"]["service"] == "forecast"
    assert result["complaints"]["service"] == "complaint"

    assert "verdict" in result["critic"]
    assert result["critic"]["verdict"] in ["approved", "rejected", "revision"]
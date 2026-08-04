from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_complaint_service_adds_scenario_watchouts_to_summary():
    from app.domain.services.complaint_service import ComplaintService

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value={"issues": [], "overall_summary": "", "action_items": []})

    service = ComplaintService(db=db, llm=llm)
    service.get_complaint_summary = MagicMock(
        return_value={
            "period_days": 28,
            "total_feedback": 12,
            "sentiment_breakdown": {
                "negative": 4,
                "positive": 6,
                "neutral": 2,
                "negative_pct": 33.3,
            },
            "unique_complaints": ["Slow takeaway handoff"],
            "unique_positives": ["Friendly staff"],
        }
    )

    result = await service.analyse_and_recommend(
        scenario_profile={
            "id": "weekday_lunch",
            "label": "Weekday Lunch",
            "service_window": "12:00-15:00",
            "operational_focus": "Lunch pacing and staffing efficiency.",
        }
    )

    assert result["data"]["scenario_label"] == "Weekday Lunch"
    assert result["data"]["service_window"] == "12:00-15:00"
    assert any("Takeaway packaging" in item for item in result["data"]["scenario_watchouts"])


@pytest.mark.asyncio
async def test_complaint_summary_includes_category_breakdown():
    """The LLM previously had to infer complaint themes purely from raw text every
    time -- this confirms the quantified category counts now reach get_complaint_summary."""
    from app.domain.services.complaint_service import ComplaintService

    db = MagicMock()
    llm = MagicMock()

    with patch("app.domain.services.complaint_service.BusinessAnalyticsService") as MockAnalytics:
        MockAnalytics.return_value.get_complaints_by_category.return_value = [
            {"category": "Wait Time", "count": 10}, {"category": "Ambience", "count": 2},
        ]
        service = ComplaintService(db=db, llm=llm)
        service.get_recent_feedback = MagicMock(return_value={
            "total_feedback": 12, "negative_count": 4, "positive_count": 6, "neutral_count": 2,
            "negative_pct": 33.3, "negative_texts": ["Waited forever"], "positive_texts": ["Great!"],
        })
        summary = service.get_complaint_summary(days=28)

    assert summary["category_breakdown"] == [
        {"category": "Wait Time", "count": 10}, {"category": "Ambience", "count": 2},
    ]


@pytest.mark.asyncio
async def test_complaint_prompt_includes_category_breakdown():
    from app.domain.services.complaint_service import ComplaintService

    db = MagicMock()
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value={"issues": [], "overall_summary": "", "action_items": []})

    service = ComplaintService(db=db, llm=llm)
    service.get_complaint_summary = MagicMock(
        return_value={
            "period_days": 28,
            "total_feedback": 12,
            "sentiment_breakdown": {"negative": 4, "positive": 6, "neutral": 2, "negative_pct": 33.3},
            "unique_complaints": ["Slow takeaway handoff"],
            "unique_positives": ["Friendly staff"],
            "category_breakdown": [{"category": "Wait Time", "count": 10}],
        }
    )

    await service.analyse_and_recommend()

    prompt = llm.complete_json.await_args.kwargs["prompt"]
    assert "Wait Time: 10" in prompt

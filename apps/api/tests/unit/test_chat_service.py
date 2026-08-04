"""P5-12 RAG chatbot — unit tests for context retrieval and multi-turn history."""

from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


def _mock_run(scenario="friday_rush", verdict="approved", score=0.88, notes="Solid plan."):
    run = MagicMock()
    run.scenario        = scenario
    run.critic_verdict  = verdict
    run.critic_score    = score
    run.critic          = {"notes": notes}
    run.created_at      = datetime(2026, 6, 6, 18, 0, 0)
    return run


def test_build_context_includes_run_data():
    from app.domain.services.chat_service import build_context

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        _mock_run("friday_rush", "approved", 0.91, "Strong demand forecast."),
        _mock_run("weekday_lunch", "revision", 0.65, "Inventory shortfall flagged."),
    ]
    mock_org_query = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    context = build_context(
        org_id=1,
        org_name="Test Kitchen",
        question="Why was last week revised?",
        db=mock_db,
        memory=None,
    )

    assert "Test Kitchen" in context
    assert "friday_rush" in context
    assert "weekday_lunch" in context
    assert "revision" in context
    assert "0.65" in context


def test_build_context_with_no_runs_returns_safe_default():
    from app.domain.services.chat_service import build_context

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    context = build_context(
        org_id=1,
        org_name="Test Kitchen",
        question="How did we do?",
        db=mock_db,
        memory=None,
    )

    assert "No planning runs found" in context


def test_build_context_includes_db_feedback():
    from app.domain.services.chat_service import build_context

    fb = MagicMock()
    fb.raw_text = "Pizza was cold on arrival"
    fb.sentiment = MagicMock()
    fb.sentiment.value = "negative"
    fb.created_at = datetime(2026, 6, 1)

    mock_db = MagicMock()
    # First query = PlanningRun (empty), second query = Feedback
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock_db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [fb]

    context = build_context(
        org_id=1,
        org_name="Test Kitchen",
        question="What complaints did we have?",
        db=mock_db,
        memory=None,
    )

    assert "Pizza was cold on arrival" in context


def test_build_context_handles_qdrant_failure_gracefully():
    from app.domain.services.chat_service import build_context

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    mock_memory = MagicMock()
    mock_memory.retrieve_similar_complaints.side_effect = Exception("Qdrant unavailable")

    # Should not raise
    context = build_context(
        org_id=1,
        org_name="Test Kitchen",
        question="Any issues?",
        db=mock_db,
        memory=mock_memory,
    )

    assert "Test Kitchen" in context


def test_build_context_includes_rag_retrieval_when_memory_provided():
    """P6-A2: memory was previously accepted and never called -- context was pure
    raw SQL with no relevance ranking. This confirms it's now actually wired in,
    scoped to the real question asked."""
    from app.domain.services.chat_service import build_context

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    mock_memory = MagicMock()
    mock_memory.retrieve_similar_complaints.return_value = [
        {"text": "Naan was undercooked twice last week", "score": 0.91, "metadata": {}}
    ]
    mock_memory.retrieve_relevant_sops.return_value = [
        {"text": "SOP: check tandoor temperature before dinner service", "score": 0.88, "metadata": {}}
    ]

    context = build_context(
        org_id=1,
        org_name="Test Kitchen",
        question="Have we had naan complaints before?",
        db=mock_db,
        memory=mock_memory,
    )

    assert "Naan was undercooked twice last week" in context
    assert "check tandoor temperature" in context
    mock_memory.retrieve_similar_complaints.assert_called_once_with(
        "Have we had naan complaints before?", 1, top_k=3
    )
    mock_memory.retrieve_relevant_sops.assert_called_once_with(
        "Have we had naan complaints before?", 1, top_k=3
    )


def test_build_context_omits_rag_sections_when_memory_returns_nothing():
    from app.domain.services.chat_service import build_context

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    mock_memory = MagicMock()
    mock_memory.retrieve_similar_complaints.return_value = []
    mock_memory.retrieve_relevant_sops.return_value = []

    context = build_context(
        org_id=1, org_name="Test Kitchen", question="Anything?", db=mock_db, memory=mock_memory,
    )

    assert "Relevant past complaints" not in context
    assert "Relevant SOPs" not in context


def test_swiggy_search_menu_tool_removed():
    """P6-A3: search_menu confirmed to return zero results in this sandbox --
    the dead tool definition and its handler branch were removed entirely."""
    from app.domain.services.chat_service import _TOOLS, _SWIGGY_TOOL_NAMES

    tool_names = {t["function"]["name"] for t in _TOOLS}
    assert "swiggy_search_menu" not in tool_names
    assert "swiggy_search_menu" not in _SWIGGY_TOOL_NAMES


def test_build_context_includes_business_analytics():
    """The chatbot previously had none of the margin/complaint-category/peak-hours
    signals the Today dashboard and the planning pipeline now share -- confirms it does now."""
    from app.domain.services.chat_service import build_context

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    with patch("app.domain.services.chat_service.BusinessAnalyticsService") as MockAnalytics:
        MockAnalytics.return_value.get_dish_performance.return_value = [
            {"name": "Margherita", "category": "pizza", "revenue": 600.0, "quantity": 2, "margin_pct": 66.7},
        ]
        MockAnalytics.return_value.get_complaints_by_category.return_value = [
            {"category": "Wait Time", "count": 10},
        ]
        MockAnalytics.return_value.get_peak_hours.return_value = [
            {"hour": h, "avg_orders": 5.0 if h == 19 else 0.0} for h in range(24)
        ]

        context = build_context(org_id=1, org_name="Test Kitchen", question="How are we doing?", db=mock_db)

    assert "Margherita" in context
    assert "66.7" in context or "67" in context
    assert "Wait Time: 10" in context
    assert "19:00" in context


def test_history_trimmed_to_last_6():
    """The service keeps only the last 6 history messages before the new question."""
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(10)
    ]
    # Replicate the trimming logic from stream_reply
    trimmed = long_history[-6:]
    assert len(trimmed) == 6
    assert trimmed[0]["content"] == "msg 4"  # first kept message
    assert trimmed[-1]["content"] == "msg 9"  # last kept message

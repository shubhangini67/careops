"""Unit tests for the observability summary endpoint (P5-08)."""

from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


def _mock_run(scenario="friday_rush", verdict="approved", score=0.88, duration_ms=3200):
    run = MagicMock()
    run.scenario = scenario
    run.critic_verdict = verdict
    run.critic_score = score
    run.created_at = datetime.utcnow() - timedelta(hours=2)
    run.metadata_ = {"total_duration_ms": duration_ms}
    return run


def test_summary_totals():
    from app.api.routes.runs import observability_summary

    runs = [
        _mock_run("friday_rush",   "approved", 0.91, 3100),
        _mock_run("weekday_lunch", "approved", 0.85, 2800),
        _mock_run("friday_rush",   "revision", 0.65, 4200),
    ]

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = runs
    mock_user = {"org_id": 1}

    result = observability_summary(days=7, db=mock_db, current_user=mock_user)

    assert result["total_runs"] == 3
    assert result["by_verdict"]["approved"] == 2
    assert result["by_verdict"]["revision"] == 1
    assert result["by_scenario"]["friday_rush"] == 2
    assert result["by_scenario"]["weekday_lunch"] == 1


def test_success_rate_calculation():
    from app.api.routes.runs import observability_summary

    runs = [_mock_run(verdict="approved")] * 3 + [_mock_run(verdict="revision")] * 1
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = runs
    mock_user = {"org_id": 1}

    result = observability_summary(days=7, db=mock_db, current_user=mock_user)

    assert result["success_rate"] == 0.75


def test_avg_duration_and_score():
    from app.api.routes.runs import observability_summary

    runs = [
        _mock_run(score=0.9,  duration_ms=3000),
        _mock_run(score=0.8,  duration_ms=5000),
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = runs
    mock_user = {"org_id": 1}

    result = observability_summary(days=7, db=mock_db, current_user=mock_user)

    assert result["avg_duration_ms"] == 4000
    assert result["avg_critic_score"] == 0.85


def test_empty_runs_returns_safe_defaults():
    from app.api.routes.runs import observability_summary

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock_user = {"org_id": 1}

    result = observability_summary(days=7, db=mock_db, current_user=mock_user)

    assert result["total_runs"] == 0
    assert result["success_rate"] is None
    assert result["avg_critic_score"] is None
    assert result["avg_duration_ms"] is None
    assert result["top_scenario"] is None


def test_top_scenario_is_most_frequent():
    from app.api.routes.runs import observability_summary

    runs = (
        [_mock_run("friday_rush")] * 5 +
        [_mock_run("weekday_lunch")] * 2
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = runs
    mock_user = {"org_id": 1}

    result = observability_summary(days=7, db=mock_db, current_user=mock_user)

    assert result["top_scenario"] == "friday_rush"

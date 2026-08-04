from datetime import datetime
from unittest.mock import MagicMock


def test_run_service_create_from_response_persists_core_fields():
    from app.domain.services.run_service import RunService

    db = MagicMock()
    response = {
        "scenario": "friday_rush",
        "target_date": "2026-05-08",
        "status": "ready",
        "generated_at": "2026-04-27T10:00:00",
        "recommendations": {"forecast": {"data": {}}},
        "rag_context": {"similar": []},
        "critic": {
            "verdict": "approved",
            "score": 0.86,
            "decision_log_id": 147,
        },
        "meta": {"debug": False},
    }

    RunService(db).create_from_response(response)

    run = db.add.call_args.args[0]
    assert run.scenario == "friday_rush"
    assert run.target_date == "2026-05-08"
    assert run.status == "ready"
    assert run.critic_verdict == "approved"
    assert run.critic_score == 0.86
    assert run.decision_log_id == 147
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(run)


def test_run_service_serializes_summary_and_detail():
    from app.domain.services.run_service import RunService

    run = MagicMock()
    run.id = 12
    run.scenario = "friday_rush"
    run.target_date = "2026-05-08"
    run.status = "needs_review"
    run.critic_verdict = "revision"
    run.critic_score = 0.7
    run.decision_log_id = 9
    run.generated_at = datetime(2026, 4, 27, 10, 0, 0)
    run.created_at = datetime(2026, 4, 27, 10, 1, 0)
    run.final_response = {"scenario": "friday_rush"}
    run.recommendations = {"inventory": {}}
    run.rag_context = {"sops": []}
    run.critic = {"verdict": "revision"}
    run.metadata_ = {"simulation_mode": False}

    service = RunService(MagicMock())
    summary = service.to_summary(run)
    detail = service.to_detail(run)

    assert summary["id"] == 12
    assert summary["generated_at"] == "2026-04-27T10:00:00"
    assert detail["final_response"]["scenario"] == "friday_rush"
    assert detail["metadata"]["simulation_mode"] is False

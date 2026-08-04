"""P5-11 tenant isolation tests — Postgres org_id scoping + Qdrant payload filters."""

from unittest.mock import MagicMock, patch


# ── Postgres isolation ────────────────────────────────────────────────────────

def _make_run(id: int, org_id: int, verdict: str = "approved", score: float = 0.88):
    run = MagicMock()
    run.id           = id
    run.org_id       = org_id
    run.scenario     = "friday_rush"
    run.target_date  = "2026-06-07"
    run.status       = "completed"
    run.critic_verdict = verdict
    run.critic_score = score
    run.decision_log_id = None
    run.generated_at = None
    run.created_at   = None
    return run


def test_list_runs_filters_by_org_id():
    from app.domain.services.run_service import RunService

    org_a_runs = [_make_run(1, org_id=1), _make_run(2, org_id=1)]
    mock_db = MagicMock()
    (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = org_a_runs

    service = RunService(mock_db)
    results = service.list_runs(org_id=1)

    # The first filter call must include the org_id condition
    filter_args = mock_db.query.return_value.filter.call_args[0]
    assert any("org_id" in str(a) for a in filter_args), "list_runs must filter by org_id"
    assert len(results) == 2


def test_get_run_scoped_to_org():
    from app.domain.services.run_service import RunService

    org_a_run = _make_run(42, org_id=1)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = org_a_run

    service = RunService(mock_db)
    result = service.get_run(run_id=42, org_id=1)

    filter_args = mock_db.query.return_value.filter.call_args[0]
    assert any("org_id" in str(a) for a in filter_args), "get_run must filter by org_id"
    assert result is org_a_run


def test_get_run_returns_none_for_wrong_org():
    from app.domain.services.run_service import RunService

    mock_db = MagicMock()
    # Simulate DB returning nothing when org_id doesn't match
    mock_db.query.return_value.filter.return_value.first.return_value = None

    service = RunService(mock_db)
    result = service.get_run(run_id=42, org_id=2)

    assert result is None, "get_run must return None when org doesn't own the run"


# ── Qdrant isolation ──────────────────────────────────────────────────────────

def _make_memory_service():
    from app.infrastructure.vector.memory_service import MemoryService
    mock_qdrant  = MagicMock()
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [0.1] * 128
    mock_qdrant.query_points.return_value.points = []
    with patch("app.infrastructure.vector.memory_service.ensure_collection"):
        svc = MemoryService(qdrant=mock_qdrant, embedder=mock_embedder)
    return svc, mock_qdrant


def test_store_complaint_includes_org_id_in_payload():
    svc, mock_qdrant = _make_memory_service()
    svc.store_complaint(text="Pizza was cold", org_id=7)

    upsert_call = mock_qdrant.upsert.call_args
    point = upsert_call.kwargs["points"][0]
    assert point.payload["org_id"] == 7
    assert point.payload["text"] == "Pizza was cold"


def test_store_sop_includes_org_id_in_payload():
    svc, mock_qdrant = _make_memory_service()
    svc.store_sop(text="Always check temp before serving", org_id=3)

    upsert_call = mock_qdrant.upsert.call_args
    point = upsert_call.kwargs["points"][0]
    assert point.payload["org_id"] == 3


def test_retrieve_complaints_passes_org_filter():
    from qdrant_client.models import Filter
    svc, mock_qdrant = _make_memory_service()
    svc.retrieve_similar_complaints(query="cold food", org_id=5)

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    assert "query_filter" in call_kwargs
    assert isinstance(call_kwargs["query_filter"], Filter)
    condition = call_kwargs["query_filter"].must[0]
    assert condition.key == "org_id"
    assert condition.match.value == 5


def test_retrieve_sops_passes_org_filter():
    from qdrant_client.models import Filter
    svc, mock_qdrant = _make_memory_service()
    svc.retrieve_relevant_sops(query="food safety", org_id=9)

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    assert "query_filter" in call_kwargs
    assert isinstance(call_kwargs["query_filter"], Filter)
    condition = call_kwargs["query_filter"].must[0]
    assert condition.key == "org_id"
    assert condition.match.value == 9

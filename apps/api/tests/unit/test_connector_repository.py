"""Unit tests for ConnectorRepository.

Uses an in-memory SQLite DB so no PostgreSQL needed. Verifies upsert
idempotency, get, status updates, and error_count increment.
"""

import pytest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.models import Connector
from app.infrastructure.swiggy.connector_repository import ConnectorRepository

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session with only the connectors table -- skips FK
    enforcement so org_id=1 is accepted without a parent row. (Every JSONB
    column in this schema was converted to plain JSON in P6-A18, so this no
    longer needs to dodge a Postgres-only column type; kept as a single-table
    fixture anyway since this test only needs Connector.)"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Connector.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def repo(db_session):
    return ConnectorRepository(db_session)


@pytest.fixture
def org_id():
    return 1  # no real org row needed — SQLite skips FK enforcement by default


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_upsert_creates_new_connector(repo, org_id):
    connector = repo.upsert(org_id, "swiggy", sync_status="never_synced")
    assert connector.id is not None
    assert connector.org_id == org_id
    assert connector.connector_type == "swiggy"
    assert connector.sync_status == "never_synced"


def test_upsert_updates_existing_connector(repo, org_id):
    repo.upsert(org_id, "swiggy", sync_status="never_synced")
    updated = repo.upsert(org_id, "swiggy", sync_status="success", error_count=0)
    assert updated.sync_status == "success"

    # Only one row should exist
    from sqlalchemy.orm import Session
    count = repo.db.query(Connector).filter_by(org_id=org_id, connector_type="swiggy").count()
    assert count == 1


def test_get_returns_none_when_not_found(repo, org_id):
    result = repo.get(org_id, "nonexistent_platform")
    assert result is None


def test_update_sync_status_sets_error_count(repo, org_id):
    repo.upsert(org_id, "swiggy")

    repo.update_sync_status(org_id, "swiggy", "error", error="timeout after 30s")
    connector = repo.get(org_id, "swiggy")

    assert connector.sync_status == "error"
    assert connector.error_count == 1
    assert connector.last_error == "timeout after 30s"

    # Second error should increment
    repo.update_sync_status(org_id, "swiggy", "error", error="401 token expired")
    connector = repo.get(org_id, "swiggy")
    assert connector.error_count == 2


def test_update_sync_status_clears_error_on_success(repo, org_id):
    repo.upsert(org_id, "swiggy")
    repo.update_sync_status(org_id, "swiggy", "error", error="bad gateway")
    repo.update_sync_status(org_id, "swiggy", "success")

    connector = repo.get(org_id, "swiggy")
    assert connector.sync_status == "success"
    assert connector.last_error is None
    assert connector.last_sync_at is not None


def test_list_active_filters_by_type(repo, org_id):
    repo.upsert(org_id, "swiggy", access_token_encrypted="tok_swiggy")
    repo.upsert(org_id, "pos_square")  # no token

    active = repo.list_active(connector_type="swiggy")
    assert len(active) == 1
    assert active[0].connector_type == "swiggy"

    all_active = repo.list_active()
    assert len(all_active) == 1  # pos_square has no token

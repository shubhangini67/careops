"""Async planning run job queue backed by Redis.

Simple Redis-hash-based job queue — no external job library. Matches the
existing plan_cache.py Redis pattern (redis.asyncio, same connection).

Job lifecycle:
  enqueue_planning_run() → status=queued
  (worker picks up job)  → status=running
  (worker completes)     → status=completed / failed

Jobs expire after 24h (TTL). The queue itself is a Redis list; each entry
is a job_id. The job hash stores all metadata.

Key schema:
  job:{job_id}          — Redis hash (status, result, error, created_at, ...)
  planning_run_queue    — Redis list of pending job_ids
"""

import json
import uuid
import structlog
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.core.settings import get_settings

log = structlog.get_logger()

JOB_TTL = 86_400       # 24 hours
QUEUE_KEY = "planning_run_queue"

_client: Optional[aioredis.Redis] = None


async def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def enqueue_planning_run(
    scenario: str,
    org_id: int,
    target_date: Optional[str] = None,
) -> str:
    """Enqueue a planning run job. Returns the job_id."""
    job_id = str(uuid.uuid4())
    job_key = f"job:{job_id}"

    job_data = {
        "job_id": job_id,
        "status": "queued",
        "scenario": scenario,
        "org_id": str(org_id),
        "target_date": target_date or "",
        "result": "",
        "error": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        client = await _get_client()
        await client.hset(job_key, mapping=job_data)
        await client.expire(job_key, JOB_TTL)
        await client.rpush(QUEUE_KEY, job_id)
        log.info("job_enqueued", job_id=job_id, scenario=scenario, org_id=org_id)
    except Exception as exc:
        log.error("job_enqueue_failed", error=str(exc), scenario=scenario, org_id=org_id)

    return job_id


async def get_job_status(job_id: str) -> dict:
    """Return the full job metadata dict for a given job_id.

    Returns a dict with status=not_found if the job doesn't exist or Redis fails.
    """
    job_key = f"job:{job_id}"
    try:
        client = await _get_client()
        data = await client.hgetall(job_key)
        if not data:
            return {"job_id": job_id, "status": "not_found"}
        result_raw = data.get("result", "")
        return {
            "job_id": job_id,
            "status": data.get("status", "unknown"),
            "scenario": data.get("scenario"),
            "org_id": int(data.get("org_id", 0)),
            "target_date": data.get("target_date") or None,
            "result": json.loads(result_raw) if result_raw else None,
            "error": data.get("error") or None,
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }
    except Exception as exc:
        log.error("job_status_failed", job_id=job_id, error=str(exc))
        return {"job_id": job_id, "status": "error", "error": str(exc)}


async def update_job_status(
    job_id: str,
    status: str,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Internal: update a job's status (called by the worker)."""
    job_key = f"job:{job_id}"
    updates = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if result is not None:
        updates["result"] = json.dumps(result, default=str)
    if error is not None:
        updates["error"] = error

    try:
        client = await _get_client()
        await client.hset(job_key, mapping=updates)
    except Exception as exc:
        log.error("job_update_failed", job_id=job_id, error=str(exc))

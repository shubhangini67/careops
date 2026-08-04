# CareOps AI Infrastructure

Local infrastructure for CareOps AI. All services run via Docker Compose.

## Services

| Service | Purpose | Port |
|---------|---------|------|
| PostgreSQL 16 | Primary relational data store: all structured data, planning runs, auth | 5432 |
| Qdrant | Vector memory for complaint RAG, SOP retrieval, planning memory, and semantic caches | 6333 (REST), 6334 (gRPC) |
| Redis 7 | Plan cache (1hr TTL by scenario + date) and circuit breaker state for Swiggy endpoints | 6379 |

## Start the stack

```bash
docker compose up -d
```

## Stop the stack

```bash
docker compose down
```

## Reset all data

```bash
docker compose down -v   # removes persistent volumes
docker compose up -d
# then re-run seed scripts
```

Persistent Docker volumes (`postgres_data`, `qdrant_data`, `redis_data`) are defined in `docker-compose.yml`. Data survives normal container restarts: only `down -v` wipes it.

## Notes

- This is a local development stack, not a production deployment
- Redis is used for plan caching (1hr TTL by `org_id + scenario + date`) and circuit breaker state (per-endpoint failure counters and open-circuit flags for Swiggy MCP)
- Qdrant uses shared collections with `org_id` payload filters for multi-tenant isolation
- PostgreSQL uses `org_id` column scoping on all run and settings queries

# Scripts

Project utility scripts for seeding, local setup, and eval dataset management.

## Scripts

| Script | Purpose |
|--------|---------|
| `seed_demo_data.py` | Seeds the full CareOps relational demo dataset: encounters (orders), appointments (reservations), patient feedback, clinical supplies, and service lines. Uses hospital scenario IDs (`ed_surge`, `opd_peak`, `icu_capacity`, `supply_shortage`). Dates and random seed are computed relative to script run-time |
| `seed_qdrant_memory.py` | Loads patient complaint patterns and hospital SOP-style memory into Qdrant (`complaints_memory` collection) |
| `test_qdrant_retrieval.py` | Quick retrieval sanity check: verifies Qdrant is seeded and returning results |
| `build_golden_dataset.py` | Builds the `careops-golden-v1` LangSmith regression eval dataset from approved planning runs |
| `build_ragas_dataset.py` | Extracts RAGAS eval candidate samples from real planning runs; output is not yet promoted into the golden fixtures |
| `build_deepeval_dataset.py` | Extracts DeepEval eval candidate samples from real planning runs; output is not yet promoted into the golden fixtures |
| `get_swiggy_token.py` | Refreshes the dev-only Swiggy OAuth access token (5-day TTL) |

## Typical usage

Run from the repository root after Docker services are up and the API virtual environment is activated.

```bash
cd apps/api
venv\Scripts\activate   # Windows
# or: source venv/bin/activate  (macOS/Linux)

python ..\..\scripts\seed_demo_data.py
python ..\..\scripts\seed_qdrant_memory.py
```

## Expected output after seeding

- Several months of historical encounters, anchored to the run date
- Appointments for the next roughly 2.5 months, matched to each scenario's weekday pattern
- Patient feedback spanning positive, negative, and neutral sentiment
- 18 clinical supply items, with 1 to 4 randomly selected to run low each seed day
- 27 hospital service lines (departments/procedures)
- Qdrant `complaints_memory` collection populated with complaint embeddings (after `seed_qdrant_memory.py`)

## Reset everything

```bash
docker compose down -v   # wipe all persistent volumes
docker compose up -d     # restart fresh
# then re-run seed scripts
```

# CareOps AI — Agentic Hospital Operations and Policy Copilot

CareOps AI helps hospital operations teams forecast department workload, monitor capacity and supplies, retrieve hospital SOPs with citations, and route sensitive actions through a human approval queue.

**Important:** This platform provides **operational planning only**. It does not provide diagnoses, treatment advice, or medication recommendations. All patient data is synthetic and de-identified.

## Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Python 3.11 |
| Agents | LangGraph (7-agent CareOps pipeline) |
| MCP | Local healthcare/FHIR MCP server |
| Frontend | Next.js, TypeScript |
| Data | PostgreSQL, Qdrant, Redis |
| LLM | Groq (default) + Gemini fallback |
| Evals | RAGAS, DeepEval, LangSmith |
| Observability | Langfuse (optional — app starts without credentials) |

## CareOps LangGraph agents

1. **Supervisor/router** — validates scenario, sets operational context
2. **Capacity Forecast** — 24–48h OPD/admission workload projection
3. **FHIR Operations** — synthetic encounter/appointment aggregates (no PHI)
4. **Policy RAG** — hospital SOP retrieval with citations
5. **Resource Allocation** — staffing and supply coordination
6. **Safety & Grounding Critic** — blocks clinical-advice language, scores plan
7. **Human Approval Queue** — creates review actions for low-confidence steps

## Local setup

### Prerequisites

- Docker Compose
- Python 3.11+
- Node.js 20.9+
- Groq API key ([console.groq.com](https://console.groq.com))
- Gemini API key (embeddings + fallback)

### 1. Infrastructure

```bash
docker compose up -d
```

### 2. Backend

```bash
cd apps/api
cp .env.example .env   # set GROQ_API_KEY, GEMINI_API_KEY
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python ../../scripts/seed_hospital_data.py
python ../../scripts/seed_hospital_policies.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend

```bash
cd apps/web/careops-ui
npm install
npm run dev
```

Open http://localhost:3000 — register a hospital/facility workspace, then use **Scenario Planner** to run an operations plan.

## MCP tools (healthcare)

Run `python healthcare_mcp_server.py` from `apps/api/`:

- `get_capacity_snapshot`
- `get_department_workload`
- `get_staffing_summary`
- `get_supply_shortages`
- `get_fhir_encounter_summary`
- `search_hospital_policy`
- `create_review_action`

## Synthetic data

- Relational seed: `scripts/seed_hospital_data.py` (4 departments, beds, staff, supplies, incidents)
- Policy vectors: `scripts/seed_hospital_policies.py` (10 hospital SOPs in Qdrant)
- FHIR fixtures: `data/fhir/` — see [data/fhir/README.md](data/fhir/README.md) for Synthea import notes

## Tests

```bash
cd apps/api
pytest tests/unit -q --ignore=tests/unit/test_swiggy_reservation_sync.py
pytest evals/test_ragas_complaint.py evals/test_deepeval_quality.py -v
cd ../web/careops-ui && npm run build
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 shubhangini67.

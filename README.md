# CareOps AI

**Agentic hospital operations copilot** — forecast department workload, monitor beds and supplies, retrieve hospital policies with citations, and route sensitive actions through a human approval queue.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](apps/api)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](apps/api)
[![LangGraph](https://img.shields.io/badge/LangGraph-agents-8B5CF6)](apps/api/app/orchestration/careops_graph.py)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](apps/web/careops-ui)

> **Scope:** Operational planning only — not diagnosis, treatment, or medication advice.  
> **Data:** Synthetic, de-identified hospital fixtures (no real PHI).

---

## What it does

| Capability | Description |
|------------|-------------|
| **Capacity forecasting** | 24–48h OPD/admission workload from appointments + bed occupancy |
| **Policy RAG** | Retrieves hospital SOPs from Qdrant with **`policy_id` citations** |
| **Resource allocation** | Staffing and clinical supply coordination across departments |
| **Safety critic** | Blocks clinical-advice language; scores plan grounding |
| **Human approval queue** | Low-confidence actions require operator sign-off |
| **Operations dashboard** | Health score, live signals, supply alerts, encounter analytics |

### Scenario presets

`ed_surge` · `opd_peak` · `icu_capacity` · `supply_shortage`

---

## Architecture

```
Next.js UI  →  FastAPI  →  LangGraph (7 agents)
                  ↓              ↓
            PostgreSQL       Qdrant (policies + complaints)
                  ↓              ↓
              Redis          Healthcare MCP (FHIR + local tools)
```

**Agent pipeline:** Supervisor → Capacity Forecast → parallel *(FHIR Ops · Policy RAG · Resource Allocation)* → Aggregator → Safety Critic → Human Approval Queue

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/INTERVIEW_GUIDE.md`](docs/INTERVIEW_GUIDE.md)

---

## Quick start

### Prerequisites

Docker Compose · Python 3.11+ · Node.js 20.9+ · [Groq](https://console.groq.com) + [Gemini](https://aistudio.google.com) API keys

### 1. Infrastructure

```bash
docker compose up -d
```

### 2. Backend

```bash
cd apps/api
cp .env.example .env          # set GROQ_API_KEY, GEMINI_API_KEY
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python ../../scripts/seed_demo_data.py
python ../../scripts/seed_hospital_data.py
python ../../scripts/seed_qdrant_memory.py
python ../../scripts/seed_hospital_policies.py
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd apps/web/careops-ui
npm install && npm run dev
```

Open **http://localhost:3000** → register a facility → **Scenario Planner** → run `ed_surge`.

---

## Demo walkthrough

1. **Dashboard** — operational health, capacity forecast, supply snapshot  
2. **Planning** — stream the 7-agent pipeline with per-node observability  
3. **Policy citations** — inspect retrieved SOP excerpts in the plan output  
4. **Action Center** — approve or reject pending supply / ops actions  

---

## Tech stack

| Layer | Tools |
|-------|--------|
| Backend | FastAPI, SQLAlchemy, Alembic |
| Agents | LangGraph, Groq / Gemini |
| RAG | Qdrant, Gemini embeddings |
| Frontend | Next.js 16, TypeScript, Tailwind CSS 4 |
| Data | PostgreSQL, Redis |
| Evals | RAGAS, DeepEval, LangSmith golden set |

---

## Healthcare MCP tools

Run from `apps/api/`: `python healthcare_mcp_server.py`

`get_capacity_snapshot` · `get_department_workload` · `get_staffing_summary` · `get_supply_shortages` · `get_fhir_encounter_summary` · `search_hospital_policy` · `create_review_action`

---

## Tests

```bash
cd apps/api
pytest tests/unit -q
pytest evals/test_ragas_complaint.py evals/test_deepeval_quality.py -v -W ignore::DeprecationWarning
cd ../web/careops-ui && npm run build
```

---

## Project layout

```
apps/api/          FastAPI + LangGraph + MCP server
apps/web/careops-ui/   Next.js operator dashboard
scripts/           Demo + hospital seed scripts
data/fhir/         Synthetic FHIR fixtures
docs/              Architecture, API, evaluation guides
```

---

## Deploy (when ready)

**Backend → [Render](https://render.com)** · **Frontend → [Vercel](https://vercel.com)**

Step-by-step: [`docs/DEPLOY.md`](docs/DEPLOY.md) (Postgres, Redis, Qdrant Cloud, env vars, one-time seeds).

---

## Author

**[shubhangini67](https://github.com/shubhangini67)**

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 shubhangini67.

# CareOps AI

**Agentic hospital operations copilot** — seven specialist agents forecast capacity, read FHIR operations data, retrieve hospital policies with citations, and route sensitive actions through a human approval queue.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](apps/api)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](apps/api)
[![LangGraph](https://img.shields.io/badge/LangGraph-agents-8B5CF6)](apps/api/app/orchestration/careops_graph.py)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](apps/web/careops-ui)

> Operational planning only — not diagnosis, treatment, or medication advice.  
> Demo data is synthetic and de-identified (no real PHI).

<p align="center">
  <img src="docs/screenshots/01-home.png" alt="CareOps AI landing page" width="100%">
</p>

---

## Product tour

All screens below are from a local run at `http://localhost:3000`.

### Operations dashboard

Health score, bed utilization, supply alerts, and live intelligence in one briefing.

<p align="center">
  <img src="docs/screenshots/04-dashboard.png" alt="Operations dashboard" width="100%">
</p>

### Scenario planner

Seven agents build a safety-reviewed plan: capacity forecast, FHIR ops, policy RAG, resource allocation, critic, then approval queue.

<p align="center">
  <img src="docs/screenshots/06-scenario-planner.png" alt="Scenario planner with a completed plan" width="100%">
</p>

### Policy Assistant (AI chat)

Ask about capacity, supplies, safety incidents, and past runs. Answers are grounded in hospital data and policies — not generic chat.

<p align="center">
  <img src="docs/screenshots/09-chat-empty.png" alt="Policy Assistant suggested questions" width="100%">
</p>

<p align="center">
  <img src="docs/screenshots/10-ai-chat.png" alt="Policy Assistant answering a supply question" width="100%">
</p>

### Approval queue

Low-confidence or high-impact actions wait for a human sign-off before anything executes.

<p align="center">
  <img src="docs/screenshots/08-approval-queue.png" alt="Approval queue with pending supply reorder" width="100%">
</p>

### Capacity forecast · resources · sign-in

<table>
<tr>
<td width="50%"><img src="docs/screenshots/05-capacity-forecast.png" alt="Capacity forecast analytics"></td>
<td width="50%"><img src="docs/screenshots/07-resources.png" alt="Run history and data health"></td>
</tr>
<tr>
<td align="center">Capacity trends and department load</td>
<td align="center">Run history, critic scores, exports</td>
</tr>
</table>

<p align="center">
  <img src="docs/screenshots/02-login.png" alt="Hospital workspace sign-in" width="80%">
</p>

---

## What it does

| Feature | What you get |
|---------|----------------|
| **Capacity forecasting** | 24–48h admission / OPD workload from appointments and bed occupancy |
| **Policy RAG** | Hospital SOPs from Qdrant with `policy_id` citations |
| **Resource allocation** | Staffing and clinical supply coordination across departments |
| **Safety critic** | Blocks clinical-advice language; scores grounding before you see the plan |
| **Human approval queue** | Supply reorders and low-confidence actions need operator sign-off |
| **Policy Assistant** | Operator AI chat over runs, supplies, policies, and safety history |

**Scenario presets:** `ed_surge` · `opd_peak` · `icu_capacity` · `supply_shortage`

---

## Architecture

```
Next.js UI  →  FastAPI  →  LangGraph (7 agents)
                  ↓              ↓
            PostgreSQL       Qdrant (policies)
                  ↓              ↓
              Redis          Healthcare MCP (FHIR + local tools)
```

**Pipeline:** Supervisor → Capacity Forecast → parallel *(FHIR Ops · Policy RAG · Resource Allocation)* → Aggregator → Safety Critic → Human Approval Queue

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/INTERVIEW_GUIDE.md`](docs/INTERVIEW_GUIDE.md)

---

## Quick start

**Needs:** Docker Compose · Python 3.11+ · Node.js 20.9+ · [Groq](https://console.groq.com) + [Gemini](https://aistudio.google.com) API keys

```bash
# 1. Infrastructure
docker compose up -d

# 2. Backend
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

# 3. Frontend
cd ../web/careops-ui
npm install && npm run dev
```

Open **http://localhost:3000** → register a facility → **Scenario Planner** → run Emergency Surge → ask the **Policy Assistant**.

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

## Layout

```
apps/api/              FastAPI + LangGraph + healthcare MCP
apps/web/careops-ui/   Operator dashboard
scripts/               Demo + hospital seed scripts
data/fhir/             Synthetic FHIR fixtures
docs/                  Architecture, API, deploy, screenshots
```

Deploy: [`docs/DEPLOY.md`](docs/DEPLOY.md) · Backend on Render · Frontend on Vercel

---

## Author

**[shubhangini67](https://github.com/shubhangini67)**

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 shubhangini67.

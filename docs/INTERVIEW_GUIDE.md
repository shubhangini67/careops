# CareOps AI — Interview Guide

A concise reference for explaining the architecture, agent flow, MCP integration, RAG, evaluation, and safety decisions.

## Elevator pitch

CareOps AI is a **hospital operations copilot** built on a LangGraph multi-agent pipeline. It forecasts workload, reads capacity/supply signals, retrieves **hospital policies with citations**, and routes sensitive actions to a **human approval queue**. It explicitly does **not** give clinical advice.

## Architecture (high level)

```
Next.js UI  →  FastAPI (/api/v1)  →  LangGraph (7 agents)
                      ↓                    ↓
              PostgreSQL (audit)     Qdrant (policies)
                      ↓                    ↓
                 Redis (cache)      Healthcare MCP (local FHIR/tools)
```

**Agent flow** uses parallel fan-out, critic scoring, and a human approval queue — orchestration patterns adapted for hospital operations.

## Agent flow

```
Supervisor → Capacity Forecast → [FHIR Ops | Policy RAG | Resource Allocation] (parallel)
    → Aggregator → Safety Critic → Human Approval Queue → API response
```

| Agent | Role |
|-------|------|
| Supervisor | Validates scenario (`ed_surge`, `opd_peak`, etc.) |
| Capacity Forecast | 24–48h workload from appointments + bed occupancy |
| FHIR Operations | Synthetic encounter summaries — **no PHI** |
| Policy RAG | Qdrant search over hospital SOPs → **citations** |
| Resource Allocation | Staffing + supply shortage coordination |
| Safety Critic | Blocks diagnosis/treatment language; scores grounding |
| Human Approval | Creates `action_queue` items when confidence < 0.75 |

## Healthcare MCP

CareOps uses a **local healthcare MCP server** (`healthcare_mcp_server.py`) exposing deterministic tools backed by PostgreSQL + synthetic FHIR JSON. No external food-delivery integration.

## RAG design

- **Collection:** `sop_memory` in Qdrant (org-scoped)
- **Embeddings:** Gemini `gemini-embedding-001`
- **Retrieval:** Policy RAG agent queries top-k SOPs; every policy-based answer includes `citations[]` with `policy_id` + excerpt
- **Safety:** Critic penalizes missing citations (lower confidence → approval queue)

## Evaluation

- **Golden set:** `tests/fixtures/careops_golden_policy_questions.json` (16 synthetic operational/policy questions)
- **RAGAS:** faithfulness, answer relevancy, context precision (`evals/test_ragas_complaint.py`)
- **DeepEval:** hallucination checks (`evals/test_deepeval_quality.py`)
- **CI:** GitHub Actions runs unit tests + eval suites when API keys are configured

Record only metrics from executed test runs — do not invent benchmark numbers.

## Safety decisions

1. **No clinical advice** — blocklist in Safety Critic (`diagnose`, `prescribe`, `medication`, etc.)
2. **Synthetic data only** — FHIR fixtures use `SYN-PAT-*` IDs; dashboards show department aggregates
3. **Human-in-the-loop** — supply reorders and low-confidence plans → Action Queue (`approve_required` tier)
4. **PHI-free UI** — no patient names/MRNs in operator dashboards
5. **Langfuse optional** — missing credentials do not block startup

## Trade-offs

| Choice | Why | Cost |
|--------|-----|------|
| Reuse LangGraph shell vs rewrite | Faster delivery, proven critic/queue patterns | Some legacy table names remain (`planning_runs`) |
| Local MCP vs live EHR | Demo-safe, deterministic, no HIPAA scope | Not production EHR integration |
| Gemini embeddings | Quality for policy retrieval | Requires second API key |
| Keep PostgreSQL audit trail | Compliance-friendly run history | Migration complexity from restaurant schema |

## Demo script (2 minutes)

1. Register facility at `/register`
2. Open **Scenario Planner** → run `Emergency Surge`
3. Show policy citations in response
4. Open **Approval Queue** → pending supply/plan review actions
5. Ask Policy Assistant a question about ED surge threshold → cited SOP

## Key files

- Graph: `apps/api/app/orchestration/careops_graph.py`
- MCP tools: `apps/api/app/infrastructure/healthcare/mcp_tools.py`
- Seeds: `scripts/seed_hospital_data.py`, `scripts/seed_hospital_policies.py`
- FHIR: `data/fhir/`

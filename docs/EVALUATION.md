# CareOps AI Evaluation

Reflects Phase 5 complete (LangSmith golden dataset, regression CI gate, RAGAS, and DeepEval) and Phase 6A in progress.

---

## Evaluation layers

CareOps AI is evaluated across five layers: software correctness, LangSmith regression, planning quality, data realism, and audit visibility.

---

### Layer 1: software correctness

Standard pytest suite covering service logic, graph nodes, and API routes.

```bash
cd apps/api

# Unit tests
pytest tests/unit -q

# Integration tests (requires running PostgreSQL, Qdrant, and Redis)
pytest tests/integration -q --ignore=tests/integration/test_langgraph_flow.py
```

- `tests/unit/`: individual service logic, critic helpers, inventory alerts, forecast signal, and Guest Concierge's own tool handlers, session state, and route contract (mocked Swiggy client, no live network needed)
- `tests/integration/`: API route responses, database persistence, auth flow

---

### Layer 2: LangSmith regression evals

The primary quality gate. A golden dataset of 50 curated planning runs is stored in LangSmith as `careops-golden-v1`. Automated evaluators run against this dataset and the CI gate requires a 90% pass rate.

**Building the dataset**

```bash
cd apps/api
python ../../scripts/build_golden_dataset.py
```

`build_golden_dataset.py` (in the root `scripts/` folder) pulls approved planning runs from PostgreSQL with a minimum critic score, uploads them to LangSmith as `careops-golden-v1`, and saves a local `golden_runs.json` fixture for offline CI use.

**Running the CI gate**

```bash
pytest tests/unit/test_langsmith_evals.py -v
```

The gate runs against the local `golden_runs.json` fixture, with no live LangSmith API calls required. It checks that the critic score clears a minimum threshold on all golden runs, that shortage-alert runs contain restock actions, and that overall pass rate clears 90 percent.

**Requirements:** `LANGSMITH_API_KEY` for building the dataset. The CI gate itself uses the local fixture only and requires no provider key.

---

### Layer 3: LLM quality evals, RAGAS and DeepEval

Fine-grained evals on complaint-RAG quality and critic and agent output quality. Both suites use Groq as the evaluator LLM.

```bash
pytest evals/test_ragas_complaint.py -v -W ignore::DeprecationWarning
pytest evals/test_deepeval_quality.py -v -W ignore::DeprecationWarning
```

| Suite | File | Metric | What it checks |
|-------|------|--------|----------------|
| RAGAS | `evals/test_ragas_complaint.py` | Faithfulness | Every claim in the complaint recommendations is supported by retrieved Qdrant context, not hallucinated |
| RAGAS | `evals/test_ragas_complaint.py` | Context precision | Retrieved context is actually relevant to the complaint question asked |
| DeepEval | `evals/test_deepeval_quality.py` | HallucinationMetric | Critic output does not make claims contradicted by the aggregated plan |
| DeepEval | `evals/test_deepeval_quality.py` | AnswerRelevancyMetric | Agent outputs address the scenario's actual operational question |

Both suites currently run against a static, hand-written fixture (`evals/complaint_rag_samples.json` for RAGAS, literal test-case dictionaries inside `test_deepeval_quality.py` for DeepEval), not against live pipeline output.

**Candidate dataset refresh, not yet promoted:** `scripts/build_ragas_dataset.py` and `scripts/build_deepeval_dataset.py` extract candidate samples from real `PlanningRun` records, so the eval fixtures can be regenerated from actual current pipeline behavior instead of staying frozen at the point they were first written. Their extraction logic is unit-tested in `apps/api/tests/unit/test_build_eval_datasets.py`. Promoting the candidates these scripts produce into the actual golden fixture files, so the eval suites reflect the live-signals and dynamic-scenario work shipped since, is tracked as upcoming work and has not been done yet.

---

### Layer 4: planning quality

Manual and automated checks on recommendation quality.

- Recommendations should match the selected scenario's framing. A high-volume scenario should surface peak-pressure actions, not low-stock-weekend actions.
- Critic notes should clearly explain the verdict with scenario-specific reasoning.
- Dimension scores should reflect actual plan strength, with safety and feasibility weighted highest.
- Revision reasons and actionable feedback should be non-generic when the verdict is not approved.
- What-if simulator scores (cost pressure, benefit, tradeoff) should move predictably when cover count changes.

---

### Layer 5: data realism

Checks that seeded data flows correctly through the pipeline.

- Reservation pressure for the target date should align with the scenario.
- Inventory shortage and overstock signals should be reflected in inventory recommendations.
- Complaint patterns retrieved from Qdrant should match the operational context.
- The Prophet forecast should show peak demand in the correct service window for each scenario.

Verify current data coverage with:

```
GET /api/v1/data-health
```

---

### Layer 6: audit visibility

- Every planning run should be persisted with critic verdict, score, recommendation detail, and full metadata.
- The `/data` page (which merges the former `/runs` and `/data-health` pages) should remain usable: scenario filter, date range, critic score trend, run detail panel, and PDF and Excel export should all work.
- `GET /api/v1/data-health` should accurately reflect current seeded data coverage.
- The observability summary should correctly aggregate recent runs.

---

## Sentry exception capture

All unhandled exceptions are captured by Sentry (`sentry-sdk` with FastAPI integration), conditional on `SENTRY_DSN` being set. LangGraph node failures are wrapped so stack traces are tagged by node name.

Smoke test:

```
GET /debug/sentry-test
```

---

## Observability

`GET /api/v1/data-health` (used by the frontend's `/data` page) and `GET /api/v1/observability/summary` together provide recent aggregate stats: total runs, success rate, average critic score, average duration, and breakdown by verdict and scenario.

Langfuse tracing (conditional on `LANGFUSE_SECRET_KEY`) attaches one span per graph node and one generation per real LLM call to every planning run, and a Kindred replay endpoint (`POST /replay`, mounted outside `/api/v1`) supports single-generation prompt replay for debugging.

---

## References

- `apps/api/tests/`: backend test suite
- `apps/api/evals/`: RAGAS and DeepEval eval scripts
- `apps/api/tests/unit/test_langsmith_evals.py`: LangSmith regression CI gate, local fixture
- `scripts/build_golden_dataset.py`: golden dataset builder
- `scripts/build_ragas_dataset.py`, `scripts/build_deepeval_dataset.py`: candidate dataset refresh scripts, not yet promoted into the golden fixtures
- `docs/AGENTS.md`: node-level responsibilities used for evaluating per-agent output quality

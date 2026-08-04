# Tests

Test documentation for CareOps AI. Phase 6A in progress.

## Test locations

| Suite | Location | Run command |
|-------|----------|-------------|
| Unit tests | `apps/api/tests/unit/` | `pytest tests/unit -q` |
| Integration tests | `apps/api/tests/integration/` | `pytest tests/integration -q --ignore=tests/integration/test_langgraph_flow.py` |
| LangSmith regression | `apps/api/tests/unit/test_langsmith_evals.py` | `pytest tests/unit/test_langsmith_evals.py -v` |
| RAGAS evals | `apps/api/evals/test_ragas_complaint.py` | `pytest evals/test_ragas_complaint.py -v` |
| DeepEval evals | `apps/api/evals/test_deepeval_quality.py` | `pytest evals/test_deepeval_quality.py -v` |

`apps/api/tests/unit/test_concierge_service.py` and `test_concierge_route.py` cover Guest Concierge's tool handlers, session state, and route contract with a mocked Swiggy client; they run as part of the standard unit suite above, no live network needed.

All commands run from `apps/api/` with the virtual environment activated.

## Standard test run

```bash
cd apps/api
pytest tests/ -q --ignore=tests/integration/test_langgraph_flow.py
```

`test_langgraph_flow.py` references a removed module and is excluded until rewritten.

RAGAS and DeepEval currently evaluate against static hand-written fixtures. `scripts/build_ragas_dataset.py` and `scripts/build_deepeval_dataset.py` extract fresh candidate samples from real planning runs, but their output has not yet been promoted into the golden fixtures used by these test suites.

## LLM quality evals

These require a live `GROQ_API_KEY` and make real LLM calls. Do not include in standard CI.

```bash
# Build golden dataset (requires LANGSMITH_API_KEY + GROQ_API_KEY)
# Run from apps/api/
python ../../scripts/build_golden_dataset.py

# Run regression gate against local fixture: requires 90% pass rate
pytest tests/unit/test_langsmith_evals.py -v

# RAGAS faithfulness on complaint RAG
pytest evals/test_ragas_complaint.py -v -W ignore::DeprecationWarning

# DeepEval hallucination + relevancy
pytest evals/test_deepeval_quality.py -v -W ignore::DeprecationWarning
```

## Frontend tests

The frontend (`apps/web/careops-ui`) does not yet have an automated test suite. Type checking runs via `tsc --noEmit`.

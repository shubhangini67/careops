"""
P4-10: RAGAS evaluation for the complaint_intelligence RAG pipeline.

Evaluates faithfulness and context precision of the complaint node's
Qdrant retrieval + LLM recommendation outputs using Groq as the
RAGAS evaluator LLM.

Run explicitly (NOT part of normal pytest suite — lives outside testpaths):
    pytest evals/test_ragas_complaint.py -v -W ignore::DeprecationWarning

Requires env vars: GROQ_API_KEY (evaluator LLM).
Results are logged to LangSmith when LANGSMITH_API_KEY is set.

Note: answer_relevancy is excluded — it requires an embeddings provider.
Configure an OpenAI-compatible embeddings endpoint and add AnswerRelevancy
to the metrics list to enable it.
"""

import json
import os
from pathlib import Path

import pytest
from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import SingleTurnSample
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import ContextPrecision, Faithfulness

FAITHFULNESS_THRESHOLD = 0.8
DATASET_PATH = Path(__file__).parent / "complaint_rag_samples.json"


def _build_evaluator():
    """Build Groq-backed LLM wrapper for RAGAS."""
    from langchain_groq import ChatGroq

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set — skipping RAGAS eval")

    return LangchainLLMWrapper(
        ChatGroq(model="llama-3.3-70b-versatile", api_key=api_key)
    )


def _load_dataset() -> EvaluationDataset:
    raw = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    samples = [
        SingleTurnSample(
            user_input=s["question"],
            response=s["answer"],
            retrieved_contexts=s["contexts"],
            reference=s.get("ground_truth"),
        )
        for s in raw
    ]
    return EvaluationDataset(samples=samples)


def _log_to_langsmith(scores: dict) -> None:
    """Log RAGAS scores as a completed run to LangSmith if credentials are present."""
    api_key = os.environ.get("LANGSMITH_API_KEY", "")
    if not api_key:
        return
    try:
        import uuid
        from datetime import datetime, timezone
        from langsmith import Client

        client = Client(api_key=api_key)
        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        client.create_run(
            id=run_id,
            name="ragas_complaint_rag_eval",
            run_type="chain",
            inputs={"dataset": str(DATASET_PATH)},
            start_time=now,
            project_name=os.environ.get("LANGSMITH_PROJECT", "CareOps AI"),
        )
        client.update_run(
            run_id,
            outputs=scores,
            end_time=now,
            status="success",
        )
        print("  Scores logged to LangSmith.")
    except Exception as exc:
        print(f"  LangSmith logging skipped: {exc}")


@pytest.fixture(scope="module")
def ragas_results():
    """Run the full RAGAS evaluation once; share results across tests."""
    llm = _build_evaluator()
    dataset = _load_dataset()

    result = evaluate(
        dataset=dataset,
        metrics=[
            Faithfulness(llm=llm),
            ContextPrecision(llm=llm),
        ],
    )

    df = result.to_pandas()
    faithfulness = float(df["faithfulness"].mean())
    context_precision = float(df["context_precision"].mean())

    import math
    if math.isnan(faithfulness) and math.isnan(context_precision):
        pytest.skip(
            "All RAGAS jobs failed (likely provider rate limit or timeout). "
            "Wait for the token limit to reset and re-run."
        )

    scores = {
        "faithfulness": faithfulness,
        "context_precision": context_precision,
        "n_samples": len(df),
        "per_sample_faithfulness": df["faithfulness"].tolist(),
        "per_sample_context_precision": df["context_precision"].tolist(),
    }

    print("\n--- RAGAS complaint RAG scores ---")
    print(f"  faithfulness:      {faithfulness:.3f}  (threshold >= {FAITHFULNESS_THRESHOLD})")
    print(f"  context_precision: {context_precision:.3f}  (informational)")
    print(f"  n_samples:         {scores['n_samples']}")

    _log_to_langsmith({k: v for k, v in scores.items() if isinstance(v, float)})
    return scores


def test_faithfulness(ragas_results):
    """Primary gate: LLM answers must be grounded in the retrieved complaint context."""
    score = ragas_results["faithfulness"]
    assert score >= FAITHFULNESS_THRESHOLD, (
        f"Faithfulness {score:.3f} is below threshold {FAITHFULNESS_THRESHOLD}. "
        "The complaint node LLM is generating claims not grounded in the retrieved context. "
        f"Per-sample scores: {ragas_results['per_sample_faithfulness']}"
    )


def test_context_precision_reported(ragas_results):
    """Qdrant retrieval quality baseline — reported but not hard-gated."""
    import math
    score = ragas_results["context_precision"]
    if math.isnan(score):
        pytest.skip("Context precision score is nan — partial provider failure.")
    print(f"\nContext precision (informational): {score:.3f}")
    assert 0.0 <= score <= 1.0, f"Context precision out of range: {score}"

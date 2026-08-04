"""Unit tests for the candidate-generating dataset-refresh scripts
(scripts/build_ragas_dataset.py, scripts/build_deepeval_dataset.py).

These only exercise the pure extraction functions against mock PlanningRun-like
objects — no live DB needed. Verifies they read the real final_response shape
(final_response["recommendations"][agent], final_response["rag_context"],
final_response["critic"]) and degrade gracefully on missing/malformed data.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from build_ragas_dataset import _extract_sample  # noqa: E402
from build_deepeval_dataset import _hallucination_candidate, _relevancy_candidates  # noqa: E402


def _run(final_response: dict, run_id: int = 1, scenario: str = "friday_rush", target_date: str = "2026-05-08"):
    return SimpleNamespace(id=run_id, scenario=scenario, target_date=target_date, final_response=final_response)


COMPLAINT_RESPONSE = {
    "recommendations": {
        "complaint": {
            "overall_summary": "Garlic bread stockouts are the top recurring issue.",
            "action_items": ["Stock 80 portions of garlic bread before Friday peak."],
            "data": {"unique_complaints": ["Ran out of Garlic Bread at 8pm on a Friday."]},
        },
    },
    "rag_context": {
        "similar_complaints": [{"text": "Ran out of Garlic Bread again on May 29.", "score": 0.9}],
        "relevant_sops": [{"text": "Garlic bread must be stocked to a minimum of 80 portions.", "score": 0.85}],
    },
}


# ── build_ragas_dataset ──────────────────────────────────────────────────────

def test_ragas_extract_sample_happy_path():
    sample = _extract_sample(_run(COMPLAINT_RESPONSE))
    assert sample is not None
    assert sample["question"] == "Ran out of Garlic Bread at 8pm on a Friday."
    assert len(sample["contexts"]) == 2
    assert sample["answer"] == "Garlic bread stockouts are the top recurring issue."
    assert sample["ground_truth"] is None
    assert sample["source_run_id"] == 1


def test_ragas_falls_back_to_action_items_when_no_summary():
    response = {
        "recommendations": {
            "complaint": {
                "action_items": ["Fix the thing.", "Watch the other thing."],
                "data": {"unique_complaints": ["Something went wrong."]},
            },
        },
        "rag_context": {"similar_complaints": [{"text": "context line"}], "relevant_sops": []},
    }
    sample = _extract_sample(_run(response))
    assert sample["answer"] == "Fix the thing. Watch the other thing."


def test_ragas_skips_run_with_no_unique_complaints():
    response = {
        "recommendations": {"complaint": {"overall_summary": "x", "data": {"unique_complaints": []}}},
        "rag_context": {"similar_complaints": [{"text": "y"}]},
    }
    assert _extract_sample(_run(response)) is None


def test_ragas_skips_run_with_no_rag_context():
    response = {
        "recommendations": {
            "complaint": {"overall_summary": "x", "data": {"unique_complaints": ["complaint text"]}},
        },
        "rag_context": {},
    }
    assert _extract_sample(_run(response)) is None


def test_ragas_handles_missing_complaint_block():
    assert _extract_sample(_run({"recommendations": {}})) is None
    assert _extract_sample(_run({})) is None
    assert _extract_sample(_run({"recommendations": {"complaint": None}})) is None


# ── build_deepeval_dataset ───────────────────────────────────────────────────

CRITIC_RESPONSE = {
    "critic": {"notes": "Plan addresses the shortage and occupancy risk appropriately."},
    "recommendations": {
        "reservation": {"data": {"occupancy_pct": 92}},
        "inventory": {
            "restock_actions": ["Order 5kg Mozzarella immediately."],
            "data": {"shortage_alerts": [
                {"ingredient": "Mozzarella", "severity": "critical"},
                {"ingredient": "Basil", "severity": "warning"},
            ]},
        },
        "forecast": {"data": {"demand_ratio": 1.4}},
    },
}


def test_deepeval_hallucination_candidate_happy_path():
    candidate = _hallucination_candidate(_run(CRITIC_RESPONSE, scenario="friday_rush", target_date="2026-05-08"))
    assert candidate is not None
    assert candidate["output"] == "Plan addresses the shortage and occupancy risk appropriately."
    assert any("92%" in c for c in candidate["context"])
    assert any("1 critical" in c for c in candidate["context"])
    assert any("1.4" in c for c in candidate["context"])
    assert "friday_rush" in candidate["input"]


def test_deepeval_hallucination_skips_when_no_notes():
    response = {"critic": {}, "recommendations": {}}
    assert _hallucination_candidate(_run(response)) is None


def test_deepeval_hallucination_skips_when_insufficient_context():
    # No occupancy, no demand ratio, and inventory has no shortages at all —
    # still emits the shortage-count line (0 critical), which alone isn't
    # enough context to be a useful hallucination case.
    response = {"critic": {"notes": "Looks fine."}, "recommendations": {}}
    assert _hallucination_candidate(_run(response)) is None


def test_deepeval_relevancy_candidates_extracts_complaint_and_inventory():
    merged = {
        **CRITIC_RESPONSE,
        **COMPLAINT_RESPONSE,
        "recommendations": {
            **CRITIC_RESPONSE["recommendations"],
            **COMPLAINT_RESPONSE["recommendations"],
        },
    }
    candidates = _relevancy_candidates(_run(merged))
    by_input = {c["input"]: c for c in candidates}
    complaint_q = next(k for k in by_input if "complaint issues" in k)
    inventory_q = next(k for k in by_input if "inventory actions" in k)

    assert by_input[complaint_q]["output"] == "Garlic bread stockouts are the top recurring issue."
    assert by_input[complaint_q]["retrieval_context"]

    assert "Mozzarella is critically short." in by_input[inventory_q]["retrieval_context"]
    # Basil is only "warning" severity — must not appear as a critical-shortage fact
    assert not any("Basil" in c for c in by_input[inventory_q]["retrieval_context"])


def test_deepeval_relevancy_returns_empty_list_for_empty_run():
    assert _relevancy_candidates(_run({})) == []

"""
P5-10 LangSmith regression eval CI gate.

Loads the golden dataset fixture and runs two evaluators against every example.
Fails if overall pass rate drops below 90% — catches prompt/node regressions.

Run with: pytest tests/unit/test_langsmith_evals.py -v
"""

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "golden_runs.json"
PASS_RATE_THRESHOLD = 0.90
CRITIC_SCORE_THRESHOLD = 0.70


# ── Evaluators ────────────────────────────────────────────────────────────────

def eval_critic_score(run: dict) -> dict:
    """Critic score must meet the configured approval threshold."""
    score = run.get("critic_score") or 0.0
    passed = score >= CRITIC_SCORE_THRESHOLD
    return {
        "name": "critic_score",
        "passed": passed,
        "detail": f"score={score} (threshold={CRITIC_SCORE_THRESHOLD})",
    }


def eval_restock_when_shortage(run: dict) -> dict:
    """When inventory shortage alerts exist, plan must contain restock actions."""
    has_shortage = run.get("has_shortage_alerts", False)
    restock_actions = run.get("inventory_restock_actions", [])

    if not has_shortage:
        return {"name": "restock_when_shortage", "passed": True, "detail": "no shortage — skipped"}

    passed = len(restock_actions) > 0
    return {
        "name": "restock_when_shortage",
        "passed": passed,
        "detail": f"{len(restock_actions)} restock action(s) found",
    }


EVALUATORS = [eval_critic_score, eval_restock_when_shortage]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_evaluators(example: dict) -> list[dict]:
    return [ev(example) for ev in EVALUATORS]


def _pass_rate(results: list[list[dict]]) -> float:
    total = sum(len(r) for r in results)
    passed = sum(r["passed"] for batch in results for r in batch)
    return passed / total if total > 0 else 0.0


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_fixture_exists_and_non_empty():
    assert FIXTURE_PATH.exists(), f"Golden dataset fixture not found: {FIXTURE_PATH}"
    examples = json.loads(FIXTURE_PATH.read_text())
    assert len(examples) >= 3, "Golden dataset must have at least 3 examples"


def test_all_golden_runs_pass_evaluators():
    examples = json.loads(FIXTURE_PATH.read_text())
    results = [_run_evaluators(ex) for ex in examples]

    failures = [
        (examples[i]["scenario"], r["name"], r["detail"])
        for i, batch in enumerate(results)
        for r in batch
        if not r["passed"]
    ]

    rate = _pass_rate(results)
    assert rate >= PASS_RATE_THRESHOLD, (
        f"Eval pass rate {rate:.0%} is below {PASS_RATE_THRESHOLD:.0%} threshold.\n"
        f"Failures:\n" + "\n".join(f"  [{s}] {n}: {d}" for s, n, d in failures)
    )


def test_critic_score_evaluator_passes_good_run():
    result = eval_critic_score({"critic_score": 0.91})
    assert result["passed"] is True


def test_critic_score_evaluator_fails_low_score():
    result = eval_critic_score({"critic_score": 0.55})
    assert result["passed"] is False


def test_restock_evaluator_passes_when_restock_present():
    result = eval_restock_when_shortage({
        "has_shortage_alerts": True,
        "inventory_restock_actions": ["Order 4kg Mozzarella immediately"],
    })
    assert result["passed"] is True


def test_restock_evaluator_fails_when_restock_missing():
    result = eval_restock_when_shortage({
        "has_shortage_alerts": True,
        "inventory_restock_actions": [],
    })
    assert result["passed"] is False


def test_restock_evaluator_skips_when_no_shortage():
    result = eval_restock_when_shortage({"has_shortage_alerts": False})
    assert result["passed"] is True


def test_intentional_regression_fails_ci_gate():
    """Simulates a regressed run — verifies CI gate correctly rejects it."""
    regressed_runs = [
        {"scenario": "friday_rush", "critic_score": 0.3, "has_shortage_alerts": True, "inventory_restock_actions": []},
        {"scenario": "weekday_lunch", "critic_score": 0.4, "has_shortage_alerts": False, "inventory_restock_actions": []},
    ]
    results = [_run_evaluators(r) for r in regressed_runs]
    rate = _pass_rate(results)
    assert rate < PASS_RATE_THRESHOLD, (
        "Regression test should fail the CI gate — check evaluator logic"
    )

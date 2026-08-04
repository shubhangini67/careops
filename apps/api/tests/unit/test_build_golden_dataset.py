"""Regression test for scripts/build_golden_dataset.py's field extraction.

Guards against the bug found P6-post-S13c: the extractors originally read
final_response["agents"][...], but final_assembler_node actually writes
final_response["recommendations"][...] — so restock_actions/shortage_alerts
were silently always empty/false for every golden-set row, making the
restock_when_shortage evaluator in test_langsmith_evals.py a permanent no-op.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from build_golden_dataset import _extract_restock_actions, _has_shortage_alerts  # noqa: E402


def _run(final_response: dict) -> SimpleNamespace:
    return SimpleNamespace(final_response=final_response)


def test_extracts_restock_actions_from_recommendations_shape():
    run = _run({
        "recommendations": {
            "inventory": {
                "restock_actions": ["Order 5kg tomatoes immediately"],
                "data": {"shortage_alerts": [{"ingredient": "tomatoes"}]},
            },
        },
    })
    assert _extract_restock_actions(run) == ["Order 5kg tomatoes immediately"]
    assert _has_shortage_alerts(run) is True


def test_no_shortages_returns_empty_and_false():
    run = _run({
        "recommendations": {
            "inventory": {"restock_actions": [], "data": {"shortage_alerts": []}},
        },
    })
    assert _extract_restock_actions(run) == []
    assert _has_shortage_alerts(run) is False


@pytest.mark.parametrize("final_response", [
    {},
    {"recommendations": {}},
    {"recommendations": {"inventory": None}},
    {"agents": {"inventory": {"recommendation": {"restock_actions": ["stale shape"]}}}},
])
def test_malformed_or_stale_shapes_degrade_gracefully(final_response):
    run = _run(final_response)
    assert _extract_restock_actions(run) == []
    assert _has_shortage_alerts(run) is False

"""
Build candidate DeepEval cases (critic hallucination + agent relevancy) from
live approved planning runs.

apps/api/evals/test_deepeval_quality.py's CRITIC_HALLUCINATION_CASES and
RELEVANCY_CASES are static, hand-written, and fixed at authoring time (6 cases
total — see docs/DECISIONS.md D-013), so they'll never catch a drift pattern
that didn't exist when someone wrote them. This script samples real critic
verdicts and agent recommendations from recent approved runs and writes them
as CANDIDATE cases for human review — it never edits test_deepeval_quality.py
directly.

Both "context"/"retrieval_context" fields here are built from structured data
values already present in the run (occupancy%, shortage counts, demand ratio,
RAG snippets), not from an LLM — same convention the hand-written cases use.
Nothing is auto-promoted: a human reviews each candidate and copies it into
test_deepeval_quality.py's CRITIC_HALLUCINATION_CASES / RELEVANCY_CASES by hand.

Usage:
    cd apps/api
    python ../../scripts/build_deepeval_dataset.py [--limit N] [--dry-run]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "apps" / "api" / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.models import PlanningRun
from app.core.settings import get_settings

DEFAULT_LIMIT   = 30
CANDIDATES_PATH = Path(__file__).parent.parent / "apps" / "api" / "evals" / "deepeval_cases.candidates.json"


def _hallucination_candidate(run: PlanningRun) -> dict | None:
    """Ground truth = structured facts from the bundle; actual_output = critic notes."""
    try:
        response = run.final_response or {}
        critic = response.get("critic") or {}
        notes = critic.get("notes")
        if not notes:
            return None

        recs = response.get("recommendations") or {}
        reservation_data = (recs.get("reservation") or {}).get("data") or {}
        inventory_data = (recs.get("inventory") or {}).get("data") or {}
        forecast_data = (recs.get("forecast") or {}).get("data") or {}

        occupancy = reservation_data.get("occupancy_pct")
        shortages = inventory_data.get("shortage_alerts") or []
        critical_shortages = sum(
            1 for a in shortages if isinstance(a, dict) and a.get("severity") == "critical"
        )
        demand_ratio = forecast_data.get("demand_ratio") or inventory_data.get("demand_ratio")

        context = []
        if occupancy is not None:
            context.append(f"Occupancy is at {occupancy}% for the {run.scenario} service window.")
        context.append(f"There are {critical_shortages} critical inventory shortage(s) flagged for this scenario.")
        if demand_ratio is not None:
            context.append(f"Demand ratio is {demand_ratio}.")
        if len(context) < 2:
            return None

        return {
            "input": f"Critic evaluation of {run.scenario} planning bundle "
                     f"(target_date={run.target_date}).",
            "output": str(notes),
            "context": context,
            "source_run_id": run.id,
        }
    except (KeyError, TypeError, AttributeError):
        return None


_RELEVANCY_QUESTIONS = {
    "complaint":   "What are the top complaint issues and recommended fixes for {scenario} service?",
    "forecast":    "What demand forecast actions should be taken for the upcoming {scenario} service?",
    "inventory":   "What inventory actions are needed for the {scenario} scenario?",
    "reservation": "What reservation and capacity actions are needed for {scenario} service?",
}


def _relevancy_candidates(run: PlanningRun) -> list[dict]:
    candidates = []
    try:
        response = run.final_response or {}
        recs = response.get("recommendations") or {}
        rag_context = response.get("rag_context") or {}

        for agent, question_template in _RELEVANCY_QUESTIONS.items():
            agent_out = recs.get(agent)
            if not isinstance(agent_out, dict):
                continue

            if agent == "complaint":
                answer = agent_out.get("overall_summary")
                if not answer:
                    answer = " ".join(str(a) for a in (agent_out.get("action_items") or []))
                retrieval_context = [
                    str(item.get("text"))
                    for item in (rag_context.get("similar_complaints") or []) + (rag_context.get("relevant_sops") or [])
                    if isinstance(item, dict) and item.get("text")
                ]
            elif agent == "inventory":
                answer = " ".join(str(a) for a in (agent_out.get("restock_actions") or []))
                data = agent_out.get("data") or {}
                retrieval_context = [
                    f"{a.get('ingredient')} is critically short."
                    for a in (data.get("shortage_alerts") or [])
                    if isinstance(a, dict) and a.get("severity") == "critical"
                ]
            else:
                answer = agent_out.get("recommendation")
                data = agent_out.get("data") or {}
                retrieval_context = [f"{k}: {v}" for k, v in data.items() if isinstance(v, (str, int, float, bool))][:5]

            if not answer or not retrieval_context:
                continue

            candidates.append({
                "input": question_template.format(scenario=run.scenario),
                "output": str(answer),
                "retrieval_context": retrieval_context,
                "source_run_id": run.id,
            })
    except (KeyError, TypeError, AttributeError):
        pass
    return candidates


def build(limit: int = DEFAULT_LIMIT, dry_run: bool = False) -> None:
    settings = get_settings()
    engine   = create_engine(settings.postgres_url)
    Session  = sessionmaker(bind=engine)
    db       = Session()

    runs = (
        db.query(PlanningRun)
        .filter(
            PlanningRun.critic_verdict == "approved",
            PlanningRun.final_response.isnot(None),
        )
        .order_by(PlanningRun.created_at.desc())
        .limit(limit)
        .all()
    )
    db.close()

    if not runs:
        print("No approved runs found in the DB. Run some planning scenarios first.")
        return

    existing = {"hallucination": [], "relevancy": []}
    existing_inputs = set()
    if CANDIDATES_PATH.exists():
        existing = json.loads(CANDIDATES_PATH.read_text())
        existing_inputs = {
            c["input"] for c in existing.get("hallucination", []) + existing.get("relevancy", [])
        }

    new_hallucination = []
    new_relevancy = []
    for run in runs:
        h = _hallucination_candidate(run)
        if h and h["input"] not in existing_inputs:
            existing_inputs.add(h["input"])
            new_hallucination.append(h)
        for r in _relevancy_candidates(run):
            if r["input"] not in existing_inputs:
                existing_inputs.add(r["input"])
                new_relevancy.append(r)

    print(f"Scanned {len(runs)} approved run(s) -> "
          f"{len(new_hallucination)} new hallucination candidate(s), "
          f"{len(new_relevancy)} new relevancy candidate(s).")

    if dry_run:
        print(json.dumps({"hallucination": new_hallucination, "relevancy": new_relevancy}, indent=2))
        return

    if not new_hallucination and not new_relevancy:
        print("Nothing new to write.")
        return

    combined = {
        "hallucination": existing.get("hallucination", []) + new_hallucination,
        "relevancy": existing.get("relevancy", []) + new_relevancy,
    }
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(json.dumps(combined, indent=2))
    print(f"Wrote candidates -> {CANDIDATES_PATH}")
    print("Review each entry, then copy it into test_deepeval_quality.py's "
          "CRITIC_HALLUCINATION_CASES / RELEVANCY_CASES by hand — candidates are never auto-promoted.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    limit = DEFAULT_LIMIT
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])
    build(limit=limit, dry_run=dry_run)

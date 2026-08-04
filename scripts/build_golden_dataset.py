"""
P5-10: Build golden dataset from best historical planning runs.

Pulls approved runs (critic_score >= 0.7) from the DB, pushes them to a
LangSmith dataset called 'careops-golden-v1', and saves a local
fixture file for offline CI use.

Usage:
    cd apps/api
    python ../../scripts/build_golden_dataset.py
"""

import json
import os
import sys
from pathlib import Path

# Allow imports from apps/api/app
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "apps" / "api" / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.models import PlanningRun
from app.core.settings import get_settings

DATASET_NAME     = "careops-golden-v1"
SCORE_THRESHOLD  = 0.70
FIXTURE_PATH     = Path(__file__).parent.parent / "apps" / "api" / "tests" / "fixtures" / "golden_runs.json"


def _extract_restock_actions(run: PlanningRun) -> list[str]:
    # final_assembler_node writes final_response["recommendations"][agent], where each
    # entry is {**recommendation, "data": ...} — NOT under an "agents" key. The old
    # "agents" path here always KeyError'd and silently returned [], which meant
    # restock actions were empty for every golden-set row (see _has_shortage_alerts).
    try:
        inv = run.final_response["recommendations"]["inventory"]
        return inv.get("restock_actions", [])
    except (KeyError, TypeError, AttributeError):
        return []


def _has_shortage_alerts(run: PlanningRun) -> bool:
    try:
        alerts = run.final_response["recommendations"]["inventory"]["data"]["shortage_alerts"]
        return len(alerts) > 0
    except (KeyError, TypeError, AttributeError):
        return False


def build(dry_run: bool = False):
    settings = get_settings()
    engine   = create_engine(settings.postgres_url)
    Session  = sessionmaker(bind=engine)
    db       = Session()

    runs = (
        db.query(PlanningRun)
        .filter(
            PlanningRun.critic_verdict == "approved",
            PlanningRun.critic_score  >= SCORE_THRESHOLD,
            PlanningRun.final_response.isnot(None),
        )
        .order_by(PlanningRun.critic_score.desc())
        .limit(50)
        .all()
    )

    if not runs:
        print("No approved runs found in the DB. Run some planning scenarios first.")
        db.close()
        return

    print(f"Found {len(runs)} golden run(s) (verdict=approved, score>={SCORE_THRESHOLD})")

    examples = []
    for run in runs:
        restock = _extract_restock_actions(run)
        shortage = _has_shortage_alerts(run)
        examples.append({
            "id":                       run.id,
            "scenario":                 run.scenario,
            "target_date":              run.target_date,
            "critic_score":             float(run.critic_score),
            "critic_verdict":           run.critic_verdict,
            "has_shortage_alerts":      shortage,
            "inventory_restock_actions": restock,
        })

    # Save local fixture for CI
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(examples, indent=2))
    print(f"Fixture saved -> {FIXTURE_PATH}")

    if dry_run:
        print("Dry run — skipping LangSmith upload.")
        db.close()
        return

    # Push to LangSmith
    langsmith_key = os.getenv("LANGSMITH_API_KEY", "")
    if not langsmith_key:
        print("LANGSMITH_API_KEY not set — skipping LangSmith upload.")
        db.close()
        return

    from langsmith import Client
    client = Client(api_key=langsmith_key)

    # Delete existing dataset if present so we start fresh
    existing = [d for d in client.list_datasets() if d.name == DATASET_NAME]
    if existing:
        client.delete_dataset(dataset_id=existing[0].id)
        print(f"Deleted existing dataset '{DATASET_NAME}'")

    dataset = client.create_dataset(
        DATASET_NAME,
        description="Golden planning runs — approved, critic_score >= 0.7. Used for regression evals.",
    )

    inputs  = [{"scenario": ex["scenario"], "target_date": ex["target_date"]} for ex in examples]
    outputs = [
        {
            "critic_score":              ex["critic_score"],
            "has_shortage_alerts":       ex["has_shortage_alerts"],
            "inventory_restock_actions": ex["inventory_restock_actions"],
        }
        for ex in examples
    ]

    client.create_examples(inputs=inputs, outputs=outputs, dataset_id=dataset.id)
    print(f"Pushed {len(examples)} example(s) to LangSmith dataset '{DATASET_NAME}'")
    print(f"View at: https://smith.langchain.com/datasets/{dataset.id}")

    db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    build(dry_run=dry_run)

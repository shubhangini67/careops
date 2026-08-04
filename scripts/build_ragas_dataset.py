"""
Build candidate RAGAS samples for the complaint-RAG eval from live approved runs.

apps/api/evals/complaint_rag_samples.json is static and hand-curated (see
docs/DECISIONS.md D-013), which means evals/test_ragas_complaint.py can only ever
catch regressions on the same ~18 examples it was written with. This script
samples real complaint_intelligence RAG interactions from recent approved
planning runs and writes them as CANDIDATES for human review — it never writes
directly to the real, CI-gating complaint_rag_samples.json.

ground_truth is intentionally left null: RAGAS ground truth requires a human to
verify what the *correct* answer actually is. Auto-generating it (e.g. by asking
an LLM) would let the eval silently grade itself against its own unverified
opinion, which defeats the point of having ground truth at all.

Usage:
    cd apps/api
    python ../../scripts/build_ragas_dataset.py [--limit N] [--dry-run]

--dry-run prints what would be written without touching the candidates file.
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

DEFAULT_LIMIT     = 30
CURATED_PATH      = Path(__file__).parent.parent / "apps" / "api" / "evals" / "complaint_rag_samples.json"
CANDIDATES_PATH   = Path(__file__).parent.parent / "apps" / "api" / "evals" / "complaint_rag_samples.candidates.json"


def _extract_sample(run: PlanningRun) -> dict | None:
    """Extract one RAGAS candidate from a run's complaint_intelligence output.

    Mirrors the shape complaint_intelligence_node writes: final_response["rag_context"]
    = {"similar_complaints": [{"text": ...}], "relevant_sops": [{"text": ...}]}, and
    final_response["recommendations"]["complaint"] = {**recommendation, "data": {...}}.
    """
    try:
        response = run.final_response or {}
        complaint = (response.get("recommendations") or {}).get("complaint")
        rag_context = response.get("rag_context") or {}
        if not isinstance(complaint, dict):
            return None

        data = complaint.get("data") or {}
        unique_complaints = data.get("unique_complaints") or []
        if not unique_complaints:
            return None
        question = str(unique_complaints[0])

        contexts = [
            str(item.get("text"))
            for item in (rag_context.get("similar_complaints") or []) + (rag_context.get("relevant_sops") or [])
            if isinstance(item, dict) and item.get("text")
        ]
        if not contexts:
            return None

        answer = complaint.get("overall_summary")
        if not answer:
            action_items = complaint.get("action_items") or []
            answer = " ".join(str(a) for a in action_items)
        if not answer:
            return None

        return {
            "question": question,
            "contexts": contexts,
            "answer": str(answer),
            "ground_truth": None,  # needs human review before this can be promoted
            "source_run_id": run.id,
        }
    except (KeyError, TypeError, AttributeError):
        return None


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

    curated_questions = set()
    if CURATED_PATH.exists():
        curated = json.loads(CURATED_PATH.read_text())
        curated_questions = {str(ex.get("question", "")).strip().lower() for ex in curated}

    existing_candidates = []
    existing_questions = set()
    if CANDIDATES_PATH.exists():
        existing_candidates = json.loads(CANDIDATES_PATH.read_text())
        existing_questions = {str(ex.get("question", "")).strip().lower() for ex in existing_candidates}

    new_candidates = []
    for run in runs:
        sample = _extract_sample(run)
        if sample is None:
            continue
        key = sample["question"].strip().lower()
        if key in curated_questions or key in existing_questions:
            continue
        existing_questions.add(key)
        new_candidates.append(sample)

    print(f"Scanned {len(runs)} approved run(s) -> {len(new_candidates)} new candidate(s) "
          f"(skipped: already curated, missing RAG context, or duplicate).")

    if dry_run:
        print(json.dumps(new_candidates, indent=2))
        return

    if not new_candidates:
        print("Nothing new to write.")
        return

    all_candidates = existing_candidates + new_candidates
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(json.dumps(all_candidates, indent=2))
    print(f"Wrote {len(all_candidates)} total candidate(s) -> {CANDIDATES_PATH}")
    print("Review each entry, fill in ground_truth, then move it into "
          f"{CURATED_PATH.name} by hand — candidates are never auto-merged.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    limit = DEFAULT_LIMIT
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])
    build(limit=limit, dry_run=dry_run)

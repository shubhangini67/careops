"""Seed hospital policy/SOP vectors into Qdrant for CareOps Policy RAG."""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "apps", "api", ".env"))

from app.infrastructure.vector.qdrant_client import get_qdrant_client
from app.infrastructure.vector.embedding_service import EmbeddingService
from app.infrastructure.vector.memory_service import MemoryService

DEMO_ORG_ID = 1

POLICIES = [
    ("POLICY-001", "Emergency surge: when ED occupancy exceeds 85%, activate internal escalation and defer elective transfers."),
    ("POLICY-002", "ICU bed management: maintain one buffer bed where possible; escalate to bed management if occupancy exceeds 90%."),
    ("POLICY-003", "Staffing ratios: minimum nurse-to-bed ratio 1:6 on general wards during peak hours."),
    ("POLICY-004", "Supply reorder: critical PPE and respiratory supplies require human approval before procurement above threshold."),
    ("POLICY-005", "Patient privacy: operational dashboards must show department aggregates only — no PHI on shared screens."),
    ("POLICY-006", "OPD wait times: if average wait exceeds 45 minutes, open overflow clinic slots and notify charge nurse."),
    ("POLICY-007", "Safety incidents: moderate or high severity incidents require supervisor review within 4 hours."),
    ("POLICY-008", "After-hours escalation: contact on-call operations lead when three departments simultaneously exceed 80% occupancy."),
    ("POLICY-009", "CareOps disclaimer: the platform provides operational planning only — never diagnosis, treatment, or medication advice."),
    ("POLICY-010", "Forecast review: capacity forecasts for 24–48 hours must be validated against staffing rosters before shift changes."),
]

qdrant = get_qdrant_client()
embedder = EmbeddingService()
memory = MemoryService(qdrant, embedder)

print("Seeding hospital policies into Qdrant...")
removed = memory.purge_policy_vectors(DEMO_ORG_ID)
print(f"  Purged {removed} existing policy vectors for org {DEMO_ORG_ID}")

for policy_id, text in POLICIES:
    memory.store_sop(text, org_id=DEMO_ORG_ID, metadata={"policy_id": policy_id, "domain": "hospital_operations"})
    print(f"  {policy_id}")
    time.sleep(0.65)  # Gemini free-tier embed_content quota is 100 req/min

counts = memory.collection_counts()
print(f"Seeded {len(POLICIES)} hospital policies.")
print(f"Collection counts: {counts}")

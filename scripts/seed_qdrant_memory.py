import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'apps', 'api')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'apps', 'api', '.env'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.vector.qdrant_client import get_qdrant_client
from app.infrastructure.vector.embedding_service import EmbeddingService
from app.infrastructure.vector.memory_service import MemoryService
from app.infrastructure.db.models import Feedback

# ── Setup ──────────────────────────────────────────────
DEMO_ORG_ID  = 1   # matches seed_demo_data.py's DEMO_ORG_ID
DATABASE_URL = "postgresql://careops:careopspass@localhost:5432/careops"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

qdrant   = get_qdrant_client()
embedder = EmbeddingService()
memory   = MemoryService(qdrant, embedder)

print("Seeding Qdrant vector memory (CareOps hospital SOPs)...")

legacy_removed = memory.purge_legacy_restaurant_vectors()
if any(legacy_removed.values()):
    print(f"  Purged legacy restaurant/Swiggy vectors: {legacy_removed}")

org_removed = memory.purge_org_memory(DEMO_ORG_ID)
print(f"  Purged org {DEMO_ORG_ID} vectors: {org_removed}")

# ── 1. SOP rules ───────────────────────────────────────
sop_rules = [
    # ── Capacity management ──
    "Maximum ED holding capacity is 70 patients at any time before overflow protocol activates.",
    "When bed occupancy exceeds 90%, close elective admissions and switch to surge waitlist only.",
    "When Friday confirmed ED appointments exceed 13 parties, activate triage waitlist immediately.",
    "Elective slots for a Friday surge must be closed no later than 48 hours before service if near capacity.",
    "Walk-in ED buffer must not exceed 8 patients on peak Friday or Saturday evenings.",
    "Friday and Saturday evenings are peak ED periods. Minimum 3 charge nurses required from 6pm to 11pm.",

    # ── Emergency department operations ──
    "ED triage assessment time must not exceed 20 minutes during peak surge hours.",
    "Pre-stage overflow beds for top 5 ED service lines by 5pm on Friday evenings.",
    "On Fridays with 14 or more confirmed appointments, stage extra IV saline and PPE by 4:30pm.",
    "Critical supplies must be checked for expiry before every ED shift.",
    "Surgical gloves and N95 respirators must be verified before every surge shift.",

    # ── Inventory management ──
    "Reorder supplies when stock falls below the defined reorder threshold.",
    "Perishable clinical items with spoilage risk must be checked daily.",
    "IV saline bags and wound dressings must be stocked sufficiently for ED surge — minimum 80 units.",
    "Examination gloves must be lot-checked before every service. Expired stock must be discarded.",
    "Post-ED surge inventory check must be completed by 10am Saturday.",
    "Emergency reorders for critical supplies must be placed within 24 hours of threshold breach.",
    "Monthly supply audit must be conducted on the first Monday of each month.",

    # ── Patient experience ──
    "All patient complaints must be acknowledged within 5 minutes of being raised.",
    "Waiting time for confirmed appointments must not exceed 10 minutes.",
    "Exam rooms must be cleaned and reset within 5 minutes of patient discharge.",
    "Staff must remain professional and courteous at all times when handling complaints.",
    "Positive feedback must be shared with the care team at the next pre-shift briefing.",

    # ── Transfers and discharge ──
    "Step-down transfers must be initiated within 30 minutes of ICU clearance.",
    "Delayed discharge complaints must trigger a review of bed management workflow.",
    "If more than 3 discharge communication complaints are received in a single day, escalate to charge nurse.",

    # ── ED surge protocol ──
    "Friday evening ED surge is defined as 7pm to 10pm. All hands on deck policy applies.",
    "During ED surge, a dedicated triage coordinator must be stationed at the front desk.",
    "Pre-surge briefing must be conducted at 5:30pm every Friday.",
    "Standard Friday prep: 80 IV saline units by 5pm, overflow beds staged, 2 extra ED nurses from 6pm.",

    # ── Weekend operations ──
    "Weekend clinic service (12pm–3pm): ensure pharmacy and diagnostics stocks are doubled.",
    "Saturday service debrief must be conducted at 10pm to flag Sunday prep needs.",
    "Weekend walk-in demand typically adds 15–20% to appointment-based volume estimates.",
    "Post-peak-Friday Sundays should be treated as moderate-high demand days for supply purposes.",

    # ── OPD peak ──
    "OPD clinic rooms must be prepped and ready by 11:30am daily.",
    "OPD peak service (12pm–3pm) requires minimum 2 nurses and 1 front-desk coordinator.",
    "Corporate health screening bookings must be confirmed with a named point of contact.",
    "When OPD appointments exceed 7 parties, add 1 additional nurse.",

    # ── ICU capacity and special events ──
    "Holiday Mondays must be treated as Saturday-equivalent for staffing and supply purposes.",
    "When external events (outbreaks, mass gatherings) are nearby, elevate demand forecast by 15–20%.",
    "For all high-demand planning windows, begin prep at least 72 hours in advance.",
    "Start-of-month Mondays should be monitored as potential mini-surge spikes.",
]

print(f"\n  Seeding {len(sop_rules)} SOP rules...")
for i, rule in enumerate(sop_rules):
    memory.store_sop(
        text=rule,
        org_id=DEMO_ORG_ID,
        metadata={"rule_index": i, "category": "operational_sop"}
    )
    print(f"    SOP {i+1:02d}: {rule[:70]}...")
    time.sleep(0.65)  # Gemini free-tier embed_content quota is 100 req/min

# ── 2. Seed complaints from Postgres into Qdrant ───────
print(f"\n  Seeding complaints from Postgres...")
feedbacks = session.query(Feedback).all()
complaint_count = 0

for feedback in feedbacks:
    memory.store_complaint(
        text=feedback.raw_text,
        org_id=DEMO_ORG_ID,
        metadata={
            "feedback_id": feedback.id,
            "sentiment":   feedback.sentiment.value if feedback.sentiment else None,
            "source":      feedback.source.value if feedback.source else None,
        }
    )
    complaint_count += 1
    print(f"    Feedback {feedback.id}: {feedback.raw_text[:65]}...")
    time.sleep(0.65)  # Gemini free-tier embed_content quota is 100 req/min

session.close()

print(f"\nQdrant memory seeded successfully.")
counts = memory.collection_counts()
print(f"  {len(sop_rules)} SOP rules -> sop_memory collection")
print(f"  {complaint_count} feedback entries -> complaint_memory collection")
print(f"  Collection counts: {counts}")

"""Seed synthetic hospital operations data for CareOps AI."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.models import (
    Appointment,
    BedCapacity,
    Department,
    SafetyIncident,
    SentimentType,
    StaffRole,
    StaffShift,
    SupplyItem,
)

DATABASE_URL = "postgresql://careops:careopspass@localhost:5432/careops"
DEMO_ORG_ID = 1
NOW = datetime.utcnow()

DEPARTMENTS = [
    ("Emergency", "emergency", 30),
    ("General Medicine OPD", "general-medicine-opd", 0),
    ("ICU", "icu", 24),
    ("General Ward", "general-ward", 80),
]

SUPPLIES = [
    ("Normal Saline IV Bags", "iv_fluids", "units", 120, 40, False),
    ("Surgical Gloves (L)", "ppe", "boxes", 18, 25, True),
    ("Oxygen Cylinder Regulators", "respiratory", "units", 6, 8, True),
    ("Syringes 5ml", "consumables", "packs", 90, 30, False),
    ("Bandages Sterile", "wound_care", "packs", 12, 20, True),
    ("Hand Sanitizer 500ml", "hygiene", "bottles", 45, 15, False),
]

POLICIES = [
    ("POLICY-001", "Emergency surge: when ED occupancy exceeds 85%, activate internal escalation and defer elective transfers."),
    ("POLICY-002", "ICU bed management: maintain one buffer bed where possible; escalate to bed management if occupancy exceeds 90%."),
    ("POLICY-003", "Staffing ratios: minimum nurse-to-bed ratio 1:6 on general wards during peak hours."),
    ("POLICY-004", "Supply reorder: critical PPE and respiratory supplies require human approval before procurement above threshold."),
    ("POLICY-005", "Patient privacy: operational dashboards must show department aggregates only — no PHI on shared screens."),
    ("POLICY-006", "OPD wait times: if average wait exceeds 45 minutes, open overflow clinic slots and notify charge nurse."),
    ("POLICY-007", "Safety incidents: moderate or high severity incidents require supervisor review within 4 hours."),
    ("POLICY-008", "After-hours escalation: contact on-call operations lead when three departments simultaneously exceed 80% occupancy."),
]

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

print("Seeding CareOps hospital data...")

for table in (SafetyIncident, Appointment, StaffShift, BedCapacity, SupplyItem, Department):
    session.query(table).delete()
session.commit()

dept_map = {}
for name, slug, beds in DEPARTMENTS:
    d = Department(org_id=DEMO_ORG_ID, name=name, slug=slug, bed_limit=beds or 0)
    session.add(d)
    session.flush()
    dept_map[slug] = d
    if beds:
        occupied = int(beds * 0.82) if slug == "icu" else int(beds * 0.71)
        session.add(BedCapacity(org_id=DEMO_ORG_ID, department_id=d.id, total_beds=beds, occupied_beds=occupied))

for name, cat, unit, qty, threshold, critical in SUPPLIES:
    session.add(
        SupplyItem(
            org_id=DEMO_ORG_ID,
            name=name,
            category=cat,
            unit=unit,
            quantity_on_hand=qty,
            reorder_threshold=threshold,
            is_critical=critical,
        )
    )

for i, (slug, _) in enumerate([(s, s) for s in dept_map]):
    dept = dept_map[["emergency", "general-medicine-opd", "icu", "general-ward"][i % 4]]
    session.add(
        StaffShift(
            org_id=DEMO_ORG_ID,
            department_id=dept.id,
            role=StaffRole.nurses if i % 2 == 0 else StaffRole.doctors,
            headcount=4 + (i % 3),
            shift_start=NOW,
            shift_end=NOW + timedelta(hours=8),
        )
    )

for day in range(1, 8):
    for slug in dept_map:
        session.add(
            Appointment(
                org_id=DEMO_ORG_ID,
                department_id=dept_map[slug].id,
                scheduled_at=NOW + timedelta(hours=6 * day),
                status="booked",
                encounter_type="outpatient" if "opd" in slug else "inpatient",
            )
        )

incidents = [
    ("Emergency", "medium", "wait_time", "Synthetic incident: ED triage wait exceeded target during evening surge.", SentimentType.negative),
    ("ICU", "low", "equipment", "Synthetic incident: ventilator alarm checklist delayed on shift handoff.", SentimentType.neutral),
    ("General Ward", "low", "communication", "Synthetic feedback: discharge instructions clarity rated below target.", SentimentType.negative),
]
for dept, sev, cat, summary, sent in incidents:
    session.add(
        SafetyIncident(
            org_id=DEMO_ORG_ID,
            department=dept,
            severity=sev,
            category=cat,
            summary=summary,
            sentiment=sent,
        )
    )

session.commit()
print(f"  Departments: {len(DEPARTMENTS)}")
print(f"  Supplies: {len(SUPPLIES)}")
print(f"  Policies (see seed_hospital_policies.py): {len(POLICIES)}")
print("CareOps hospital relational seed complete.")

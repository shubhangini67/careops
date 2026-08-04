"""Local healthcare MCP tool implementations (replaces Swiggy MCP)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.db import models as db
from app.infrastructure.healthcare.fhir_store import get_fhir_store
from app.infrastructure.vector.memory_service import MemoryService


class HealthcareMCPTools:
    """Deterministic local tools backed by PostgreSQL + synthetic FHIR fixtures."""

    def __init__(self, db_session: Session, memory: MemoryService | None = None):
        self.db = db_session
        self.memory = memory
        self.fhir = get_fhir_store()

    def get_capacity_snapshot(self, org_id: int | None = None) -> dict[str, Any]:
        beds = self.db.query(db.BedCapacity).all()
        if org_id:
            beds = [b for b in beds if b.org_id == org_id]
        departments = []
        total_beds = occupied = 0
        for b in beds:
            total_beds += b.total_beds
            occupied += b.occupied_beds
            pct = round(100 * b.occupied_beds / b.total_beds, 1) if b.total_beds else 0
            departments.append({
                "department": b.department.name if b.department else b.department_id,
                "total_beds": b.total_beds,
                "occupied_beds": b.occupied_beds,
                "occupancy_pct": pct,
            })
        return {
            "as_of": datetime.utcnow().isoformat(),
            "departments": departments,
            "facility_occupancy_pct": round(100 * occupied / total_beds, 1) if total_beds else 0,
        }

    def get_department_workload(self, department: str | None = None) -> dict[str, Any]:
        q = self.db.query(db.Appointment)
        appts = q.all()
        now = datetime.utcnow()
        horizon = now + timedelta(hours=48)
        buckets: dict[str, int] = {}
        for a in appts:
            dept_name = a.department.name if a.department else "Unknown"
            if department and dept_name.lower() != department.lower():
                continue
            if a.scheduled_at and now <= a.scheduled_at <= horizon:
                buckets[dept_name] = buckets.get(dept_name, 0) + 1
        return {
            "window_hours": 48,
            "appointments_by_department": [
                {"department": k, "count": v} for k, v in sorted(buckets.items())
            ],
        }

    def get_staffing_summary(self, org_id: int | None = None) -> dict[str, Any]:
        shifts = self.db.query(db.StaffShift).all()
        if org_id:
            shifts = [s for s in shifts if s.org_id == org_id]
        summary: dict[str, dict[str, int]] = {}
        for s in shifts:
            dept = s.department.name if s.department else "Unknown"
            role_bucket = summary.setdefault(dept, {"doctors": 0, "nurses": 0, "support": 0})
            role_bucket[s.role.value] = role_bucket.get(s.role.value, 0) + s.headcount
        return {"departments": [{"department": d, **roles} for d, roles in sorted(summary.items())]}

    def get_supply_shortages(self) -> dict[str, Any]:
        items = self.db.query(db.SupplyItem).all()
        shortages = []
        for item in items:
            if item.quantity_on_hand <= item.reorder_threshold:
                shortages.append({
                    "supply": item.name,
                    "category": item.category,
                    "on_hand": item.quantity_on_hand,
                    "threshold": item.reorder_threshold,
                    "unit": item.unit,
                })
        return {"shortages": shortages, "count": len(shortages)}

    def get_fhir_encounter_summary(self) -> dict[str, Any]:
        return self.fhir.encounter_summary()

    def search_hospital_policy(self, query: str, org_id: int = 1, top_k: int = 3) -> dict[str, Any]:
        if not self.memory:
            return {"results": [], "citations": []}
        hits = self.memory.retrieve_relevant_sops(query, org_id=org_id, top_k=top_k)
        results = []
        citations = []
        for i, hit in enumerate(hits, start=1):
            text = hit.get("text", "")
            policy_id = (hit.get("metadata") or {}).get("policy_id", f"POLICY-{i}")
            results.append({"policy_id": policy_id, "excerpt": text[:400], "score": hit.get("score")})
            citations.append({"id": policy_id, "source": "hospital_policy_index", "excerpt": text[:200]})
        return {"query": query, "results": results, "citations": citations}

    def create_review_action(
        self,
        org_id: int,
        title: str,
        description: str,
        category: str = "operations_review",
        confidence: float = 0.5,
        tier: db.ActionTier | None = None,
    ) -> dict[str, Any]:
        resolved_tier = tier or (
            db.ActionTier.recommendation
            if confidence >= 0.75
            else db.ActionTier.approve_required
        )
        action = db.ActionQueue(
            org_id=org_id,
            category=category,
            tier=resolved_tier,
            status=db.ActionStatus.pending,
            title=title,
            payload={"description": description, "confidence": confidence, "requires_human_review": confidence < 0.75},
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)
        return {
            "action_id": action.id,
            "tier": action.tier.value,
            "status": action.status.value,
            "requires_human_review": confidence < 0.75,
        }

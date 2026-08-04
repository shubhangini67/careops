"""Load synthetic FHIR fixtures for local healthcare MCP tools."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_FHIR_DIR = Path(__file__).resolve().parents[5] / "data" / "fhir"


@lru_cache(maxsize=1)
def _load(name: str) -> list[dict[str, Any]]:
    path = _FHIR_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


class FHIRStore:
    """Read-only access to de-identified synthetic FHIR resources."""

    def patients(self) -> list[dict[str, Any]]:
        return _load("patients.json")

    def encounters(self) -> list[dict[str, Any]]:
        return _load("encounters.json")

    def appointments(self) -> list[dict[str, Any]]:
        return _load("appointments.json")

    def observations(self) -> list[dict[str, Any]]:
        return _load("observations.json")

    def encounter_summary(self) -> dict[str, Any]:
        """Department-level encounter counts — no patient identifiers."""
        by_dept: dict[str, dict[str, int]] = {}
        for enc in self.encounters():
            dept = (enc.get("serviceProvider") or {}).get("display") or "Unknown"
            bucket = by_dept.setdefault(dept, {"active": 0, "planned": 0, "finished": 0})
            status = enc.get("status", "unknown")
            if status in ("in-progress", "arrived"):
                bucket["active"] += 1
            elif status == "planned":
                bucket["planned"] += 1
            elif status == "finished":
                bucket["finished"] += 1
        return {
            "departments": [
                {"department": dept, **counts}
                for dept, counts in sorted(by_dept.items())
            ],
            "total_encounters": len(self.encounters()),
            "note": "Synthetic aggregate — no patient identifiers exposed.",
        }


def get_fhir_store() -> FHIRStore:
    return FHIRStore()

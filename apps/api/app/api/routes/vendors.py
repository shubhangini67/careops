"""vendors.py — real, org-scoped offline (WhatsApp/phone) vendor directory.

Backs the "Message Your Vendors" picker: a restaurant genuinely works with a
handful of real vendors by category (produce, dairy, dough, general grocery),
not one auto-picked one -- the owner should see who's actually on file and
what each one supplies before choosing who to message. Instamart (the only
online "vendor") is deliberately excluded here -- it already has its own
dedicated live-price-check flow, not a WhatsApp draft.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.infrastructure.db.models import Vendor, VendorPriceQuote

router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorSummary(BaseModel):
    id: int
    name: str
    category: str | None = None
    # Distinct ingredients this vendor has a real price quote on file for --
    # "what they deal in," derived from real data, never a fabricated list.
    supplies: list[str] = []


@router.get("", response_model=list[VendorSummary])
def list_vendors(
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VendorSummary]:
    org_id = current["org_id"]
    vendors = (
        db.query(Vendor)
        .filter(Vendor.org_id == org_id, Vendor.is_online.is_(False))
        .order_by(Vendor.id.asc())
        .all()
    )
    quotes = (
        db.query(VendorPriceQuote)
        .join(Vendor, Vendor.id == VendorPriceQuote.vendor_id)
        .filter(Vendor.org_id == org_id, Vendor.is_online.is_(False))
        .all()
    )
    supplies_by_vendor: dict[int, set[str]] = {}
    for q in quotes:
        supplies_by_vendor.setdefault(q.vendor_id, set()).add(q.ingredient)

    return [
        VendorSummary(
            id=v.id, name=v.name, category=v.category,
            supplies=sorted(supplies_by_vendor.get(v.id, set())),
        )
        for v in vendors
    ]

"""Vendor/supplier lookups. Instamart is just one vendor among several here --
local vendors reached by WhatsApp/phone are the common case for this restaurant
(confirmed 2026-07-08), not a fallback.
"""

from sqlalchemy.orm import Session

from app.infrastructure.db.models import Vendor, VendorPriceQuote


class VendorService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, vendor_id: int) -> Vendor | None:
        return self.db.query(Vendor).filter(Vendor.id == vendor_id).first()

    def list_vendors(self, org_id: int) -> list[Vendor]:
        return self.db.query(Vendor).filter(Vendor.org_id == org_id).order_by(Vendor.name).all()

    def cheapest_vendor_for_ingredient(self, org_id: int, ingredient: str) -> dict | None:
        """Cheapest VendorPriceQuote for `ingredient` among this org's vendors, or None
        if no vendor has quoted a price for it."""
        row = (
            self.db.query(VendorPriceQuote, Vendor)
            .join(Vendor, VendorPriceQuote.vendor_id == Vendor.id)
            .filter(Vendor.org_id == org_id, VendorPriceQuote.ingredient == ingredient)
            .order_by(VendorPriceQuote.price.asc())
            .first()
        )
        if row is None:
            return None
        quote, vendor = row
        return {"vendor_id": vendor.id, "vendor_name": vendor.name, "price": quote.price, "quoted_at": quote.quoted_at}

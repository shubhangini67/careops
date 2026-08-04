"""Unit tests for VendorService."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Vendor, VendorPriceQuote
from app.domain.services.vendor_service import VendorService


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    Vendor.__table__.create(bind=eng)
    VendorPriceQuote.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(VendorPriceQuote).delete()
        session.query(Vendor).delete()
        session.commit()


ORG_ID = 1


def _vendor(db, name, is_online=False, whatsapp_number=None, category=None):
    v = Vendor(org_id=ORG_ID, name=name, category=category, is_online=is_online, whatsapp_number=whatsapp_number)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _quote(db, vendor, ingredient, price):
    q = VendorPriceQuote(vendor_id=vendor.id, ingredient=ingredient, price=price)
    db.add(q)
    db.commit()


def test_list_vendors_filters_by_org_and_sorts_by_name(db):
    _vendor(db, "Ramesh Traders")
    _vendor(db, "Instamart", is_online=True)
    other_org = Vendor(org_id=2, name="Other Org Vendor", is_online=False)
    db.add(other_org)
    db.commit()

    service = VendorService(db)
    vendors = service.list_vendors(ORG_ID)

    assert [v.name for v in vendors] == ["Instamart", "Ramesh Traders"]


def test_get_returns_vendor_by_id(db):
    vendor = _vendor(db, "Ramesh Traders", whatsapp_number="+919876543210")
    service = VendorService(db)
    fetched = service.get(vendor.id)
    assert fetched is not None
    assert fetched.whatsapp_number == "+919876543210"


def test_get_returns_none_for_missing_vendor(db):
    service = VendorService(db)
    assert service.get(9999) is None


def test_cheapest_vendor_for_ingredient_returns_lowest_price(db):
    ramesh = _vendor(db, "Ramesh Traders")
    instamart = _vendor(db, "Instamart", is_online=True)
    _quote(db, ramesh, "Mozzarella Cheese", 380.0)
    _quote(db, instamart, "Mozzarella Cheese", 420.0)

    service = VendorService(db)
    result = service.cheapest_vendor_for_ingredient(ORG_ID, "Mozzarella Cheese")

    assert result is not None
    assert result["vendor_name"] == "Ramesh Traders"
    assert result["price"] == 380.0


def test_cheapest_vendor_for_ingredient_returns_none_when_no_quotes(db):
    service = VendorService(db)
    assert service.cheapest_vendor_for_ingredient(ORG_ID, "Fresh Basil") is None


def test_cheapest_vendor_for_ingredient_scoped_to_org(db):
    other_org_vendor = Vendor(org_id=2, name="Other Org Vendor", is_online=False)
    db.add(other_org_vendor)
    db.commit()
    db.refresh(other_org_vendor)
    _quote(db, other_org_vendor, "Mozzarella Cheese", 100.0)  # very cheap, but different org

    service = VendorService(db)
    result = service.cheapest_vendor_for_ingredient(ORG_ID, "Mozzarella Cheese")

    assert result is None

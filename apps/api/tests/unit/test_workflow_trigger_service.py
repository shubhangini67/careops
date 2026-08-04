"""Unit tests for WorkflowTriggerService -- the 2 built-in triggers that
auto-create Action Queue rows after a planning run finishes."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import ActionQueue, ActionStatus, ActionTier, Vendor, VendorPriceQuote
from app.domain.services.workflow_trigger_service import WorkflowTriggerService


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    ActionQueue.__table__.create(bind=eng)
    Vendor.__table__.create(bind=eng)
    VendorPriceQuote.__table__.create(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
        session.query(ActionQueue).delete()
        session.query(VendorPriceQuote).delete()
        session.query(Vendor).delete()
        session.commit()


ORG_ID = 1


def _mock_llm(result=None, side_effect=None):
    """No llm passed to WorkflowTriggerService means the deterministic
    template is always used -- most tests below don't need one. Only the
    LLM-drafting-specific tests construct one of these."""
    llm = MagicMock()
    if side_effect is not None:
        llm.complete_json = AsyncMock(side_effect=side_effect)
    else:
        llm.complete_json = AsyncMock(return_value=result)
    return llm


def _plan_with_shortages(*ingredients_with_severity, forecast_data=None):
    return {
        "recommendations": {
            "inventory": {
                "data": {
                    "shortage_alerts": [
                        {
                            "ingredient": name, "severity": severity,
                            "unit": "kg", "quantity_in_stock": 1.0,
                            "reorder_threshold": 1.5, "shortfall": 0.5,
                            "recommended_restock_qty": 0.5,
                        }
                        for name, severity in ingredients_with_severity
                    ]
                }
            },
            **({"forecast": {"data": forecast_data}} if forecast_data else {}),
        },
        "market_intel": {},
    }


def _plan_with_overstock(*ingredients_with_spoilage_risk):
    return {
        "recommendations": {
            "inventory": {
                "data": {
                    "overstock_alerts": [
                        {
                            "ingredient": name, "spoilage_risk": at_risk,
                            "unit": "kg", "quantity_in_stock": 12.0,
                            "reorder_threshold": 2.0, "excess": 6.0,
                        }
                        for name, at_risk in ingredients_with_spoilage_risk
                    ]
                }
            },
        },
        "market_intel": {},
    }


def _plan_with_market(tonight_busy, deals, slot_deals=None):
    # P6-A20: OccupancyEnricher exposes a count/summary, not a named-restaurant
    # list -- `deals` here is still passed as a list by callers for readability,
    # reduced to its count to match the anonymised market_intel shape.
    return {
        "recommendations": {},
        "market_intel": {
            "tonight_busy": tonight_busy,
            "dineout_deals_count": len(deals),
            "slot_deals_found": slot_deals or [],
        },
    }


# ── Trigger 1: critical shortages ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_critical_shortages_creates_restock_alert(db):
    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    assert len(created) == 1
    assert created[0].category == "restock_alert"
    assert "Mozzarella" in created[0].title


@pytest.mark.asyncio
async def test_one_critical_shortage_does_not_trigger(db):
    plan = _plan_with_shortages(("Mozzarella", "critical"))
    service = WorkflowTriggerService(db)
    assert await service.evaluate_and_queue(ORG_ID, plan) == []


@pytest.mark.asyncio
async def test_warning_severity_shortages_do_not_count(db):
    plan = _plan_with_shortages(("Mozzarella", "warning"), ("Basil", "warning"))
    service = WorkflowTriggerService(db)
    assert await service.evaluate_and_queue(ORG_ID, plan) == []


@pytest.mark.asyncio
async def test_repeated_run_does_not_duplicate_pending_restock_alert(db):
    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db)
    await service.evaluate_and_queue(ORG_ID, plan)
    second_run = await service.evaluate_and_queue(ORG_ID, plan)
    assert second_run == []


@pytest.mark.asyncio
async def test_restock_alert_payload_carries_full_shortage_detail(db):
    """P6-A31: Action Center's hero card + list need real per-ingredient
    numbers, not just names."""
    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    restock = next(a for a in created if a.category == "restock_alert")
    shortages = restock.payload["shortages"]
    assert len(shortages) == 2
    first = shortages[0]
    assert first["ingredient"] == "Mozzarella"
    assert first["quantity_in_stock"] == 1.0
    assert first["reorder_threshold"] == 1.5
    assert first["recommended_restock_qty"] == 0.5
    assert first["whatsapp_vendor"] is None  # no VendorPriceQuote seeded
    assert "usual minimum" in first["reason"]  # generic fallback reason, plain language


@pytest.mark.asyncio
async def test_restock_alert_never_picks_a_channel_both_stay_options(db):
    """The system doesn't decide Instamart vs. WhatsApp for the owner -- it
    surfaces both real options and lets them choose. Instamart is always
    checkable live (not something this trigger pre-fetches or gates on), so
    an online VendorPriceQuote shouldn't show up as a "suggested" pick here
    at all -- only the offline (WhatsApp) vendor is ever attached."""
    online = Vendor(org_id=ORG_ID, name="Instamart", category="general", is_online=True)
    db.add(online)
    db.flush()
    db.add(VendorPriceQuote(vendor_id=online.id, ingredient="Mozzarella", price=150.0))
    db.commit()

    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    restock = next(a for a in created if a.category == "restock_alert")
    mozzarella = next(s for s in restock.payload["shortages"] if s["ingredient"] == "Mozzarella")
    assert mozzarella["whatsapp_vendor"] is None
    assert not any(a.category == "whatsapp_vendor_order" for a in created)


@pytest.mark.asyncio
async def test_restock_alert_drafts_whatsapp_order_for_real_offline_vendor(db):
    """A real local (offline) vendor carrying the ingredient gets an
    approve-gated WhatsApp draft created alongside the restock alert, so the
    owner has a one-click way to message them -- not just a name shown."""
    vendor_a = Vendor(org_id=ORG_ID, name="Ramesh Traders", category="produce")
    vendor_b = Vendor(org_id=ORG_ID, name="Sharma Supplies", category="produce")
    db.add_all([vendor_a, vendor_b])
    db.flush()
    db.add_all([
        VendorPriceQuote(vendor_id=vendor_a.id, ingredient="Mozzarella", price=180.0),
        VendorPriceQuote(vendor_id=vendor_b.id, ingredient="Mozzarella", price=210.0),
    ])
    db.commit()

    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db)  # no llm -- exercises the deterministic template path
    created = await service.evaluate_and_queue(ORG_ID, plan)

    restock = next(a for a in created if a.category == "restock_alert")
    mozzarella = next(s for s in restock.payload["shortages"] if s["ingredient"] == "Mozzarella")
    assert mozzarella["whatsapp_vendor"] == "Ramesh Traders"  # cheapest offline quote wins

    draft = next(a for a in created if a.category == "whatsapp_vendor_order")
    assert draft.tier == ActionTier.approve_required
    assert draft.payload["vendor"] == "Ramesh Traders"
    assert draft.payload["ingredient"] == "Mozzarella"
    assert "Ramesh bhai" in draft.payload["message_draft"]


@pytest.mark.asyncio
async def test_whatsapp_draft_falls_back_to_any_offline_vendor_without_a_quote(db):
    """The WhatsApp option must never disappear just because this exact
    ingredient has no price history with this vendor -- an owner can message
    whoever they already order from about anything running low."""
    vendor = Vendor(org_id=ORG_ID, name="Green Valley Produce", category="produce")
    db.add(vendor)
    db.flush()
    # Deliberately no VendorPriceQuote for "Mozzarella" at all.
    db.commit()

    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    restock = next(a for a in created if a.category == "restock_alert")
    mozzarella = next(s for s in restock.payload["shortages"] if s["ingredient"] == "Mozzarella")
    assert mozzarella["whatsapp_vendor"] == "Green Valley Produce"
    draft = next(a for a in created if a.category == "whatsapp_vendor_order")
    assert draft.payload["vendor"] == "Green Valley Produce"


@pytest.mark.asyncio
async def test_whatsapp_draft_uses_llm_drafted_message_when_available(db):
    """When an LLM is configured and returns a valid draft, that draft is used
    instead of the canned template."""
    vendor = Vendor(org_id=ORG_ID, name="Ramesh Traders", category="produce")
    db.add(vendor)
    db.flush()
    db.add(VendorPriceQuote(vendor_id=vendor.id, ingredient="Mozzarella", price=180.0))
    db.commit()

    llm = _mock_llm(result={"message": "Ramesh bhai, cheese khatam ho gaya, kal 2kg bhej do please!"})
    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db, llm)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    draft = next(a for a in created if a.category == "whatsapp_vendor_order")
    assert draft.payload["message_draft"] == "Ramesh bhai, cheese khatam ho gaya, kal 2kg bhej do please!"
    llm.complete_json.assert_awaited()


@pytest.mark.asyncio
async def test_whatsapp_draft_falls_back_to_template_on_llm_error(db):
    """An LLM failure must never block the WhatsApp draft from being created
    -- it just falls back to the deterministic template."""
    vendor = Vendor(org_id=ORG_ID, name="Ramesh Traders", category="produce")
    db.add(vendor)
    db.flush()
    db.add(VendorPriceQuote(vendor_id=vendor.id, ingredient="Mozzarella", price=180.0))
    db.commit()

    llm = _mock_llm(side_effect=RuntimeError("provider down"))
    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db, llm)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    draft = next(a for a in created if a.category == "whatsapp_vendor_order")
    assert "Ramesh bhai" in draft.payload["message_draft"]  # deterministic template, not a crash


@pytest.mark.asyncio
async def test_whatsapp_draft_falls_back_to_template_on_malformed_llm_output(db):
    """A non-dict or empty-message LLM response is treated the same as a
    failure -- never send an empty or garbage draft."""
    vendor = Vendor(org_id=ORG_ID, name="Ramesh Traders", category="produce")
    db.add(vendor)
    db.flush()
    db.add(VendorPriceQuote(vendor_id=vendor.id, ingredient="Mozzarella", price=180.0))
    db.commit()

    llm = _mock_llm(result={"message": ""})
    plan = _plan_with_shortages(("Mozzarella", "critical"), ("Basil", "critical"))
    service = WorkflowTriggerService(db, llm)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    draft = next(a for a in created if a.category == "whatsapp_vendor_order")
    assert "Ramesh bhai" in draft.payload["message_draft"]


@pytest.mark.asyncio
async def test_restock_alert_reason_uses_real_forecast_adjustment(db):
    plan = _plan_with_shortages(
        ("Mozzarella", "critical"), ("Basil", "critical"),
        forecast_data={
            "adjustment_multiplier": 1.32,
            "adjustment_reasons": ["weather (rain): x1.3"],
        },
    )
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    shortages = created[0].payload["shortages"]
    assert all("32%" in s["reason"] and "higher" in s["reason"] for s in shortages)


# ── Message Your Vendors (owner-picked, on-demand) ───────────────────────────

@pytest.mark.asyncio
async def test_create_vendor_message_drafts_for_the_chosen_vendor(db):
    """The owner picking a vendor themselves (not the cheapest-quote auto-
    match) must still produce a real, approve-to-send WhatsApp draft."""
    vendor = Vendor(org_id=ORG_ID, name="Green Valley Produce", category="produce")
    db.add(vendor)
    db.flush()
    db.commit()

    service = WorkflowTriggerService(db)
    action = await service.create_vendor_message(
        ORG_ID, vendor.id,
        {"ingredient": "Fresh Basil", "unit": "kg", "quantity_in_stock": 1.0,
         "reorder_threshold": 3.0, "recommended_restock_qty": 5.0},
    )

    assert action.category == "whatsapp_vendor_order"
    assert action.status == ActionStatus.pending
    assert action.payload["vendor"] == "Green Valley Produce"
    assert action.payload["ingredient"] == "Fresh Basil"
    assert action.payload["message_draft"]


@pytest.mark.asyncio
async def test_create_vendor_message_unknown_vendor_raises(db):
    service = WorkflowTriggerService(db)
    with pytest.raises(ValueError):
        await service.create_vendor_message(ORG_ID, 9999, {"ingredient": "Fresh Basil"})


@pytest.mark.asyncio
async def test_create_vendor_message_scoped_to_org(db):
    """A vendor belonging to a different org must never be messageable."""
    other_org_vendor = Vendor(org_id=ORG_ID + 1, name="Someone Else's Vendor", category="produce")
    db.add(other_org_vendor)
    db.flush()
    db.commit()

    service = WorkflowTriggerService(db)
    with pytest.raises(ValueError):
        await service.create_vendor_message(ORG_ID, other_org_vendor.id, {"ingredient": "Fresh Basil"})


# ── Trigger 3: overstock + spoilage risk ─────────────────────────────────────

@pytest.mark.asyncio
async def test_overstock_with_spoilage_risk_creates_action(db):
    plan = _plan_with_overstock(("Fresh Basil", True))
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    assert len(created) == 1
    assert created[0].category == "overstock_alert"
    assert "Fresh Basil" in created[0].title
    assert "overstocked" in created[0].title


@pytest.mark.asyncio
async def test_overstock_without_spoilage_risk_does_not_trigger(db):
    """A shelf-stable item sitting above its usual stock level isn't
    urgent -- it's just extra inventory, not avoidable waste."""
    plan = _plan_with_overstock(("Canned Tomatoes", False))
    service = WorkflowTriggerService(db)
    assert await service.evaluate_and_queue(ORG_ID, plan) == []


@pytest.mark.asyncio
async def test_overstock_payload_carries_full_detail(db):
    plan = _plan_with_overstock(("Fresh Basil", True))
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    item = created[0].payload["overstock_items"][0]
    assert item["ingredient"] == "Fresh Basil"
    assert item["quantity_in_stock"] == 12.0
    assert item["reorder_threshold"] == 2.0
    assert item["excess"] == 6.0
    assert "spoilage-risk" in item["reason"]


@pytest.mark.asyncio
async def test_repeated_run_does_not_duplicate_pending_overstock_alert(db):
    plan = _plan_with_overstock(("Fresh Basil", True))
    service = WorkflowTriggerService(db)
    await service.evaluate_and_queue(ORG_ID, plan)
    second_run = await service.evaluate_and_queue(ORG_ID, plan)
    assert second_run == []


@pytest.mark.asyncio
async def test_multiple_overstock_items_named_in_title(db):
    plan = _plan_with_overstock(("Fresh Basil", True), ("Cream", True), ("Paneer", True), ("Mint", True))
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    title = created[0].category == "overstock_alert" and created[0].title
    assert "and 1 more" in title
    assert len(created[0].payload["ingredients"]) == 4


# ── Trigger 2: busy + competitor deals ───────────────────────────────────────

@pytest.mark.asyncio
async def test_busy_plus_two_deals_creates_pricing_review(db):
    plan = _plan_with_market(tonight_busy=True, deals=["deal1", "deal2"])
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)

    assert len(created) == 1
    assert created[0].category == "pricing_promo_review"


@pytest.mark.asyncio
async def test_busy_plus_one_deal_does_not_trigger(db):
    plan = _plan_with_market(tonight_busy=True, deals=["deal1"])
    service = WorkflowTriggerService(db)
    assert await service.evaluate_and_queue(ORG_ID, plan) == []


@pytest.mark.asyncio
async def test_two_deals_but_not_busy_does_not_trigger(db):
    plan = _plan_with_market(tonight_busy=False, deals=["deal1", "deal2"])
    service = WorkflowTriggerService(db)
    assert await service.evaluate_and_queue(ORG_ID, plan) == []


@pytest.mark.asyncio
async def test_slot_deals_and_competitor_deals_both_count_toward_threshold(db):
    plan = _plan_with_market(tonight_busy=True, deals=["deal1"], slot_deals=["slot1"])
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)
    assert len(created) == 1


@pytest.mark.asyncio
async def test_repeated_run_does_not_duplicate_pending_pricing_review(db):
    plan = _plan_with_market(tonight_busy=True, deals=["deal1", "deal2"])
    service = WorkflowTriggerService(db)
    await service.evaluate_and_queue(ORG_ID, plan)
    second_run = await service.evaluate_and_queue(ORG_ID, plan)
    assert second_run == []


# ── Both triggers at once ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_both_triggers_fire_independently(db):
    plan = {
        "recommendations": {
            "inventory": {"data": {"shortage_alerts": [
                {"ingredient": "Mozzarella", "severity": "critical"},
                {"ingredient": "Basil", "severity": "critical"},
            ]}}
        },
        "market_intel": {
            "tonight_busy": True,
            "dineout_deals_count": 2,
            "slot_deals_found": [],
        },
    }
    service = WorkflowTriggerService(db)
    created = await service.evaluate_and_queue(ORG_ID, plan)
    categories = {a.category for a in created}
    assert categories == {"restock_alert", "pricing_promo_review"}

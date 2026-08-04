"""
CareOps AI — demo data seed (v6, hospital operations)

Replaces restaurant menu/inventory/feedback with hospital service lines,
clinical supplies, patient safety incidents, and CareOps scenario IDs
(ed_surge, opd_peak, icu_capacity, supply_shortage).

Still uses Order/MenuItem/Inventory/Reservation tables for analytics
compatibility — "orders" represent billed encounters/service lines.
"""

import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")),
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.scenarios import list_scenarios
from app.infrastructure.db.models import (
    ActionQueue,
    ActionStatus,
    ActionTier,
    CriticVerdict,
    DecisionLog,
    Expense,
    ExpenseCategory,
    ExpenseRecurrence,
    Feedback,
    FeedbackSource,
    Inventory,
    MenuItem,
    Order,
    PlanningRun,
    Reservation,
    ReservationStatus,
    SentimentType,
    Vendor,
    VendorPriceQuote,
)

DATABASE_URL = "postgresql://careops:careopspass@localhost:5432/careops"
SEED_AS_OF   = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
HISTORY_DAYS = 161   # ~23 weeks of trailing history, ending today

SCENARIO_WEEKDAY = {s["id"]: s["default_weekday"] for s in list_scenarios()}  # Mon=0..Sun=6
FUTURE_OCCURRENCES = 10  # ~2.5 months of upcoming weekly targets per scenario


def fmt(d: datetime) -> str:
    return f"{d.strftime('%b')} {d.day}"


def recent_weekday_dates(anchor: datetime, weekday: int, n: int) -> list[datetime]:
    """n dates matching `weekday`, most recent strictly before/on anchor first,
    spaced a week apart, returned oldest-first."""
    delta = (anchor.weekday() - weekday) % 7
    if delta == 0:
        delta = 7
    most_recent = anchor - timedelta(days=delta)
    return [most_recent - timedelta(weeks=i) for i in range(n)][::-1]


def upcoming_weekday_dates(anchor: datetime, weekday: int, n: int) -> list[datetime]:
    """n future dates matching `weekday`, strictly after anchor, weekly cadence,
    soonest-first -- mirrors _next_matching_service_date in runs.py."""
    days_ahead = (weekday - anchor.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    first = anchor + timedelta(days=days_ahead)
    return [first + timedelta(weeks=i) for i in range(n)]


# ── Historical Friday peaks — last 9 Fridays before today ───────────────────
FRIDAY_PEAK_DATES  = recent_weekday_dates(SEED_AS_OF, weekday=4, n=9)
FRIDAY_PEAK_COUNTS = [138, 127, 108, 119, 131, 112, 122, 108, 115]
FRIDAY_PEAKS = dict(zip(FRIDAY_PEAK_DATES, FRIDAY_PEAK_COUNTS))

# ── Historical weekday-lunch peaks — alternating Tue/Wed over ~8 weeks ──────
_lunch_dates = sorted(
    recent_weekday_dates(SEED_AS_OF, weekday=1, n=8) + recent_weekday_dates(SEED_AS_OF, weekday=2, n=8)
)[-15:]
WEEKDAY_LUNCH_COUNTS = [48, 52, 44, 49, 46, 51, 43, 47, 41, 49, 43, 45, 38, 50, 44]
WEEKDAY_LUNCH_PEAKS  = dict(zip(_lunch_dates, WEEKDAY_LUNCH_COUNTS))

# ── Historical holiday-style spikes — three one-off dates in the trailing history
HOLIDAY_PEAK_DATES  = [
    SEED_AS_OF - timedelta(weeks=10, days=3),
    SEED_AS_OF - timedelta(weeks=6, days=1),
    SEED_AS_OF - timedelta(weeks=1, days=2),
]
HOLIDAY_PEAK_COUNTS = [88, 94, 105]
HOLIDAY_PEAKS = dict(zip(HOLIDAY_PEAK_DATES, HOLIDAY_PEAK_COUNTS))

# ── Future planning window — next 10 occurrences per scenario ──────────────
FUTURE_SCENARIO_TARGETS = {
    scenario_id: upcoming_weekday_dates(SEED_AS_OF, weekday, FUTURE_OCCURRENCES)
    for scenario_id, weekday in SCENARIO_WEEKDAY.items()
}

engine  = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()
# Seeded by today's date, not a fixed integer -- every "random" draw below
# (which items run short, which dishes are popular, which feedback text gets
# sampled, etc.) is deterministic within a single day, so a demo session
# doesn't shift under you mid-demo, but genuinely different from one day to
# the next instead of being frozen forever on the same 3 ingredients/3 dishes.
random.seed(SEED_AS_OF.strftime("%Y-%m-%d"))


# ── Hour distributions ───────────────────────────────────────────────────────

def hour_friday() -> int:
    return random.choices(
        [12, 13, 14, 17, 18, 19, 20, 21, 22],
        weights=[3,  4,  3,  4, 14, 20, 20, 16,  8],
    )[0]

def hour_weekend() -> int:
    return random.choices(
        [11, 12, 13, 14, 18, 19, 20, 21],
        weights=[4,  8,  9,  6,  8, 13, 14, 10],
    )[0]

def hour_weekday_lunch() -> int:
    return random.choices(
        [12, 13, 14, 15, 19, 20, 21],
        weights=[22, 30, 18,  8,  6,  9,  7],
    )[0]

def hour_holiday() -> int:
    return random.choices(
        [12, 13, 17, 18, 19, 20, 21, 22],
        weights=[5,  4,  6, 14, 20, 22, 16,  8],
    )[0]

def hour_generic_weekday() -> int:
    return random.choices(
        [12, 13, 14, 19, 20, 21],
        weights=[15, 18, 10, 20, 22, 15],
    )[0]


print("Seeding CareOps v6 demo data (hospital operations)...")
print(f"  As-of : {SEED_AS_OF.date()} | History: {HISTORY_DAYS} days")

# ── Clear ────────────────────────────────────────────────────────────────────
session.query(DecisionLog).delete()
session.query(PlanningRun).delete()
session.query(Feedback).delete()
session.query(Order).delete()
session.query(Reservation).delete()
session.query(Inventory).delete()
session.query(MenuItem).delete()
session.query(Expense).delete()
session.query(ActionQueue).delete()
session.query(VendorPriceQuote).delete()
session.query(Vendor).delete()
session.commit()
print("  Cleared existing data")


# ── 1. Service lines (mapped to MenuItem for encounter analytics) ─────────────
menu_items = [
    MenuItem(name="ED Triage Level 3",           category="emergency",   price=850.0,  cost_price=280.0, is_available=True),
    MenuItem(name="Trauma Assessment",           category="emergency",   price=1200.0, cost_price=420.0, is_available=True),
    MenuItem(name="Emergency Observation",       category="emergency",   price=650.0,  cost_price=210.0, is_available=True),
    MenuItem(name="Chest Pain Protocol",         category="emergency",   price=980.0,  cost_price=340.0, is_available=True),
    MenuItem(name="General Surgery Consult",     category="surgery",     price=750.0,  cost_price=260.0, is_available=True),
    MenuItem(name="Minor Procedure Pack",        category="surgery",     price=1100.0, cost_price=390.0, is_available=True),
    MenuItem(name="Orthopedic Consult",          category="surgery",     price=820.0,  cost_price=290.0, is_available=True),
    MenuItem(name="Internal Medicine Follow-up", category="outpatient",  price=450.0,  cost_price=135.0, is_available=True),
    MenuItem(name="Cardiology OPD Visit",        category="outpatient",  price=520.0,  cost_price=160.0, is_available=True),
    MenuItem(name="Pediatrics Consult",          category="outpatient",  price=480.0,  cost_price=145.0, is_available=True),
    MenuItem(name="Dermatology OPD",             category="outpatient",  price=410.0,  cost_price=120.0, is_available=True),
    MenuItem(name="CT Scan Chest",               category="diagnostics", price=3200.0, cost_price=980.0, is_available=True),
    MenuItem(name="Laboratory Panel",            category="diagnostics", price=890.0,  cost_price=260.0, is_available=True),
    MenuItem(name="X-Ray Series",                category="diagnostics", price=650.0,  cost_price=190.0, is_available=True),
    MenuItem(name="Ultrasound Abdomen",          category="diagnostics", price=1100.0, cost_price=330.0, is_available=True),
    MenuItem(name="MRI Brain",                   category="diagnostics", price=4500.0, cost_price=1400.0, is_available=True),
    MenuItem(name="ICU Bed Day",                 category="inpatient",   price=8500.0, cost_price=3200.0, is_available=True),
    MenuItem(name="General Ward Bed Day",        category="inpatient",   price=4200.0, cost_price=1550.0, is_available=True),
    MenuItem(name="IV Antibiotic Course",        category="pharmacy",    price=1200.0, cost_price=380.0, is_available=True),
    MenuItem(name="Pain Management Protocol",    category="pharmacy",    price=680.0,  cost_price=210.0, is_available=True),
    MenuItem(name="Insulin Management",          category="pharmacy",    price=540.0,  cost_price=165.0, is_available=True),
    MenuItem(name="Physiotherapy Session",       category="rehab",       price=350.0,  cost_price=95.0,  is_available=True),
    MenuItem(name="Discharge Planning Review",   category="rehab",       price=280.0,  cost_price=75.0,  is_available=True),
    MenuItem(name="Nutrition Consult",           category="rehab",       price=320.0,  cost_price=88.0,  is_available=True),
    MenuItem(name="Pre-op Assessment",           category="surgery",     price=590.0,  cost_price=175.0, is_available=True),
    MenuItem(name="Post-op Follow-up",           category="surgery",     price=470.0,  cost_price=140.0, is_available=True),
    MenuItem(name="Telehealth Consult",          category="outpatient",  price=290.0,  cost_price=65.0,  is_available=True),
]
session.add_all(menu_items)
session.commit()
print(f"  Added {len(menu_items)} service lines")


# ── 2. Inventory — realistic mix, 1-4 of 18 randomly low each seed day ──────
# Thresholds/units/spoilage-risk are fixed business facts (how much of X do we
# actually need before it's a problem), but WHICH items are currently low and
# HOW MUCH stock is on hand are randomized per day (seeded by date above) --
# previously this was always the same 3 items (Mozzarella/Fresh Basil/Garlic)
# at the same literal quantities, every single day, forever.
INVENTORY_BASE = [
    ("IV Saline Bags",        "units",  40.0, True),
    ("Surgical Gloves",       "boxes",  25.0, True),
    ("N95 Respirators",       "boxes",  20.0, True),
    ("Sterile Syringes",      "packs",  30.0, True),
    ("Wound Dressings",       "packs",  20.0, True),
    ("Hand Sanitizer",        "bottles", 15.0, False),
    ("Oxygen Cannulas",       "units",  8.0,  True),
    ("Ventilator Circuits",   "units",  6.0,  True),
    ("Normal Saline 500ml",   "units",  35.0, False),
    ("Surgical Masks",        "boxes",  30.0, False),
    ("Examination Gloves",    "boxes",  25.0, True),
    ("Bandages Sterile",      "packs",  20.0, True),
    ("Antiseptic Solution",   "litres", 10.0, False),
    ("Glucose Test Strips",   "packs",  12.0, False),
    ("Urinary Catheters",     "units",  15.0, True),
    ("IV Administration Sets","units",  18.0, True),
    ("Pulse Oximeter Probes", "units",  8.0,  True),
    ("Isolation Gowns",       "units",  40.0, True),
]

n_low = random.randint(1, 4)
low_positions = set(random.sample(range(len(INVENTORY_BASE)), n_low))

inventory_items = []
low_ingredients_seeded = []        # for dynamic decision-log/RAG memory below
comfortable_ingredients_seeded = []
for idx, (name, unit, threshold, spoilage) in enumerate(INVENTORY_BASE):
    if idx in low_positions:
        qty = round(threshold * random.uniform(0.15, 0.85), 2)
        low_ingredients_seeded.append((name, unit, qty, threshold))
    else:
        qty = round(threshold * random.uniform(1.3, 3.2), 2)
        comfortable_ingredients_seeded.append((name, unit, qty, threshold))
    inventory_items.append(Inventory(
        ingredient_name=name, unit=unit,
        quantity_in_stock=qty, reorder_threshold=threshold, spoilage_risk=spoilage,
    ))

session.add_all(inventory_items)
session.commit()
print(f"  Added {len(inventory_items)} inventory items ({n_low} below threshold: "
      f"{', '.join(n for n, *_ in low_ingredients_seeded)})")


# ── 3. Reservations ───────────────────────────────────────────────────────────
ALL_GUEST_NAMES = [
    "Priya Sharma",  "Rohan Mehta",    "Ananya Singh",  "Arjun Patel",
    "Sneha Iyer",    "Vikram Nair",    "Pooja Desai",   "Karan Malhotra",
    "Isha Joshi",    "Dev Kapoor",     "Riya Verma",    "Aditya Rao",
    "Meera Shah",    "Kabir Sethi",    "Naina Kapoor",  "Sahil Bhatia",
    "Tanya Gupta",   "Rahul Sharma",   "Divya Menon",   "Nikhil Jain",
    "Sanya Bose",    "Aman Khanna",    "Kavya Pillai",  "Rohit Shetty",
]

reservations = []
base_date = SEED_AS_OF - timedelta(days=HISTORY_DAYS)

for day_offset in range(HISTORY_DAYS + 1):
    current_date = base_date + timedelta(days=day_offset)
    d = current_date.date()
    is_friday  = current_date.weekday() == 4
    is_weekend = current_date.weekday() in [5, 6]
    is_weekday_lunch_peak = d in {dt.date() for dt in WEEKDAY_LUNCH_PEAKS}
    is_holiday = d in {dt.date() for dt in HOLIDAY_PEAKS if HOLIDAY_PEAKS[dt] > 0}

    if   d in {dt.date() for dt in FRIDAY_PEAKS}:   count = random.randint(14, 18)
    elif is_holiday:                                  count = random.randint(14, 18)
    elif is_weekday_lunch_peak:                       count = random.randint(9, 12)
    elif is_friday:                                   count = random.randint(10, 14)
    elif is_weekend:                                  count = random.randint(6, 10)
    else:                                             count = random.randint(3, 6)

    for _ in range(count):
        if is_friday or is_weekend or is_holiday:
            hour = random.choice([13, 18, 19, 20, 21])
        elif is_weekday_lunch_peak:
            hour = random.choice([12, 12, 13, 13, 14, 19, 20])
        else:
            hour = random.choice([13, 19, 20])

        status = random.choices(
            [ReservationStatus.confirmed, ReservationStatus.completed,
             ReservationStatus.cancelled,  ReservationStatus.waitlist],
            weights=[15, 65, 10, 10],
        )[0]

        reservations.append(Reservation(
            guest_name   = random.choice(ALL_GUEST_NAMES),
            guest_count  = random.randint(2, 8) if is_holiday else random.randint(2, 6),
            reserved_at  = current_date.replace(hour=hour, minute=random.choice([0, 15, 30, 45])),
            status       = status,
            table_number = random.randint(1, 15),
            notes        = random.choice([
                None, None, None, None,
                "Wheelchair access needed", "Follow-up after discharge",
                "Interpreter required", "Post-op review", "Family caregiver accompanying",
                "Diabetic — fasting labs", "Cardiology referral", "Pediatric guardian present",
            ]),
        ))


# ── Future reservations ──────────────────────────────────────────────────────
FUTURE_NAMES = [
    ("Priya Sharma", 4),   ("Rohan Mehta", 2),    ("Ananya Singh", 6),
    ("Arjun Patel",  3),   ("Sneha Iyer",  5),    ("Vikram Nair",  2),
    ("Pooja Desai",  4),   ("Karan Malhotra", 8), ("Isha Joshi",   2),
    ("Dev Kapoor",   3),   ("Riya Verma",  4),    ("Aditya Rao",   6),
    ("Meera Shah",   5),   ("Kabir Sethi", 4),    ("Naina Kapoor", 3),
    ("Sahil Bhatia", 6),   ("Tanya Gupta", 2),    ("Rahul Sharma", 4),
    ("Divya Menon",  5),   ("Nikhil Jain", 3),
]

def make_future_res(target, count, waitlist_from, hour_choices, notes_choices, guest_adj=0):
    out = []
    for idx, (name, guests) in enumerate(FUTURE_NAMES[:count]):
        out.append(Reservation(
            guest_name   = name,
            guest_count  = max(2, guests + guest_adj),
            reserved_at  = target.replace(
                hour=random.choice(hour_choices),
                minute=random.choice([0, 15, 30, 45]),
            ),
            status = ReservationStatus.waitlist if idx >= waitlist_from else ReservationStatus.confirmed,
            table_number = random.randint(1, 15),
            notes = random.choice(notes_choices),
        ))
    return out

# ED Surge — first + third occurrence seeded high-occupancy (>90%, triggers Diff 2)
ED_SURGE_CONFIGS = [
    dict(count=18, waitlist_from=15, hours=[18, 19, 19, 20, 20, 21],
         notes=[None, "Post-discharge follow-up", "Wheelchair access", "Cardiology referral", "Multi-department consult"], guest_adj=2),
    dict(count=13, waitlist_from=11, hours=[18, 19, 20, 21],
         notes=[None, None, "Emergency follow-up", "Family caregiver accompanying"], guest_adj=0),
    dict(count=17, waitlist_from=14, hours=[18, 19, 19, 20, 20, 21],
         notes=[None, "Post-op review", "Interpreter required", "Pediatric guardian present", "Wheelchair access"], guest_adj=2),
    dict(count=12, waitlist_from=10, hours=[18, 19, 20, 21],
         notes=[None, None, "Follow-up after discharge", "Cardiology referral"], guest_adj=0),
]
DEFAULT_ED_SURGE_CONFIG = dict(count=11, waitlist_from=9, hours=[18, 19, 20, 21],
    notes=[None, None, "Post-discharge follow-up", "Wheelchair access"], guest_adj=0)

OPD_PEAK_CONFIGS = [
    dict(count=9,  waitlist_from=8,  hours=[12, 13, 14], guest_adj=-1),
    dict(count=10, waitlist_from=8,  hours=[12, 13, 14], guest_adj=-1),
    dict(count=9,  waitlist_from=8,  hours=[12, 13, 14], guest_adj=-1),
    dict(count=11, waitlist_from=9,  hours=[12, 13, 14], guest_adj=-1),
    dict(count=9,  waitlist_from=8,  hours=[12, 13, 14], guest_adj=-1),
    dict(count=10, waitlist_from=8,  hours=[12, 13, 14], guest_adj=-1),
    dict(count=9,  waitlist_from=8,  hours=[12, 13, 14], guest_adj=-1),
]
OPD_PEAK_NOTES = [None, None, "Routine OPD follow-up", "Lab results review", "Telehealth prep"]
DEFAULT_OPD_PEAK_CONFIG = dict(count=9, waitlist_from=8, hours=[12, 13, 14], guest_adj=-1)

ICU_CAPACITY_CONFIGS = [
    dict(count=15, waitlist_from=10, hours=[18, 19, 20, 21], adj=1),
    dict(count=14, waitlist_from=10, hours=[18, 19, 20, 21], adj=1),
    dict(count=17, waitlist_from=12, hours=[17, 18, 19, 20, 21], adj=2),
]
ICU_CAPACITY_NOTES = [None, "Step-down transfer", "Post-ICU follow-up", "Family conference", "Discharge planning"]
DEFAULT_ICU_CONFIG = dict(count=13, waitlist_from=10, hours=[18, 19, 20, 21], adj=1)

SUPPLY_SHORTAGE_CONFIGS = [
    dict(count=10, waitlist_from=8, hours=[13, 18, 19, 20]),
    dict(count=11, waitlist_from=9, hours=[13, 18, 19, 20]),
    dict(count=9,  waitlist_from=8, hours=[13, 18, 19, 20]),
]
SUPPLY_SHORTAGE_NOTES = [None, "Weekend clinic slot", "Elective procedure prep"]
DEFAULT_SUPPLY_CONFIG = dict(count=9, waitlist_from=8, hours=[13, 18, 19, 20])

for i, target in enumerate(FUTURE_SCENARIO_TARGETS["ed_surge"]):
    cfg = ED_SURGE_CONFIGS[i] if i < len(ED_SURGE_CONFIGS) else DEFAULT_ED_SURGE_CONFIG
    reservations.extend(make_future_res(target, cfg["count"], cfg["waitlist_from"], cfg["hours"], cfg["notes"], cfg["guest_adj"]))

for i, target in enumerate(FUTURE_SCENARIO_TARGETS["opd_peak"]):
    cfg = OPD_PEAK_CONFIGS[i] if i < len(OPD_PEAK_CONFIGS) else DEFAULT_OPD_PEAK_CONFIG
    reservations.extend(make_future_res(target, cfg["count"], cfg["waitlist_from"], cfg["hours"], OPD_PEAK_NOTES, cfg["guest_adj"]))

for i, target in enumerate(FUTURE_SCENARIO_TARGETS["icu_capacity"]):
    cfg = ICU_CAPACITY_CONFIGS[i] if i < len(ICU_CAPACITY_CONFIGS) else DEFAULT_ICU_CONFIG
    reservations.extend(make_future_res(target, cfg["count"], cfg["waitlist_from"], cfg["hours"], ICU_CAPACITY_NOTES, cfg["adj"]))

for i, target in enumerate(FUTURE_SCENARIO_TARGETS["supply_shortage"]):
    cfg = SUPPLY_SHORTAGE_CONFIGS[i] if i < len(SUPPLY_SHORTAGE_CONFIGS) else DEFAULT_SUPPLY_CONFIG
    reservations.extend(make_future_res(target, cfg["count"], cfg["waitlist_from"], cfg["hours"], SUPPLY_SHORTAGE_NOTES, -1))

session.add_all(reservations)
session.commit()
print(f"  Added {len(reservations)} reservations")


# ── 4. Encounters (historical — stored as Order rows for analytics) ─────────
menu_items_db = session.query(MenuItem).all()
emergency_items  = [m for m in menu_items_db if m.category == "emergency"]
outpatient_items = [m for m in menu_items_db if m.category == "outpatient"]
surgery_items    = [m for m in menu_items_db if m.category == "surgery"]
diagnostics_items = [m for m in menu_items_db if m.category == "diagnostics"]
inpatient_items  = [m for m in menu_items_db if m.category == "inpatient"]
other_items      = [m for m in menu_items_db if m.category not in ("emergency",)]
popular_ed_services = random.sample(emergency_items, min(3, len(emergency_items)))

FRIDAY_PEAK_DATES_SET   = {d.date() for d in FRIDAY_PEAKS}
WEEKDAY_LUNCH_DATES_SET = {d.date() for d in WEEKDAY_LUNCH_PEAKS}
HOLIDAY_DATES_SET       = {d.date() for d in HOLIDAY_PEAKS if HOLIDAY_PEAKS[d] > 0}

orders = []
for day_offset in range(HISTORY_DAYS + 1):
    current_date = base_date + timedelta(days=day_offset)
    d = current_date.date()
    is_friday  = current_date.weekday() == 4
    is_weekend = current_date.weekday() in [5, 6]
    is_wdl     = d in WEEKDAY_LUNCH_DATES_SET
    is_holiday = d in HOLIDAY_DATES_SET

    if   d in FRIDAY_PEAK_DATES_SET:  order_count = FRIDAY_PEAKS.get(current_date, random.randint(85, 115))
    elif d in WEEKDAY_LUNCH_DATES_SET: order_count = WEEKDAY_LUNCH_PEAKS.get(current_date, random.randint(38, 52))
    elif is_holiday:                   order_count = HOLIDAY_PEAKS.get(current_date, random.randint(80, 105))
    elif is_friday:                    order_count = random.randint(80, 115)
    elif is_weekend:                   order_count = random.randint(45, 65)
    elif is_wdl:                       order_count = random.randint(38, 52)
    elif current_date.date() == SEED_AS_OF.date():
                                       order_count = random.randint(12, 20)  # today — partial day so far
    else:                              order_count = random.randint(20, 32)

    for _ in range(order_count):
        if d in FRIDAY_PEAK_DATES_SET and random.random() < 0.70:
            item = random.choice(popular_ed_services)
        elif is_wdl or (not is_friday and not is_weekend and not is_holiday and random.random() < 0.55):
            item = random.choices(
                [random.choice(outpatient_items), random.choice(surgery_items),
                 random.choice(emergency_items), random.choice(diagnostics_items)],
                weights=[40, 30, 20, 10],
            )[0]
        elif is_holiday:
            item = random.choices(
                [random.choice(emergency_items), random.choice(inpatient_items),
                 random.choice(surgery_items), random.choice(diagnostics_items)],
                weights=[35, 25, 25, 15],
            )[0]
        elif is_weekend:
            item = random.choice(emergency_items) if random.random() < 0.60 else random.choice(other_items)
        else:
            item = random.choice(emergency_items) if random.random() < 0.60 else random.choice(other_items)

        quantity = random.randint(1, 3)

        if d in FRIDAY_PEAK_DATES_SET: h = hour_friday()
        elif is_wdl:                    h = hour_weekday_lunch()
        elif is_holiday:                h = hour_holiday()
        elif is_weekend:                h = hour_weekend()
        elif current_date.date() == SEED_AS_OF.date():
                                        h = random.choice([12, 13, 14])
        else:                           h = hour_generic_weekday()

        orders.append(Order(
            menu_item_id = item.id,
            quantity     = quantity,
            total_price  = round(item.price * quantity, 2),
            ordered_at   = current_date.replace(hour=h, minute=random.randint(0, 59)),
            is_delivery  = random.choice([True, False]),
        ))

session.add_all(orders)
session.commit()
print(f"  Added {len(orders)} encounters over {HISTORY_DAYS + 1} days")


# ── 5. Feedback ───────────────────────────────────────────────────────────────
# Two pools:
# - Older than 28 days: ~35% negative — historically elevated
# - Last 28 days:       ~28% negative — gray zone for Diff 4 (25-30% threshold)

orders_db     = session.query(Order).all()
recent_cutoff = SEED_AS_OF - timedelta(days=28)

older_orders  = [o for o in orders_db if o.ordered_at < recent_cutoff]
recent_orders = [o for o in orders_db if o.ordered_at >= recent_cutoff]

sample_older  = random.sample(older_orders,  min(120, len(older_orders)))
sample_recent = random.sample(recent_orders, min(55,  len(recent_orders)))

ed_surge_complaints = [
    "ED wait exceeded 3 hours on Friday evening — triage backlog was unacceptable.",
    "Chest pain protocol delayed; patient waited over 45 minutes for initial assessment.",
    "Ran out of IV saline bags during Friday ED surge. Critical supply gap.",
    "Appointment wait exceeded 30 minutes despite confirmed slot.",
    "Trauma assessment felt rushed; nursing staff seemed understaffed.",
    "Friday ED surge was chaotic — patients waiting 50+ minutes in corridor.",
    "Surgical gloves stockout again during peak ED volume — third week in a row.",
    "Reserved slot at 4pm but seen 25 minutes late with no communication.",
    "Discharge instructions felt incomplete after emergency observation stay.",
    "Long queues in ED on Friday with no updates from front desk staff.",
]
opd_peak_complaints = [
    "OPD consult at 1pm — waited 35 minutes past appointment. Clinic backlog ruined the visit.",
    "Booked three follow-ups for a team; one chart was incomplete and had to be redone.",
    "Internal medicine follow-up felt rushed. For a scheduled OPD slot it should be better.",
    "Lab results not ready at appointment time. Frustrating for a quick review visit.",
    "Wheelchair not available at 12:30pm despite prior request on the booking.",
    "Clinic visit took 40 minutes on a weekday. Had to reschedule other appointments.",
    "Service was slow even though the clinic was only half full at 1pm.",
]
icu_capacity_complaints = [
    "ICU step-down delayed — family waited 45 minutes for bed assignment update.",
    "Oxygen cannulas unavailable by 7pm during capacity watch. Concerning.",
    "Large family group of 8 waiting for ICU conference — seating inadequate.",
    "ICU follow-up appointment confirmed but seen 20 minutes late.",
    "Ventilator circuit supply low during capacity watch. Not acceptable for peak planning.",
]
recent_mild_complaints = [
    "Service felt a bit slow this week, though clinical care was good.",
    "Wait time slightly longer than usual on a weekday evening in OPD.",
    "Discharge summary took longer than expected to receive.",
    "ED visit was well managed but triage took longer than the 30-minute estimate.",
    "A bit crowded in waiting area on Friday — hard to find seating.",
]
positives = [
    "ED team handled trauma assessment quickly and professionally. Excellent care.",
    "Trauma assessment was outstanding — clear communication throughout.",
    "Staff were compassionate and very helpful during a stressful visit.",
    "Discharge planning review was thorough. Perfect end to a long stay.",
    "Fast triage even on a busy Friday evening. Impressed!",
    "Cardiology OPD visit was efficient and the doctor explained everything clearly.",
    "General surgery consult was well organised — minimal wait time.",
    "This week's ED surge was handled exceptionally well. Chest pain protocol was smooth.",
    "OPD peak days run smoothly — outpatient and diagnostics combo works well.",
    "Internal medicine follow-up on a weekday was clinic-quality care.",
    "ICU capacity watch was well managed despite high occupancy!",
    "Staff remembered our follow-up from last month. Thoughtful continuity of care.",
    "Physiotherapy session scheduling is the best we've experienced at this hospital.",
    "This Friday our ED triage completed in 18 minutes. Impressive!",
    "Clinic team loved the quick OPD turnaround. Will use this facility regularly.",
    "Perfect visit — care, communication, and coordination all on point.",
    "Laboratory panel results were ready same day. Have used this service 3 times this month.",
    "Wound dressing supplies were well stocked during our visit.",
]
neutrals = [
    "Decent care but nothing extraordinary. Average experience overall.",
    "Co-pay felt a bit high for the length of consult.",
    "Parking was a bit tricky near the main entrance.",
    "Visit was fine, nothing stood out. Might try another facility next time.",
    "Waiting area is clean but felt rushed on a Saturday morning.",
    "OPD visit was okay. Consult felt brief for the fee.",
]

all_historical_complaints = ed_surge_complaints + opd_peak_complaints + icu_capacity_complaints
feedback_list = []

# Older than 28 days: ~35% negative (42/120)
for i, order in enumerate(sample_older):
    if i < 42:
        text, sentiment = random.choice(all_historical_complaints), SentimentType.negative
    elif i < 96:
        text, sentiment = random.choice(positives),                 SentimentType.positive
    else:
        text, sentiment = random.choice(neutrals),                  SentimentType.neutral
    feedback_list.append(Feedback(
        order_id   = order.id,
        raw_text   = text,
        sentiment  = sentiment,
        source     = random.choice(list(FeedbackSource)),
        created_at = order.ordered_at + timedelta(hours=random.randint(1, 48)),
    ))

# Last 28 days: ~28% negative — gray zone (this is what ComplaintService sees → Diff 4 fires)
for i, order in enumerate(sample_recent):
    if i < 15:
        text, sentiment = random.choice(recent_mild_complaints + ed_surge_complaints[:4]), SentimentType.negative
    elif i < 43:
        text, sentiment = random.choice(positives),  SentimentType.positive
    else:
        text, sentiment = random.choice(neutrals),   SentimentType.neutral
    feedback_list.append(Feedback(
        order_id   = order.id,
        raw_text   = text,
        sentiment  = sentiment,
        source     = random.choice(list(FeedbackSource)),
        created_at = order.ordered_at + timedelta(hours=random.randint(1, 48)),
    ))

session.add_all(feedback_list)
session.commit()
print(f"  Added {len(feedback_list)} feedback entries ({len(sample_older)} older ~35% neg, {len(sample_recent)} last-28d ~27% neg)")


# ── 6. Decision logs ─────────────────────────────────────────────────────────
next_ed_surge = FUTURE_SCENARIO_TARGETS["ed_surge"][0]
next_opd_peak = FUTURE_SCENARIO_TARGETS["opd_peak"][0]
next_icu_capacity = FUTURE_SCENARIO_TARGETS["icu_capacity"][2]  # the biggest-configured one
next_supply_shortage = FUTURE_SCENARIO_TARGETS["supply_shortage"][0]

recent_ed_summary = ", ".join(f"{fmt(d)} ({c})" for d, c in list(FRIDAY_PEAKS.items())[-3:])
recent_opd_summary  = ", ".join(f"{fmt(d)} ({c})" for d, c in list(WEEKDAY_LUNCH_PEAKS.items())[-3:])

decision_logs = [
    DecisionLog(
        agent="demand_forecast_agent",
        input_summary=f"Recent ED surge peaks: {recent_ed_summary} — sustained admissions above 108 encounters.",
        retrieved_context=f"5-week trend: 108-138. {fmt(next_ed_surge)} projected 125-135 admissions.",
        reasoning_summary=f"{fmt(next_ed_surge)} is a high-confidence ED surge. Pre-stage triage beds by 5pm, add 2 nursing staff.",
        action_recommended=f"Open 8+ overflow beds by 5pm {fmt(next_ed_surge)}. Book 2 extra ED nurses 18:00-22:00.",
        critic_verdict=CriticVerdict.approved, critic_score=0.92,
        critic_notes="Forecast is data-backed. Staffing recommendation is feasible.",
    ),
    DecisionLog(
        agent="inventory_agent",
        input_summary=", ".join(
            f"{name} {qty}{unit} (threshold {threshold}{unit})" for name, unit, qty, threshold in low_ingredients_seeded
        ) + " running low.",
        retrieved_context=f"{len(low_ingredients_seeded)} item(s) below threshold. {fmt(next_ed_surge)} is the next ED Surge window.",
        reasoning_summary=f"{'Multi-supply' if len(low_ingredients_seeded) > 1 else 'Supply'} shortage risk ahead of {fmt(next_ed_surge)} surge.",
        action_recommended=f"Reorder by {fmt(next_ed_surge - timedelta(days=2))}: " + ", ".join(
            f"{round(threshold - qty + threshold * 0.2, 1)}{unit} {name.lower()}" for name, unit, qty, threshold in low_ingredients_seeded
        ) + ".",
        critic_verdict=CriticVerdict.approved, critic_score=0.96,
        critic_notes="Urgent and justified. Quantities are realistic.",
    ),
    DecisionLog(
        agent="demand_forecast_agent",
        input_summary=f"OPD peak days: {recent_opd_summary} — outpatient clinic pattern holding.",
        retrieved_context="Outpatient and surgery consults dominate 12-14:00. Average 45 encounters on peak days.",
        reasoning_summary=f"{fmt(next_opd_peak)} will likely hit 46-52 encounters. Clinic throughput is the constraint.",
        action_recommended=f"Pre-open 2 extra OPD rooms by 11:30am on {fmt(next_opd_peak)}. Staff one extra nurse 12-15:00.",
        critic_verdict=CriticVerdict.approved, critic_score=0.88,
        critic_notes="OPD peak pattern is well-evidenced. Recommendation is specific and actionable.",
    ),
    DecisionLog(
        agent="complaint_intelligence_agent",
        input_summary="15 recent complaints about ED wait times and supply stockouts. Notable: surgical glove shortages on recent surges.",
        retrieved_context="Complaints cluster: Friday ED wait times, PPE availability, discharge communication.",
        reasoning_summary="Surgical glove shortage is a recurring ED surge issue. Needs pre-surge restock discipline.",
        action_recommended="Add surgical gloves to Thursday restock checklist. Set 20-min triage target for all ED surge shifts.",
        critic_verdict=CriticVerdict.approved, critic_score=0.85,
        critic_notes="Specific, actionable, addresses root cause.",
    ),
    DecisionLog(
        agent="demand_forecast_agent",
        input_summary=f"{fmt(next_icu_capacity)} ICU capacity watch projected, in line with recent occupancy spikes.",
        retrieved_context="ICU demand adds 20-25% uplift vs a standard day. Step-down transfers already elevated.",
        reasoning_summary=f"{fmt(next_icu_capacity)} may reach 100-115 encounters. Full ICU capacity protocol needed.",
        action_recommended=f"Run full surge protocol on {fmt(next_icu_capacity)}: 3 charge nurses, ventilator circuit stock doubled.",
        critic_verdict=CriticVerdict.approved, critic_score=0.90,
        critic_notes="ICU uplift is well-documented. Running surge protocol is the right call.",
    ),
    DecisionLog(
        agent="inventory_agent",
        input_summary=", ".join(
            f"{name} {qty}{unit} (threshold {threshold}{unit})"
            for name, unit, qty, threshold in comfortable_ingredients_seeded[:2]
        ) + " — comfortable now, but critical supply draw accelerates during ICU capacity watches.",
        retrieved_context=f"Past ICU watches depleted stock faster than forecast. {fmt(next_icu_capacity)} is the next high-risk date.",
        reasoning_summary=f"Stock should be rechecked ahead of {fmt(next_icu_capacity)}.",
        action_recommended=f"Recheck {' and '.join(name for name, *_ in comfortable_ingredients_seeded[:2])} levels by {fmt(next_icu_capacity - timedelta(days=4))}.",
        critic_verdict=CriticVerdict.approved, critic_score=0.87,
        critic_notes="Proactive critical supply restock — well-timed for ICU capacity watch.",
    ),
    DecisionLog(
        agent="inventory_agent",
        input_summary="Weekend watch items: IV Saline Bags, Wound Dressings, Sterile Syringes — historically depleted faster on busy weekends.",
        retrieved_context=f"{fmt(next_supply_shortage)} is the next Supply Shortage Response window.",
        reasoning_summary=f"Supplies should be topped up ahead of {fmt(next_supply_shortage)} weekend operations.",
        action_recommended=f"Restock IV Saline Bags, Wound Dressings, and Sterile Syringes by {fmt(next_supply_shortage - timedelta(days=2))}.",
        critic_verdict=CriticVerdict.approved, critic_score=0.89,
        critic_notes="Supply shortage call is well-timed. Quantities are specific and justified.",
    ),
]
# ── 7. Expenses — fixed/recurring costs backing the financial health score ──
# DEMO_ORG_ID=1 ("Casa Mia") is the seeded owner account's org. Effective dates
# anchor to the start of the history window so recurring costs are active for
# the whole trailing period, not just from today.
DEMO_ORG_ID = 1
expenses = [
    Expense(org_id=DEMO_ORG_ID, category=ExpenseCategory.rent, amount=85000.0,
            recurrence=ExpenseRecurrence.monthly, effective_date=base_date,
            note="Hospital facility lease"),
    Expense(org_id=DEMO_ORG_ID, category=ExpenseCategory.utilities, amount=22000.0,
            recurrence=ExpenseRecurrence.monthly, effective_date=base_date,
            note="Electricity, water, medical gas utilities"),
    Expense(org_id=DEMO_ORG_ID, category=ExpenseCategory.marketing, amount=3500.0,
            recurrence=ExpenseRecurrence.weekly, effective_date=base_date,
            note="Community health outreach + patient engagement campaigns"),
    Expense(org_id=DEMO_ORG_ID, category=ExpenseCategory.other, amount=15000.0,
            recurrence=ExpenseRecurrence.one_time, effective_date=SEED_AS_OF - timedelta(days=9),
            note="ED triage zone equipment upgrade"),
]
session.add_all(expenses)
session.commit()
print(f"  Added {len(expenses)} expenses (rent, utilities, marketing, one-time)")


# ── 8. Vendors — hospital supply procurement contacts ───────────────────────
vendors = [
    Vendor(org_id=DEMO_ORG_ID, name="MedSupply Co", category="consumables",
           is_online=False, whatsapp_number="+919876543210"),
    Vendor(org_id=DEMO_ORG_ID, name="Regional PPE Warehouse", category="ppe",
           is_online=False, whatsapp_number="+919876512345"),
    Vendor(org_id=DEMO_ORG_ID, name="Hospital Pharma Distributors", category="pharmacy",
           is_online=True, whatsapp_number=None),
]
session.add_all(vendors)
session.commit()
medsupply = vendors[0]
print(f"  Added {len(vendors)} vendors (MedSupply Co, Regional PPE Warehouse, Hospital Pharma Distributors)")

vendor_price_quotes = [
    VendorPriceQuote(vendor_id=vendors[0].id, ingredient="IV Saline Bags", price=45.0),
    VendorPriceQuote(vendor_id=vendors[2].id, ingredient="IV Saline Bags", price=52.0),
    VendorPriceQuote(vendor_id=vendors[0].id, ingredient="Surgical Gloves", price=340.0),
    VendorPriceQuote(vendor_id=vendors[0].id, ingredient="Sterile Syringes", price=210.0),
    VendorPriceQuote(vendor_id=vendors[0].id, ingredient="Wound Dressings", price=180.0),
    VendorPriceQuote(vendor_id=vendors[0].id, ingredient="N95 Respirators", price=420.0),
    VendorPriceQuote(vendor_id=vendors[1].id, ingredient="Examination Gloves", price=280.0),
    VendorPriceQuote(vendor_id=vendors[1].id, ingredient="Oxygen Cannulas", price=95.0),
    VendorPriceQuote(vendor_id=vendors[1].id, ingredient="Bandages Sterile", price=120.0),
    VendorPriceQuote(vendor_id=vendors[1].id, ingredient="Isolation Gowns", price=150.0),
    VendorPriceQuote(vendor_id=vendors[2].id, ingredient="Ventilator Circuits", price=680.0),
    VendorPriceQuote(vendor_id=vendors[2].id, ingredient="IV Administration Sets", price=35.0),
    VendorPriceQuote(vendor_id=vendors[2].id, ingredient="Urinary Catheters", price=220.0),
    VendorPriceQuote(vendor_id=vendors[2].id, ingredient="Pulse Oximeter Probes", price=890.0),
]
session.add_all(vendor_price_quotes)
session.commit()
print(f"  Added {len(vendor_price_quotes)} vendor price quotes across "
      f"{len({q.ingredient for q in vendor_price_quotes})} ingredients")


# ── 9. Action Queue — historical decisions + demo pending actions ───────────
# A couple of already-decided historical actions so the trust-ladder approval
# streak (P6-A12) has something real to show immediately after a fresh seed,
# not just whatever happens to accumulate from live testing.
historical_actions = [
    ActionQueue(
        org_id=DEMO_ORG_ID, category="whatsapp_vendor_order", tier=ActionTier.approve_required,
        status=ActionStatus.executed, title="Order IV Saline Bags from MedSupply Co",
        payload={"vendor_id": medsupply.id, "vendor": medsupply.name, "ingredient": "IV Saline Bags",
                 "message_draft": "Hi MedSupply, IV saline stock is low — please dispatch 50 units by tomorrow morning. Thanks!"},
        approved_by=None, executed_at=SEED_AS_OF - timedelta(days=6),
        created_at=SEED_AS_OF - timedelta(days=6, hours=1),
    ),
    ActionQueue(
        org_id=DEMO_ORG_ID, category="whatsapp_vendor_order", tier=ActionTier.approve_required,
        status=ActionStatus.executed, title="Order Surgical Gloves from MedSupply Co",
        payload={"vendor_id": medsupply.id, "vendor": medsupply.name, "ingredient": "Surgical Gloves",
                 "message_draft": "Hi MedSupply, surgical gloves running low — need 30 boxes by tomorrow AM."},
        approved_by=None, executed_at=SEED_AS_OF - timedelta(days=2),
        created_at=SEED_AS_OF - timedelta(days=2, hours=1),
    ),
]
session.add_all(historical_actions)
session.commit()

# Pending actions tied to whichever inventory items this seed's random draw
# actually marked low, so the Action Queue UI has real content before the
# workflow trigger engine (P6-A11) creates one automatically on the next
# planning run -- previously hardcoded to Fresh Basil/Mozzarella specifically,
# which no longer always match what's actually low once shortages rotate.
# Only offline (WhatsApp/phone) vendors ever get attached to a shortage --
# Online vendor pricing is checked live, on demand, not from a stored quote, so
# it's never "suggested" here; the owner decides per shortage which channel
# to use, the system just surfaces the real WhatsApp option when one exists.
offline_vendors = [v for v in vendors if not v.is_online]
offline_vendors_by_ingredient = {
    q.ingredient: next(v for v in vendors if v.id == q.vendor_id)
    for q in vendor_price_quotes
    if not next(v for v in vendors if v.id == q.vendor_id).is_online
}

def _any_offline_vendor(ingredient):
    # A vendor with an exact ingredient quote wins first, but a WhatsApp order
    # was never meant to require a pre-recorded price for that exact item --
    # in real life these rates are just discussed once or twice on a call,
    # not kept as a live price list -- so this falls back to ANY offline
    # vendor the org already works with, rather than hiding the WhatsApp
    # option entirely whenever this specific ingredient has no quote on file.
    return offline_vendors_by_ingredient.get(ingredient) or (offline_vendors[0] if offline_vendors else None)

def _whatsapp_draft(order_name, order_unit, order_qty, order_threshold, vendor, created_at=None):
    reorder_amount = round(max(order_threshold - order_qty, order_threshold * 0.3) + order_threshold * 0.2, 1)
    greeting = "Hi MedSupply" if vendor.name == "MedSupply Co" else f"Hi {vendor.name}"
    return ActionQueue(
        org_id=DEMO_ORG_ID, category="whatsapp_vendor_order", tier=ActionTier.approve_required,
        status=ActionStatus.pending, title=f"Order {order_name} from {vendor.name}",
        payload={
            "vendor_id": vendor.id, "vendor": vendor.name, "ingredient": order_name,
            "quantity_in_stock": order_qty, "reorder_threshold": order_threshold,
            "message_draft": f"{greeting}, {order_name.lower()} is running low, only {order_qty}{order_unit} left. "
                             f"Can you send {reorder_amount}{order_unit} by tomorrow morning? Let me know the rate, thanks!",
        },
        **({"created_at": created_at} if created_at else {}),
    )

top_name, top_unit, top_qty, top_threshold = low_ingredients_seeded[0]
top_shortfall = round(top_threshold - top_qty, 2)
top_restock_qty = round(top_shortfall + top_threshold * 0.2, 1)
top_vendor = _any_offline_vendor(top_name)

# Mirrors the real shape workflow_trigger_service.py's _check_critical_shortages
# builds (a "shortages" list, not a flat payload) -- the Action Center hero card
# reads action.payload.shortages[0] and falls back to the raw title otherwise.
# When a real offline vendor carries the top shortage's ingredient, a linked
# WhatsApp draft is created too, same as the real trigger service does --
# the hero's "message vendor" button opens this exact pending action.
action_queue_items = [
    ActionQueue(
        org_id=DEMO_ORG_ID, category="restock_alert", tier=ActionTier.recommendation,
        status=ActionStatus.pending,
        title=f"{top_name} is running low",
        payload={
            "shortages": [{
                "ingredient": top_name,
                "unit": top_unit,
                "quantity_in_stock": top_qty,
                "reorder_threshold": top_threshold,
                "shortfall": top_shortfall,
                "recommended_restock_qty": top_restock_qty,
                "whatsapp_vendor": top_vendor.name if top_vendor else None,
                "reason": f"Stock is running below your usual minimum of {top_threshold}{top_unit}.",
            }],
        },
    ),
]
if top_vendor:
    action_queue_items.append(_whatsapp_draft(top_name, top_unit, top_qty, top_threshold, top_vendor))

# Always keep 2-3 more pending WhatsApp vendor-order approvals on hand, for
# ingredients unrelated to today's critical shortage -- previously this only
# existed when the day's random low-stock draw happened to mark 2+
# ingredients low (n_low is randint(1,4), so plenty of seeds landed on 0 or 1
# WhatsApp items, i.e. nothing to demo the approval flow with at all).
whatsapp_candidates = [
    t for t in (low_ingredients_seeded + comfortable_ingredients_seeded)
    if t[0] in offline_vendors_by_ingredient and t[0] != top_name
]
random.shuffle(whatsapp_candidates)
n_whatsapp = min(random.randint(2, 3), len(whatsapp_candidates))
for i, (order_name, order_unit, order_qty, order_threshold) in enumerate(whatsapp_candidates[:n_whatsapp]):
    action_queue_items.append(_whatsapp_draft(
        order_name, order_unit, order_qty, order_threshold,
        offline_vendors_by_ingredient[order_name],
        created_at=SEED_AS_OF - timedelta(hours=2 + i * 3),
    ))
session.add_all(action_queue_items)
session.commit()
print(f"  Added {len(historical_actions)} historical Action Queue decisions + {len(action_queue_items)} pending demo items")


session.add_all(decision_logs)
session.commit()
print(f"  Added {len(decision_logs)} decision logs")

session.close()

print("\nCareOps v6 demo data seeded successfully.")
print(f"  History   : {(SEED_AS_OF - timedelta(days=HISTORY_DAYS)).date()} – {SEED_AS_OF.date()}")
print(f"  Future    : {FUTURE_SCENARIO_TARGETS['ed_surge'][0].date()} – {FUTURE_SCENARIO_TARGETS['ed_surge'][-1].date()} ({FUTURE_OCCURRENCES} occurrences per scenario)")
print(f"  ED surge peaks   : {len(FRIDAY_PEAKS)} historical peaks (108–138 encounters)")
print(f"  OPD peak days    : {len(WEEKDAY_LUNCH_PEAKS)} historical peaks (38–52 encounters)")
print(f"  ICU capacity     : {len(HOLIDAY_PEAKS)} historical dates")
print(f"  Inventory        : {n_low} of {len(inventory_items)} supplies below threshold ({', '.join(n for n, *_ in low_ingredients_seeded)})")
print(f"  Feedback         : {len(feedback_list)} entries — older ~35% neg, last 28d ~27% neg (Diff 4 gray zone)")
print(f"  High-occupancy   : {fmt(FUTURE_SCENARIO_TARGETS['ed_surge'][0])} and {fmt(FUTURE_SCENARIO_TARGETS['ed_surge'][2])} seeded >90% occupancy")
print(f"  Expenses         : {len(expenses)} entries — facility lease + utilities (monthly), outreach (weekly), 1 one-time cost")
print(f"  Action Queue     : {len(action_queue_items)} pending demo items")
print(f"  Vendors          : {len(vendors)} vendors, {len(vendor_price_quotes)} price quotes")

"""Unit tests for CompetitorEnricher._compute_category_pricing.

Category pricing is dish-name INDEPENDENT: your_avg is the average of ALL our items
in a category (not just ones with a name-matched competitor price), and area_avg
comes from competitor dishes keyword-classified into that category via
_classify_dish -- not from exact string matches. category_dishes (name+price+
restaurant per dish, not just bare prices) is built upstream by _compute_averages()
and passed in directly here, but _compute_category_pricing strips the restaurant
attribution before returning cheapest_dish/priciest_dish (P6-A20) -- dish name +
price only, never which restaurant serves it.
"""

from unittest.mock import MagicMock

from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher


def _enricher():
    return CompetitorEnricher(MagicMock())


def _dish(name: str, price: float, restaurant: str = "Competitor"):
    return {"name": name, "price": price, "restaurant": restaurant}


def test_category_pricing_computes_above_and_below():
    enricher = _enricher()
    category_dishes = {
        "mains": [_dish("Comp Mains", 400.0)],
        "starters": [_dish("Comp Starter", 100.0)],
    }
    our_items = [
        {"name": "Butter Chicken", "price": 340.0, "category": "Mains"},   # below area (400)
        {"name": "Paneer Tikka", "price": 160.0, "category": "Starters"},  # above area (100)
    ]

    results = enricher._compute_category_pricing(category_dishes, our_items)
    by_category = {r["category"]: r for r in results}

    assert by_category["mains"]["verdict"] == "below"
    assert by_category["mains"]["your_avg"] == 340.0
    assert by_category["mains"]["area_avg"] == 400.0
    assert by_category["starters"]["verdict"] == "above"


def test_category_pricing_verdict_in_line_within_5_percent():
    enricher = _enricher()
    category_dishes = {"mains": [_dish("Comp Dal", 200.0)]}
    our_items = [{"name": "Dal Makhani", "price": 204.0, "category": "Mains"}]  # 2% gap

    results = enricher._compute_category_pricing(category_dishes, our_items)
    assert len(results) == 1
    assert results[0]["verdict"] == "in line"


def test_category_pricing_skips_categories_with_no_competitor_data():
    enricher = _enricher()
    category_dishes: dict[str, list[dict]] = {}  # no competitor dishes classified into anything
    our_items = [{"name": "House Special", "price": 500.0, "category": "Specials"}]

    results = enricher._compute_category_pricing(category_dishes, our_items)
    assert results == []


def test_category_pricing_averages_all_our_items_in_category_not_just_matched():
    """Core of the redesign: EVERY item in a category counts toward your_avg, even
    ones with no equivalent in the competitor data -- there's no "matching" step."""
    enricher = _enricher()
    category_dishes = {"starters": [_dish("Comp A", 100.0), _dish("Comp B", 200.0)]}
    our_items = [
        {"name": "Item A", "price": 110.0, "category": "Starters"},
        {"name": "Item B", "price": 220.0, "category": "Starters"},
    ]

    results = enricher._compute_category_pricing(category_dishes, our_items)
    assert len(results) == 1
    cat = results[0]
    assert cat["your_avg"] == 165.0  # (110+220)/2
    assert cat["area_avg"] == 150.0  # (100+200)/2
    assert cat["competitor_dishes_sampled"] == 2


def test_category_pricing_ignores_items_with_no_category_or_zero_price():
    enricher = _enricher()
    category_dishes = {"mains": [_dish("Comp", 100.0)]}
    our_items = [
        {"name": "Mystery Dish", "price": 0, "category": "Mains"},       # zero price -- skipped
        {"name": "No Category Dish", "price": 100.0, "category": ""},   # no category -- skipped
    ]

    results = enricher._compute_category_pricing(category_dishes, our_items)
    assert results == []


def test_category_pricing_sorted_by_absolute_diff_descending():
    enricher = _enricher()
    category_dishes = {"cat a": [_dish("A", 100.0)], "cat b": [_dish("B", 100.0)]}
    our_items = [
        {"name": "Small Gap", "price": 106.0, "category": "Cat A"},   # 6% diff
        {"name": "Big Gap", "price": 150.0, "category": "Cat B"},     # 50% diff
    ]

    results = enricher._compute_category_pricing(category_dishes, our_items)
    assert results[0]["category"] == "cat b"
    assert results[1]["category"] == "cat a"


def test_category_pricing_cheapest_and_priciest_dish_omit_restaurant():
    enricher = _enricher()
    category_dishes = {
        "pizza": [
            _dish("Farmhouse Pizza", 549.0, "Oven Story Pizza"),
            _dish("Butter Crust Pizza", 1569.0, "American Pie"),
            _dish("Margherita", 599.0, "Domino's"),
        ],
    }
    our_items = [{"name": "Four Cheese", "price": 479.0, "category": "Pizza"}]

    results = enricher._compute_category_pricing(category_dishes, our_items)
    assert len(results) == 1
    cat = results[0]
    # Dish name + price only -- restaurant attribution stripped (P6-A20).
    assert cat["cheapest_dish"] == {"name": "Farmhouse Pizza", "price": 549.0}
    assert cat["priciest_dish"] == {"name": "Butter Crust Pizza", "price": 1569.0}
    assert "restaurant" not in cat["cheapest_dish"]
    assert "restaurant" not in cat["priciest_dish"]

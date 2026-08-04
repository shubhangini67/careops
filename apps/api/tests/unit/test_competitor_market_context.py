"""Unit tests for CompetitorEnricher's market-context signals: menu breadth,
cuisine crowding, veg/non-veg mix. All derived from data already fetched in
_get_open_competitors()/_fetch_menus() -- zero extra API calls.
"""

from unittest.mock import MagicMock

from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher


def _enricher():
    return CompetitorEnricher(MagicMock())


# ── Menu breadth ──────────────────────────────────────────────────────────────

def test_menu_breadth_compares_item_counts():
    enricher = _enricher()
    competitor_menus = [
        {"name": "A", "menu": {"categories": [{"items": [{}] * 30}]}},
        {"name": "B", "menu": {"categories": [{"items": [{}] * 20}]}},
    ]
    our_items = [{"name": f"Item {i}"} for i in range(10)]

    result = enricher._compute_menu_breadth(competitor_menus, our_items)

    assert result["your_item_count"] == 10
    assert result["competitor_avg_item_count"] == 25.0  # (30+20)/2
    assert result["competitors_sampled"] == 2


def test_menu_breadth_returns_none_when_no_data():
    enricher = _enricher()
    assert enricher._compute_menu_breadth([], [{"name": "Item"}]) is None
    assert enricher._compute_menu_breadth([{"name": "A", "menu": {}}], []) is None


def test_menu_breadth_skips_competitors_with_zero_items():
    enricher = _enricher()
    competitor_menus = [
        {"name": "A", "menu": {"categories": [{"items": [{}] * 10}]}},
        {"name": "Empty", "menu": {"categories": []}},
    ]
    our_items = [{"name": "Item"}]

    result = enricher._compute_menu_breadth(competitor_menus, our_items)
    assert result["competitor_avg_item_count"] == 10.0
    assert result["competitors_sampled"] == 1


# ── Cuisine crowding ──────────────────────────────────────────────────────────

def test_cuisine_crowding_counts_matching_competitors():
    enricher = _enricher()
    restaurants = [
        {"name": "A", "cuisines": ["Pizzas", "Italian"]},
        {"name": "B", "cuisines": ["Burgers", "American"]},
        {"name": "C", "cuisines": ["Italian", "Pastas"]},
    ]

    result = enricher._compute_cuisine_crowding(restaurants, "italian")

    assert result["cuisine"] == "italian"
    assert result["matching_count"] == 2
    assert result["total_checked"] == 3


def test_cuisine_crowding_returns_none_for_generic_cuisine():
    enricher = _enricher()
    restaurants = [{"name": "A", "cuisines": ["Italian"]}]
    assert enricher._compute_cuisine_crowding(restaurants, "restaurant") is None
    assert enricher._compute_cuisine_crowding(restaurants, "") is None


def test_cuisine_crowding_returns_none_when_no_restaurants():
    enricher = _enricher()
    assert enricher._compute_cuisine_crowding([], "italian") is None


# ── Veg/non-veg mix ───────────────────────────────────────────────────────────

def test_veg_mix_counts_pure_veg_restaurants():
    enricher = _enricher()
    restaurants = [
        {"name": "A", "veg": True},
        {"name": "B", "veg": False},
        {"name": "C", "veg": True},
        {"name": "D"},  # missing veg key -- treated as non-veg
    ]

    result = enricher._compute_veg_mix(restaurants)

    assert result["veg_count"] == 2
    assert result["total"] == 4


def test_veg_mix_returns_none_when_no_restaurants():
    enricher = _enricher()
    assert enricher._compute_veg_mix([]) is None

"""Unit tests for CompetitorEnricher._extract_landscape and _parse_cost_for_two.

Live testing found costForTwo comes back as a formatted string like "₹500 for two",
not a bare number -- these tests lock in that parsing plus the full set of detail
fields (rating, total_ratings, delivery time, cuisines, offer, veg) the "detailed
cards" redesign surfaces on the /market page.
"""

from unittest.mock import MagicMock

from app.infrastructure.swiggy.enrichers.competitor import CompetitorEnricher


def _enricher():
    return CompetitorEnricher(MagicMock())


def test_parse_cost_for_two_extracts_digits_from_formatted_string():
    enricher = _enricher()
    assert enricher._parse_cost_for_two("₹500 for two") == 500.0
    assert enricher._parse_cost_for_two("₹1,500 for two") == 1500.0
    assert enricher._parse_cost_for_two(400) == 400.0
    assert enricher._parse_cost_for_two(None) is None
    assert enricher._parse_cost_for_two("no digits here") is None


def test_extract_landscape_captures_full_detail():
    enricher = _enricher()
    restaurants = [
        {
            "name": "Oven Story Pizza",
            "avgRating": 4.4,
            "totalRatings": "2.4K+",
            "costForTwo": "₹400 for two",
            "distanceKm": 0.5,
            "deliveryTimeRange": "30-35 MINS",
            "cuisines": ["Pizzas", "Italian"],
            "offer": "70% OFF UPTO ₹130",
            "veg": False,
        },
    ]

    result = enricher._extract_landscape(restaurants)

    assert len(result) == 1
    entry = result[0]
    assert entry["name"] == "Oven Story Pizza"
    assert entry["rating"] == 4.4
    assert entry["total_ratings"] == "2.4K+"
    assert entry["cost_for_two"] == 400.0
    assert entry["distance_km"] == 0.5
    assert entry["delivery_time_range"] == "30-35 MINS"
    assert entry["cuisines"] == ["Pizzas", "Italian"]
    assert entry["offer"] == "70% OFF UPTO ₹130"
    assert entry["veg"] is False


def test_extract_landscape_defaults_missing_optional_fields():
    enricher = _enricher()
    restaurants = [{"name": "Minimal Place", "avgRating": 4.0, "costForTwo": "₹300 for two", "distanceKm": 1.0}]

    result = enricher._extract_landscape(restaurants)

    assert len(result) == 1
    entry = result[0]
    assert entry["total_ratings"] == ""
    assert entry["delivery_time_range"] == ""
    assert entry["cuisines"] == []
    assert entry["offer"] == ""
    assert entry["veg"] is False


def test_extract_landscape_skips_entries_missing_required_fields():
    enricher = _enricher()
    restaurants = [
        {"name": "No Rating", "costForTwo": "₹300 for two", "distanceKm": 1.0},
        {"name": "No Cost", "avgRating": 4.0, "distanceKm": 1.0},
        {"avgRating": 4.0, "costForTwo": "₹300 for two", "distanceKm": 1.0},  # no name
    ]

    result = enricher._extract_landscape(restaurants)
    assert result == []


def test_extract_landscape_respects_display_cap():
    enricher = _enricher()
    restaurants = [
        {"name": f"R{i}", "avgRating": 4.0, "costForTwo": "₹300 for two", "distanceKm": 1.0}
        for i in range(20)
    ]

    result = enricher._extract_landscape(restaurants)
    assert len(result) == 15  # _MAX_LANDSCAPE_ENTRIES

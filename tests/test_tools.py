"""
tests/test_tools.py

Isolation tests for each FitFindr tool.
Run with: pytest tests/
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ────────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # No listing matches an impossible combination
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []  # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)


def test_search_size_filter():
    results = search_listings("jeans", size="M", max_price=None)
    # Every result must contain "m" in its size string (case-insensitive)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    # The first result should have a higher (or equal) keyword match than the last
    results = search_listings("vintage streetwear", size=None, max_price=None)
    assert len(results) > 1  # need at least two to compare
    # Re-score manually: count tokens from query appearing in first vs last
    tokens = set("vintage streetwear".split())
    def score(item):
        text = " ".join([item["title"], item["description"],
                         " ".join(item["style_tags"]), " ".join(item["colors"])]).lower()
        return sum(1 for t in tokens if t in text)
    assert score(results[0]) >= score(results[-1])


def test_search_returns_correct_fields():
    # Use "vintage" — appears in many listings across title/tags/description
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) > 0
    required_fields = {"id", "title", "description", "category", "style_tags",
                       "size", "condition", "price", "colors", "brand", "platform"}
    assert required_fields.issubset(results[0].keys())


# ── suggest_outfit ─────────────────────────────────────────────────────────────

# A minimal listing dict to use across outfit tests
SAMPLE_ITEM = {
    "id": "lst_test",
    "title": "Vintage Graphic Band Tee — Faded Black",
    "description": "Classic faded band tee, perfect for layering.",
    "category": "tops",
    "style_tags": ["vintage", "grunge", "graphic tee"],
    "size": "M",
    "condition": "good",
    "price": 22.0,
    "colors": ["black", "grey"],
    "brand": None,
    "platform": "depop",
}


def test_suggest_outfit_with_wardrobe():
    wardrobe = get_example_wardrobe()
    result = suggest_outfit(SAMPLE_ITEM, wardrobe)
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_empty_wardrobe():
    # Should return styling advice, not crash or return empty string
    empty = get_empty_wardrobe()
    result = suggest_outfit(SAMPLE_ITEM, empty)
    assert isinstance(result, str)
    assert len(result) > 0


# ── create_fit_card ────────────────────────────────────────────────────────────

SAMPLE_OUTFIT = (
    "Pair the band tee with baggy dark wash jeans and chunky white sneakers "
    "for a 90s streetwear look."
)


def test_create_fit_card_returns_string():
    result = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_empty_outfit():
    # Empty outfit string must not raise — returns error message string
    result = create_fit_card("", SAMPLE_ITEM)
    assert result == "[fit card unavailable — outfit suggestion was empty]"


def test_create_fit_card_whitespace_outfit():
    result = create_fit_card("   ", SAMPLE_ITEM)
    assert result == "[fit card unavailable — outfit suggestion was empty]"


def test_create_fit_card_mentions_item_details():
    result = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    # Caption should reference the platform and price somewhere
    assert "depop" in result.lower() or "22" in result

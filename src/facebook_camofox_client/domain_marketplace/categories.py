"""Marketplace category map — hardcode per Listaro spec, never scrape per run.

Facebook hides categories behind nested modal trees; scraping each run is
brittle and slow. Unknown values fail loud (unknown_category) instead of
publishing into a wrong category.
"""
from __future__ import annotations

CATEGORY_MAP: dict[str, str] = {
    "services": "Services",
    "household": "Household",
    "tools": "Tools",
    "furniture": "Furniture",
    "garden": "Garden",
    "appliances": "Appliances",
    "electronics": "Electronics",
    "clothing": "Clothing & accessories",
    "vehicles": "Vehicles",
    "property": "Property for rent",
    "free": "Free stuff",
    "entertainment": "Entertainment",
    "home": "Home goods",
}


def resolve_category(value: str) -> str | None:
    """Map domain value -> exact Facebook button text. Accepts keys
    ('household'), exact text ('Household'), any case. None if unknown."""
    if not value:
        return None
    want = value.strip().lower()
    if want in CATEGORY_MAP:
        return CATEGORY_MAP[want]
    for text in CATEGORY_MAP.values():
        if text.lower() == want:
            return text
    return None

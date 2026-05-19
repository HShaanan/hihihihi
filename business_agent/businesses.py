"""Personalized business list and the search tool exposed to the ADK agent."""

import json
from pathlib import Path

_DATA_FILE = Path(__file__).parent / "data" / "businesses.json"


def _load_businesses() -> list[dict]:
    with open(_DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


_BUSINESSES = _load_businesses()


def _score(business: dict, query: str, category: str) -> int:
    text = " ".join(
        [
            business.get("name", ""),
            business.get("category", ""),
            business.get("description", ""),
            " ".join(business.get("tags", [])),
            business.get("city", ""),
        ]
    )
    score = 0
    for term in query.split():
        term = term.strip()
        if term and term in text:
            score += 2
    if category:
        if category.strip() and category.strip() in business.get("category", ""):
            score += 5
    return score


def search_businesses(query: str, category: str = "") -> dict:
    """Search the personalized business list for businesses matching the user's need.

    Use this whenever the user is looking for a business, service or provider.
    Extract the core need into `query` (free text, Hebrew) and, if the user
    implied a clear business category (e.g. "מוסך", "אינסטלציה", "מסעדה"),
    pass it in `category`.

    Args:
        query: Free-text description of what the user is looking for, in Hebrew.
        category: Optional business category to narrow the search.

    Returns:
        A dict with `count` and a `results` list of matching businesses
        (name, category, city, phone, description), best match first.
    """
    scored = []
    for business in _BUSINESSES:
        s = _score(business, query, category)
        if s > 0:
            scored.append((s, business))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [
        {
            "name": b["name"],
            "category": b["category"],
            "city": b["city"],
            "phone": b["phone"],
            "description": b["description"],
        }
        for _, b in scored[:5]
    ]
    return {"count": len(results), "results": results}

"""רשימת העסקים המותאמת אישית והכלי לחיפוש שנחשף לסוכן ה-ADK."""

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
    """מחפש ברשימת העסקים המותאמת אישית עסקים שמתאימים לצורך של המשתמש.

    יש להשתמש בכלי זה בכל פעם שהמשתמש מחפש עסק, שירות או נותן שירות.
    יש לחלץ את עיקר הצורך אל `query` (טקסט חופשי בעברית), ואם המשתמש
    רמז על קטגוריה ברורה (למשל "מוסך", "אינסטלציה", "מסעדה") יש
    להעביר אותה ב-`category`.

    Args:
        query: תיאור חופשי בעברית של מה שהמשתמש מחפש.
        category: קטגוריית עסק אופציונלית לצמצום החיפוש.

    Returns:
        מילון עם `count` ורשימת `results` של עסקים מתאימים
        (name, category, city, phone, description), הטוב ביותר ראשון.
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

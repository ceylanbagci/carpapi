from __future__ import annotations

import re
from typing import Any

_BODY_WORDS = {"suv": "SUV", "sedan": "Sedan"}

_MAKES: dict[str, str] = {
    "toyota": "Toyota",
    "honda": "Honda",
    "ford": "Ford",
    "chevrolet": "Chevrolet",
    "chevy": "Chevrolet",
    "nissan": "Nissan",
    "hyundai": "Hyundai",
    "kia": "Kia",
    "mazda": "Mazda",
    "subaru": "Subaru",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "bmw": "BMW",
    "mercedes": "Mercedes-Benz",
    "audi": "Audi",
    "lexus": "Lexus",
    "acura": "Acura",
    "infiniti": "Infiniti",
}


def plan_car_query(message: str) -> tuple[dict[str, Any], str]:
    """
    MVP planner: regex + keyword extraction.
    Replace with LLM + constrained tool output (Bedrock) using the same CarQuery JSON schema.
    """
    text = message.strip()
    lower = text.lower()

    q: dict[str, Any] = {
        "make": None,
        "model": None,
        "body_style": None,
        "year_min": None,
        "year_max": None,
        "price_min": None,
        "price_max": None,
        "mileage_max": None,
        "region": None,
        "zip_code": None,
        "radius_miles": None,
        "limit": 10,
        "semantic_query": None,
    }

    if "new jersey" in lower or re.search(r"\bnj\b", lower):
        q["region"] = "NJ"

    zip_match = re.search(r"\b(\d{5})\b", lower)
    if zip_match:
        q["zip_code"] = zip_match.group(1)

    radius_match = re.search(r"(?:within|inside)\s+(\d{1,3})\s*(?:mi|miles?)", lower)
    if not radius_match:
        radius_match = re.search(r"(\d{1,3})\s*(?:mi|miles?)\s+(?:of|from|radius)", lower)
    if radius_match:
        try:
            q["radius_miles"] = float(radius_match.group(1))
        except ValueError:
            pass

    if q["zip_code"] and q["radius_miles"] is None:
        q["radius_miles"] = 50.0

    m = re.search(r"\$(\d{1,3}(?:,\d{3})+|\d+)\s*k?", lower)
    if not m:
        m = re.search(r"(?:under|below|less than)\s*\$?\s*(\d+)\s*k?", lower)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
            if val < 1000:
                val *= 1000
            q["price_max"] = val
        except ValueError:
            pass

    m = re.search(
        r"(?:under|below|less than)\s*(\d{1,3}(?:,\d{3})+|\d+)\s*(k)?\s*miles",
        lower,
    )
    if m:
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
            if m.group(2):
                val *= 1000
            q["mileage_max"] = val
        except ValueError:
            pass

    for word, canon in _MAKES.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            q["make"] = canon
            break

    if "camry" in lower:
        q["make"] = "Toyota"
        q["model"] = "Camry"
    elif "rav4" in lower:
        q["make"] = "Toyota"
        q["model"] = "RAV4"
    elif "cr-v" in lower or "crv" in lower:
        q["make"] = "Honda"
        q["model"] = "CR-V"

    for word, canon in _BODY_WORDS.items():
        if word in lower:
            q["body_style"] = canon

    rationale_parts: list[str] = []
    if q["make"] or q["model"]:
        rationale_parts.append(f"Filtering by {q['make'] or ''} {q['model'] or ''}".strip())
    if q["price_max"]:
        rationale_parts.append(f"price at or below ${q['price_max']:,.0f}")
    if q["mileage_max"]:
        rationale_parts.append(f"mileage up to {q['mileage_max']:,.0f} mi")
    if q["region"]:
        rationale_parts.append(f"region {q['region']}")
    if q["zip_code"] and q["radius_miles"]:
        rationale_parts.append(
            f"within {q['radius_miles']:.0f} mi of {q['zip_code']}"
        )

    rationale = (
        "; ".join(rationale_parts)
        if rationale_parts
        else "Broad search ranked by lowest price (add make/model filters for tighter results)."
    )

    return q, rationale


def rag_placeholder_hint(message: str) -> str | None:
    """Future semantic retrieval hook (embeddings + pgvector)."""
    return message.strip() if len(message.strip()) > 120 else None


# Relaxation order from context/user-chat-style.md:
#   radius_miles → price_max → mileage_max → year_min
# Apply ONE relaxation step at a time; never relax multiple filters in one
# pass (silent over-relaxation is worse than a few zero-result responses).

_RADIUS_MAX = 200.0


def relax_query(q: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    """Relax a CarQuery by one filter, in priority order.

    Returns (relaxed_query, human-readable explanation) or None if there is
    nothing left to relax (caller should surface "no matches; broaden criteria").
    """
    relaxed = dict(q)

    radius = q.get("radius_miles")
    if radius:
        old = float(radius)
        new = min(old * 2, _RADIUS_MAX)
        if new > old:
            relaxed["radius_miles"] = new
            return relaxed, f"expanded search radius from {old:.0f} mi to {new:.0f} mi"
        # Already at the cap — drop the geo filter entirely.
        relaxed["radius_miles"] = None
        relaxed["zip_code"] = None
        return relaxed, "removed location radius"

    price = q.get("price_max")
    if price:
        old = float(price)
        new = round(old * 1.10 / 100) * 100  # nearest $100
        if new <= old:
            new = old + 100
        relaxed["price_max"] = new
        return relaxed, f"raised price ceiling from ${old:,.0f} to ${new:,.0f}"

    mileage = q.get("mileage_max")
    if mileage:
        old = float(mileage)
        new = round(old * 1.20 / 1000) * 1000  # nearest 1k mi
        if new <= old:
            new = old + 1000
        relaxed["mileage_max"] = new
        return relaxed, f"raised mileage ceiling from {old:,.0f} to {new:,.0f} mi"

    year_min = q.get("year_min")
    if year_min is not None:
        old = int(year_min)
        new = old - 1
        relaxed["year_min"] = new
        return relaxed, f"included one earlier model year ({new})"

    return None

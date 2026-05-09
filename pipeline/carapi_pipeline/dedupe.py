from __future__ import annotations

import hashlib
import re
from typing import Any

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def normalize_vin(raw: str | None) -> str | None:
    if not raw:
        return None
    v = raw.strip().upper().replace(" ", "")
    if _VIN_RE.match(v):
        return v
    return None


def _ngrams(text: str, n: int = 3) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.lower().strip())
    if len(cleaned) < n:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def simhash_64(text: str) -> int:
    """64-bit simhash for title+description fuzzy clustering."""
    bits = [0] * 64
    grams = _ngrams(text or "", 3)
    if not grams:
        return 0
    for gram in grams:
        h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
        for i in range(64):
            bits[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if bits[i] >= 0:
            out |= 1 << i
    return out


def _geo_key(doc: dict[str, Any]) -> str:
    lat, lon = doc.get("latitude"), doc.get("longitude")
    if lat is not None and lon is not None:
        try:
            return f"{round(float(lat), 2)}:{round(float(lon), 2)}"
        except (TypeError, ValueError):
            pass
    region = (doc.get("region") or "").strip().lower()
    city = (doc.get("city") or "").strip().lower()
    if region or city:
        return f"{region}|{city}"
    return "unknown"


def price_bucket(price: Any) -> int:
    try:
        if price is None:
            return -1
        return int(float(price) // 500)
    except (TypeError, ValueError):
        return -1


def mileage_bucket(mileage: Any) -> int:
    try:
        if mileage is None:
            return -1
        return int(float(mileage) // 1000)
    except (TypeError, ValueError):
        return -1


def build_dedupe_key(doc: dict[str, Any]) -> str:
    vin = normalize_vin(doc.get("vin"))
    if vin:
        return f"vin:{vin}"

    make = (doc.get("make") or "").strip().lower()
    model = (doc.get("model") or "").strip().lower()
    year = int(doc["year"]) if doc.get("year") is not None else 0
    pb = price_bucket(doc.get("price_amount"))
    mb = mileage_bucket(doc.get("mileage"))
    geo = _geo_key(doc)
    blob = f"{doc.get('title', '')} {(doc.get('description') or '')}"
    sh = simhash_64(blob)
    return f"fp:{sh:016x}:{make}:{model}:{year}:{pb}:{mb}:{geo}"

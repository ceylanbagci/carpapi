"""Nissan adapter — nissanusa.com /vehicles/<category>/<model>.html."""
from __future__ import annotations

from .base import (
    MakerAdapter,
    MakerLookup,
    MakerUnsupported,
    find_sticker_url_in_html,
    harvest_common_specs,
    slug,
    try_url_candidates,
)

BASE = "https://www.nissanusa.com"

MODEL_CATEGORY: dict[str, str] = {
    "altima": "cars",
    "sentra": "cars",
    "versa": "cars",
    "maxima": "cars",
    "z": "cars",
    "gt-r": "cars",
    "leaf": "cars",
    "kicks": "crossovers-suvs",
    "rogue": "crossovers-suvs",
    "rogue-sport": "crossovers-suvs",
    "murano": "crossovers-suvs",
    "pathfinder": "crossovers-suvs",
    "armada": "crossovers-suvs",
    "ariya": "crossovers-suvs",
    "frontier": "trucks",
    "titan": "trucks",
}

CATEGORIES = ["crossovers-suvs", "cars", "trucks"]


class NissanAdapter(MakerAdapter):
    make = "Nissan"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("nissan: no model on listing")
        m = slug(model)
        primary = MODEL_CATEGORY.get(m)
        order = ([primary] if primary else []) + [c for c in CATEGORIES if c != primary]
        candidates = []
        for c in order:
            candidates.append(f"{BASE}/vehicles/{c}/{m}.html")
            candidates.append(f"{BASE}/vehicles/{c}/{m}")
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"nissan: no model page for {model} {year}")
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=harvest_common_specs(
                html, model=model, year=year, trim=trim, vin=vin,
                page_url=url, source="nissanusa.com",
            ),
            raw_html=html if len(html) < 200_000 else None,
        )

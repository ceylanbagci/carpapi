"""Chevrolet adapter — chevrolet.com category/model pages."""
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

BASE = "https://www.chevrolet.com"

MODEL_CATEGORY: dict[str, str] = {
    "camaro": "performance",
    "corvette": "performance",
    "malibu": "cars",
    "trax": "suvs",
    "trailblazer": "suvs",
    "equinox": "suvs",
    "blazer": "suvs",
    "traverse": "suvs",
    "tahoe": "suvs",
    "suburban": "suvs",
    "colorado": "trucks",
    "silverado-1500": "trucks",
    "silverado-2500hd": "trucks",
    "silverado-3500hd": "trucks",
    "silverado-ev": "electric",
    "blazer-ev": "electric",
    "equinox-ev": "electric",
    "bolt-ev": "electric",
    "bolt-euv": "electric",
}

CATEGORIES = ["cars", "suvs", "trucks", "performance", "electric"]


class ChevroletAdapter(MakerAdapter):
    make = "Chevrolet"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("chevy: no model on listing")
        m = slug(model)
        primary = MODEL_CATEGORY.get(m)
        order = ([primary] if primary else []) + [c for c in CATEGORIES if c != primary]
        candidates: list[str] = []
        for c in order:
            if year:
                candidates.append(f"{BASE}/{c}/{m}/{year}/")
            candidates.append(f"{BASE}/{c}/{m}/")
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"chevy: no model page for {model} {year}")
        specs = harvest_common_specs(
            html, model=model, year=year, trim=trim, vin=vin,
            page_url=url, source="chevrolet.com",
        )
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

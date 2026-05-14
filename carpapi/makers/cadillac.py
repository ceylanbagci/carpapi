"""Cadillac adapter — cadillac.com /<category>/<model> (Chevy-like layout)."""
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

BASE = "https://www.cadillac.com"

MODEL_CATEGORY: dict[str, str] = {
    "ct4": "sedans",
    "ct5": "sedans",
    "ct6": "sedans",
    "ct4-v": "sedans",
    "ct5-v": "sedans",
    "ct5-v-blackwing": "sedans",
    "xt4": "suvs",
    "xt5": "suvs",
    "xt6": "suvs",
    "escalade": "suvs",
    "escalade-esv": "suvs",
    "escalade-iq": "electric",
    "escalade-iql": "electric",
    "lyriq": "electric",
    "optiq": "electric",
    "vistiq": "electric",
}

CATEGORIES = ["sedans", "suvs", "electric"]


class CadillacAdapter(MakerAdapter):
    make = "Cadillac"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("cadillac: no model on listing")
        m = slug(model)
        primary = MODEL_CATEGORY.get(m)
        order = ([primary] if primary else []) + [c for c in CATEGORIES if c != primary]
        candidates = []
        for c in order:
            candidates.append(f"{BASE}/{c}/{m}")
            candidates.append(f"{BASE}/{c}/{m}/")
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"cadillac: no model page for {model} {year}")
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=harvest_common_specs(
                html, model=model, year=year, trim=trim, vin=vin,
                page_url=url, source="cadillac.com",
            ),
            raw_html=html if len(html) < 200_000 else None,
        )

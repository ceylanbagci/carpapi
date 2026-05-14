"""Buick adapter — buick.com /suvs/<model> (GM-style layout)."""
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

BASE = "https://www.buick.com"

CATEGORIES = ["suvs", "electric"]  # Buick is SUV-only in 2024+


class BuickAdapter(MakerAdapter):
    make = "Buick"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("buick: no model on listing")
        m = slug(model)
        candidates = []
        for c in CATEGORIES:
            candidates.append(f"{BASE}/{c}/{m}")
            candidates.append(f"{BASE}/{c}/{m}/")
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"buick: no model page for {model} {year}")
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=harvest_common_specs(
                html, model=model, year=year, trim=trim, vin=vin,
                page_url=url, source="buick.com",
            ),
            raw_html=html if len(html) < 200_000 else None,
        )

"""Mazda adapter — mazdausa.com /vehicles/<model>."""
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

BASE = "https://www.mazdausa.com"


class MazdaAdapter(MakerAdapter):
    make = "Mazda"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("mazda: no model on listing")
        m = slug(model)
        candidates = [
            f"{BASE}/vehicles/{m}",
            f"{BASE}/vehicles/{m}/",
            f"{BASE}/{m}",
        ]
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"mazda: no model page for {model} {year}")
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=harvest_common_specs(
                html, model=model, year=year, trim=trim, vin=vin,
                page_url=url, source="mazdausa.com",
            ),
            raw_html=html if len(html) < 200_000 else None,
        )

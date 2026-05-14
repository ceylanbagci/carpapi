"""Volkswagen adapter — vw.com /en/models/<model>.html."""
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

BASE = "https://www.vw.com"


class VolkswagenAdapter(MakerAdapter):
    make = "Volkswagen"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("vw: no model on listing")
        m = slug(model)
        candidates = [
            f"{BASE}/en/models/{m}.html",
            f"{BASE}/en/models/{m}",
            f"{BASE}/models/{m}.html",
        ]
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"vw: no model page for {model} {year}")
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=harvest_common_specs(
                html, model=model, year=year, trim=trim, vin=vin,
                page_url=url, source="vw.com",
            ),
            raw_html=html if len(html) < 200_000 else None,
        )

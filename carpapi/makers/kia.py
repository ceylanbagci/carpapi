"""Kia adapter — kia.com/us/en/<model> (no category segment)."""
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

BASE = "https://www.kia.com/us/en"


class KiaAdapter(MakerAdapter):
    make = "Kia"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("kia: no model on listing")
        m = slug(model)
        candidates = [
            f"{BASE}/{m}",
            f"{BASE}/{m}/",
        ]
        # Hybrid variants typically live at -hybrid/-plug-in-hybrid slugs;
        # we let the dealer's freeform model string carry that through slug().
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"kia: no model page for {model} {year}")
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=harvest_common_specs(
                html, model=model, year=year, trim=trim, vin=vin,
                page_url=url, source="kia.com",
            ),
            raw_html=html if len(html) < 200_000 else None,
        )

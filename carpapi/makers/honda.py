"""Honda adapter — automobiles.honda.com model pages."""
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

BASE = "https://automobiles.honda.com"


class HondaAdapter(MakerAdapter):
    make = "Honda"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("honda: no model on listing")
        m = slug(model)
        candidates = []
        if year:
            candidates += [f"{BASE}/{year}/{m}", f"{BASE}/{m}/{year}"]
        candidates += [f"{BASE}/{m}", f"{BASE}/vehicles/{m}"]
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"honda: no model page for {model} {year}")
        specs = harvest_common_specs(
            html, model=model, year=year, trim=trim, vin=vin,
            page_url=url, source="automobiles.honda.com",
        )
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

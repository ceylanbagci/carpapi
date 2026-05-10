"""Toyota adapter — public model pages on toyota.com."""
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

BASE = "https://www.toyota.com"


class ToyotaAdapter(MakerAdapter):
    make = "Toyota"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("toyota: no model on listing")
        m = slug(model)
        candidates = []
        if year:
            candidates += [f"{BASE}/{m}/{year}/", f"{BASE}/{m}/{year}"]
        candidates += [f"{BASE}/{m}/", f"{BASE}/{m}"]
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"toyota: no model page for {model} {year}")
        specs = harvest_common_specs(
            html, model=model, year=year, trim=trim, vin=vin,
            page_url=url, source="toyota.com",
        )
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

"""Ram adapter — ramtrucks.com flat model pages."""
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

BASE = "https://www.ramtrucks.com"


class RamAdapter(MakerAdapter):
    make = "Ram"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("ram: no model on listing")
        m = slug(model)
        candidates: list[str] = []
        if year:
            candidates += [
                f"{BASE}/{year}/{m}.html",
                f"{BASE}/{m}/{year}.html",
            ]
        candidates += [
            f"{BASE}/{m}.html",
            f"{BASE}/{m}",
        ]
        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"ram: no model page for {model} {year}")
        specs = harvest_common_specs(
            html, model=model, year=year, trim=trim, vin=vin,
            page_url=url, source="ramtrucks.com",
        )
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

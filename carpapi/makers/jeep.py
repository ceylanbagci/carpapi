"""Jeep adapter — jeep.com flat model pages.

Jeep is part of Stellantis. Public marketing pages exist on jeep.com
without auth; per-VIN data on Mopar Owner Connect requires login and
is not attempted.
"""
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

BASE = "https://www.jeep.com"


class JeepAdapter(MakerAdapter):
    make = "Jeep"
    # jeep.com returns 403 for plain HTTP user agents (Stellantis-wide
    # bot wall). Mark unsupported until a headless-browser fallback
    # ships; the orchestrator marks rows sticky and skips them.
    supported = False

    def lookup(self, *, vin, make, model, year, trim):
        raise MakerUnsupported(
            "jeep: jeep.com requires a headless browser (Stellantis bot wall)"
        )
        # Unreachable; kept for future re-enable.
        if not model:
            raise MakerUnsupported("jeep: no model on listing")
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
            raise MakerUnsupported(f"jeep: no model page for {model} {year}")
        specs = harvest_common_specs(
            html, model=model, year=year, trim=trim, vin=vin,
            page_url=url, source="jeep.com",
        )
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

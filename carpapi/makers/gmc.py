"""GMC adapter — gmc.com category/model pages."""
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

BASE = "https://www.gmc.com"

MODEL_CATEGORY: dict[str, str] = {
    "sierra-1500": "commercial",
    "sierra-2500hd": "commercial",
    "sierra-3500hd": "commercial",
    "canyon": "trucks",
    "yukon": "suvs",
    "yukon-xl": "suvs",
    "acadia": "suvs",
    "terrain": "suvs",
    "hummer-ev": "electric",
    "hummer-ev-suv": "electric",
    "sierra-ev": "electric",
}

# Real gmc.com layout: /<category>/<model>, no year, no trailing slash.
#   /suvs/yukon  /suvs/terrain  /trucks/canyon  /electric/sierra-ev
CATEGORIES = ["suvs", "trucks", "electric", "commercial"]


def _split_sierra_paths(m: str) -> list[str]:
    """Sierra full-size pickups: /trucks/sierra/<size> (slash, not hyphen)."""
    if m == "sierra-1500":
        return ["trucks/sierra/1500"]
    if m in ("sierra-2500hd", "sierra-3500hd"):
        return ["trucks/sierra/2500hd-3500hd"]
    return []


class GmcAdapter(MakerAdapter):
    make = "GMC"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("gmc: no model on listing")
        m = slug(model)
        primary = MODEL_CATEGORY.get(m)
        order = ([primary] if primary else []) + [c for c in CATEGORIES if c != primary]

        # gmc.com uses /<category>/<model> with no year/trailing slash.
        candidates: list[str] = []
        for c in order:
            candidates.append(f"{BASE}/{c}/{m}")
            candidates.append(f"{BASE}/{c}/{m}/")
        for sub in _split_sierra_paths(m):
            candidates.insert(0, f"{BASE}/{sub}")
            candidates.insert(1, f"{BASE}/{sub}/")

        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"gmc: no model page for {model} {year}")
        specs = harvest_common_specs(
            html, model=model, year=year, trim=trim, vin=vin,
            page_url=url, source="gmc.com",
        )
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

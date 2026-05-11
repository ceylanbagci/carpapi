"""Chevrolet adapter — chevrolet.com category/model pages."""
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

BASE = "https://www.chevrolet.com"

MODEL_CATEGORY: dict[str, str] = {
    "camaro": "performance",
    "corvette": "performance",
    "malibu": "cars",
    "trax": "suvs",
    "trailblazer": "suvs",
    "equinox": "suvs",
    "blazer": "suvs",
    "traverse": "suvs",
    "tahoe": "suvs",
    "suburban": "suvs",
    "colorado": "trucks",
    "silverado-1500": "commercial",
    "silverado-2500hd": "commercial",
    "silverado-3500hd": "commercial",
    "silverado-ev": "electric",
    "blazer-ev": "electric",
    "equinox-ev": "electric",
    "bolt-ev": "electric",
    "bolt-euv": "electric",
}

# Path layout observed live on chevrolet.com:
#   /suvs/<model>          /suvs/equinox, /suvs/tahoe
#   /trucks/<model>        /trucks/colorado
#   /electric/<model>      /electric/silverado-ev
#   /performance/<model>   /performance/corvette
#   /commercial/silverado/<sub>   ← split-name truck handled below
CATEGORIES = ["suvs", "trucks", "electric", "performance", "cars", "commercial"]


def _split_silverado_paths(m: str) -> list[str]:
    """Chevy filed full-size pickups under /commercial/silverado/<size>/."""
    if m == "silverado-1500":
        return ["commercial/silverado/1500"]
    if m in ("silverado-2500hd", "silverado-3500hd"):
        # Combined page on chevy.com
        return ["commercial/silverado/2500hd-3500hd"]
    return []


class ChevroletAdapter(MakerAdapter):
    make = "Chevrolet"
    supported = True

    def lookup(self, *, vin, make, model, year, trim):
        if not model:
            raise MakerUnsupported("chevy: no model on listing")
        m = slug(model)
        primary = MODEL_CATEGORY.get(m)
        order = ([primary] if primary else []) + [c for c in CATEGORIES if c != primary]

        # Live chevy.com paths are /<category>/<model> with no trailing
        # slash and no year segment.
        candidates: list[str] = []
        for c in order:
            candidates.append(f"{BASE}/{c}/{m}")
            candidates.append(f"{BASE}/{c}/{m}/")
        # Full-size pickups live at /commercial/silverado/<size>/
        for sub in _split_silverado_paths(m):
            candidates.insert(0, f"{BASE}/{sub}")
            candidates.insert(1, f"{BASE}/{sub}/")

        url, html = try_url_candidates(self, candidates, must_mention=model)
        if not html:
            raise MakerUnsupported(f"chevy: no model page for {model} {year}")
        specs = harvest_common_specs(
            html, model=model, year=year, trim=trim, vin=vin,
            page_url=url, source="chevrolet.com",
        )
        return MakerLookup(
            maker_url=url,
            sticker_url=find_sticker_url_in_html(html, vin),
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

"""Audi adapter — CDN-blocked, marked unsupported until a headless-browser
fallback lands.

audiusa.com returns 403 to every plain-HTTP user agent (same wall as
Honda / Jeep / Ram). Bot detection runs above the application layer,
so URL-pattern tuning won't help. The orchestrator marks every Audi
row 'unsupported' and skips them on subsequent runs.
"""
from __future__ import annotations

from .base import MakerAdapter, MakerLookup, MakerUnsupported


class AudiAdapter(MakerAdapter):
    make = "Audi"
    supported = False

    def lookup(self, *, vin, make, model, year, trim):
        raise MakerUnsupported(
            "audi: audiusa.com requires a headless browser (CDN bot wall)"
        )

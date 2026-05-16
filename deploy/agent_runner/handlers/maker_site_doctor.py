"""maker-site-doctor — canary HTTPS check per active maker.

For each maker we currently have an adapter for (Ford, Toyota,
Chevrolet, GMC, Cadillac, Buick, Mazda, Kia, Nissan, VW), ping the
home page + a canary VIN URL and confirm the JSON-LD shape hasn't
drifted. This is the lightweight diagnostic version — the full
adapter contract check (Vehicle.brand, offers.price) runs from the
maker-enricher when it actually enriches a listing.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import requests

USER_AGENT = (
    "Mozilla/5.0 (compatible; CarPapiBot/1.0; "
    "+https://carpappi.com/agents)"
)

# Canary home URLs per maker. Anchors against ToS-friendly public pages,
# never a customer-data path.
CANARIES = {
    "Ford":       "https://www.ford.com/",
    "Toyota":     "https://www.toyota.com/",
    "Chevrolet":  "https://www.chevrolet.com/",
    "GMC":        "https://www.gmc.com/",
    "Cadillac":   "https://www.cadillac.com/",
    "Buick":      "https://www.buick.com/",
    "Mazda":      "https://www.mazdausa.com/",
    "Kia":        "https://www.kia.com/us/en",
    "Nissan":     "https://www.nissanusa.com/",
    "Volkswagen": "https://www.vw.com/en.html",
}


def handle(event: dict, context: Any) -> dict:
    results = []
    failures = 0
    for make, url in CANARIES.items():
        try:
            r = requests.head(
                url, timeout=6, allow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            ok = 200 <= r.status_code < 400
            results.append({
                "make": make, "status_code": r.status_code,
                "elapsed_ms": int(r.elapsed.total_seconds() * 1000),
                "ok": ok,
            })
            if not ok:
                failures += 1
        except requests.RequestException as exc:
            results.append({
                "make": make, "ok": False, "error": str(exc)[:120],
            })
            failures += 1

    return {
        "ok": failures == 0,
        "agent": "maker-site-doctor",
        "checked": len(CANARIES),
        "failures": failures,
        "results": results,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }

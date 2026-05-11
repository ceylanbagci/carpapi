"""Discover window-sticker URLs by scanning dealer VDP pages.

Most manufacturer model pages don't link a Monroney PDF (that data
lives behind owner-portals or on the dealer's site). Dealer.com VDPs,
however, routinely embed a "View Window Sticker" link that points at
the OEM's PSE endpoint. This module fetches each enriched listing's
``listing_url`` and scans the HTML for known sticker URL patterns,
then updates ``listings.window_sticker_url`` so the existing sticker
parser can pick the row up.

Idempotent: only touches rows where ``window_sticker_url IS NULL``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests

from . import db

log = logging.getLogger(__name__)

USER_AGENT = "CarPapiBot/0.1 (+https://github.com/ceylanbagci/carpapi)"
TIMEOUT = 20

# Ordered most-specific → most-general. Each pattern returns the URL we
# should resolve relative to the listing page.
SIGNATURE_PATTERNS: list[re.Pattern] = [
    # Ford PSE — known endpoint shape, very stable
    re.compile(
        r'href=[\'"]([^\'"]*?/api/legacy/pse/windowsticker/[^\'"]+)[\'"]',
        re.I,
    ),
    # Generic "windowsticker" / "monroney" anywhere in the URL
    re.compile(
        r'href=[\'"]([^\'"]*?(?:window-?sticker|monroney)[^\'"]*?)[\'"]',
        re.I,
    ),
]

# VIN-bearing PDF link — last resort. We require the VIN to appear in
# the URL so we don't accidentally pick up a brochure or warranty PDF.
VIN_PDF_PATTERN = re.compile(
    r'href=[\'"]([^\'"]*?\.pdf[^\'"]*?)[\'"]',
    re.I,
)


@dataclass
class Discovery:
    vin: str
    listing_url: str
    sticker_url: str | None
    raw_match: str | None  # the raw href captured (relative or absolute)


def _scan_html(html: str, vin: str | None = None) -> tuple[str | None, str | None]:
    """Return (raw href, source label) of the first matching sticker URL."""
    for pat in SIGNATURE_PATTERNS:
        m = pat.search(html)
        if m:
            return m.group(1), pat.pattern[:60]
    if vin:
        for m in VIN_PDF_PATTERN.finditer(html):
            href = m.group(1)
            if vin.lower() in href.lower():
                return href, "vin_pdf"
    return None, None


def _resolve(base: str, raw: str) -> str:
    href = raw.replace("&amp;", "&")
    return urljoin(base, href)


def find_for_listing(
    session: requests.Session,
    listing: db.ListingRow,
) -> Discovery:
    """Fetch one VDP, return what we found (or None)."""
    if not listing.listing_url:
        return Discovery(listing.vin, listing.listing_url or "", None, None)
    try:
        r = session.get(listing.listing_url, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        log.warning("discover %s: VDP fetch failed: %s", listing.vin, e)
        return Discovery(listing.vin, listing.listing_url, None, None)

    raw, _ = _scan_html(r.text, listing.vin)
    if not raw:
        return Discovery(listing.vin, listing.listing_url, None, None)

    return Discovery(
        vin=listing.vin,
        listing_url=listing.listing_url,
        sticker_url=_resolve(listing.listing_url, raw),
        raw_match=raw,
    )


def find_pending_for_discovery(
    cur,
    *,
    make: str | None,
    limit: int,
) -> list[db.ListingRow]:
    """Listings with maker_specs filled but no sticker URL yet."""
    sql = """
        SELECT id, vin, make, model, year, trim, listing_url,
               maker_specs, window_sticker, window_sticker_url,
               maker_enrich_status, price_amount
        FROM public.listings
        WHERE listing_url IS NOT NULL
          AND maker_specs IS NOT NULL
          AND window_sticker_url IS NULL
    """
    params = []
    if make:
        sql += " AND lower(make) = lower(%s)"
        params.append(make)
    sql += " ORDER BY scraped_at DESC NULLS LAST LIMIT %s"
    params.append(limit)
    cur.execute(sql, params)
    return [db.ListingRow(*r) for r in cur.fetchall()]


def run(*, make: str | None, limit: int) -> dict[str, int]:
    """Discover sticker URLs for up to ``limit`` listings of ``make``."""
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    with db.connect() as conn, conn.cursor() as cur:
        rows = find_pending_for_discovery(cur, make=make, limit=limit)

    counts = {"scanned": 0, "found": 0, "missed": 0, "errors": 0}
    print(f"discover-stickers: scanning {len(rows)} VDPs (make={make or 'all'}, limit={limit})")

    for i, listing in enumerate(rows, 1):
        counts["scanned"] += 1
        d = find_for_listing(sess, listing)
        if d.sticker_url:
            counts["found"] += 1
            print(f"  [{i:3}/{len(rows)}] ✓ {listing.vin}  -> {d.sticker_url[:140]}")
            with db.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.listings SET window_sticker_url=%s WHERE id=%s",
                    (d.sticker_url, listing.id),
                )
                conn.commit()
        else:
            counts["missed"] += 1
            print(f"  [{i:3}/{len(rows)}] — {listing.vin}  no sticker link on VDP")

    print()
    print("summary:", "  ".join(f"{k}={v}" for k, v in counts.items()))
    return counts

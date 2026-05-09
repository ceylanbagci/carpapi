from __future__ import annotations

"""Dealer.com adapter — Vehicle JSON-LD extractor.

Strategy:
  1. Fetch listing/inventory page once.
  2. If listing has Vehicle JSON-LD on it, harvest from there.
  3. Otherwise, parse anchors for Vehicle Detail Page (VDP) links — those
     URLs contain a 17-char VIN-shaped substring on Dealer.com — fetch
     each, extract the page's Vehicle JSON-LD.
  4. Map the schema.org Vehicle JSON-LD to a canonical CarListing dict
     that passes schema/car_listing.schema.json validation.

This module is a pure parser — IT DOES NOT decide to scrape. The caller
(carpapi.scrapers.runner) checks robots.txt and per-dealer ToS posture
first, then hands HTML / URLs to this adapter.

Per project policy:
  - Approved stack only: requests + BeautifulSoup4. No LLM.
  - Per-host throttling enforced by the runner, not here.
  - Identifiable User-Agent (browser-shaped but tagged with CarPapiBot).
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Iterator, Optional
from urllib.parse import urljoin, urlparse

log = logging.getLogger(__name__)

DOMAIN_SIGNAL = "dealer.com"

# A clearly-tagged but browser-shaped UA. The CarPapiBot suffix keeps us
# honest if a sysadmin reads logs; the Mozilla prefix prevents reflexive
# 403s from CDN bot defenses that block raw "python-requests/X.Y.Z".
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) CarPapiBot/0.1 "
    "(+https://github.com/ceylanbagci/carpapi)"
)

# Vehicle-detail URL pattern. Dealer.com VDPs are
#   /<status>/Year-Make-Model-...-VIN.htm
# Where VIN is the 17-char alphanumeric (excluding I, O, Q).
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_JSONLD_BLOCK_RE = re.compile(
    r'<script\s+[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_VEHICLE_TYPES = {"Vehicle", "Car", "Motorcycle", "MotorVehicle"}


# --------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------- #


@dataclass
class FetchedPage:
    url: str
    status: int
    html: str
    fetched_at_iso: str
    error: Optional[str] = None


# --------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------- #


def fetch(url: str, *, timeout: float = 20.0, max_bytes: int = 1_500_000) -> FetchedPage:
    """Single GET. Caps body size and times out aggressively."""
    import datetime as dt
    import requests  # noqa: PLC0415

    iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            allow_redirects=True,
            stream=True,
        )
    except requests.RequestException as exc:
        return FetchedPage(url=url, status=0, html="", fetched_at_iso=iso, error=f"{type(exc).__name__}: {exc}")

    body = b""
    try:
        for chunk in resp.iter_content(chunk_size=16_384, decode_unicode=False):
            body += chunk
            if len(body) >= max_bytes:
                break
    finally:
        resp.close()

    encoding = resp.encoding or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")

    err = None if resp.ok else f"HTTP {resp.status_code}"
    return FetchedPage(
        url=str(resp.url),
        status=resp.status_code,
        html=text,
        fetched_at_iso=iso,
        error=err,
    )


# --------------------------------------------------------------------- #
# JSON-LD extraction
# --------------------------------------------------------------------- #


def _jsonld_objects(html: str) -> list[Any]:
    """Pull every JSON-LD block; return the parsed objects, skipping garbage."""
    out: list[Any] = []
    for raw in _JSONLD_BLOCK_RE.findall(html):
        text = raw.strip()
        for candidate in (text, text.replace("&quot;", '"')):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            out.append(obj)
            break
    return out


def _walk_vehicle_nodes(node: Any) -> Iterator[dict]:
    """Yield every Vehicle/Car-typed dict in the JSON-LD tree."""
    if isinstance(node, dict):
        t = node.get("@type")
        types: list[str] = []
        if isinstance(t, str):
            types = [t]
        elif isinstance(t, list):
            types = [s for s in t if isinstance(s, str)]
        if any(s in _VEHICLE_TYPES for s in types):
            yield node
        for v in node.values():
            yield from _walk_vehicle_nodes(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_vehicle_nodes(v)


def vehicles_in_html(html: str) -> list[dict]:
    """Return every Vehicle/Car schema.org node found in the page's JSON-LD."""
    out: list[dict] = []
    for obj in _jsonld_objects(html):
        out.extend(_walk_vehicle_nodes(obj))
    return out


# --------------------------------------------------------------------- #
# VDP discovery from a listing page
# --------------------------------------------------------------------- #


def vdp_links_in_html(html: str, base_url: str) -> list[str]:
    """Return same-host hrefs that look like Vehicle Detail Pages on
    Dealer.com. Heuristic: contains a 17-char VIN-shaped substring AND
    ends with .htm/.html. De-duped, capped to 100."""
    seen: list[str] = []
    seen_set: set[str] = set()
    base_host = urlparse(base_url).hostname or ""

    for m in re.finditer(r'href="([^"#?]+)"', html, re.IGNORECASE):
        href = m.group(1).strip()
        if not href:
            continue
        joined = urljoin(base_url, href)
        if not joined.startswith(("http://", "https://")):
            continue
        if urlparse(joined).hostname != base_host:
            continue
        if not _VIN_RE.search(joined):
            continue
        if not re.search(r"\.html?(\?|$)", joined, re.IGNORECASE):
            continue
        if joined in seen_set:
            continue
        seen.append(joined)
        seen_set.add(joined)
        if len(seen) >= 100:
            break
    return seen


# --------------------------------------------------------------------- #
# Mapping schema.org → canonical CarListing
# --------------------------------------------------------------------- #


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return str(v)


def _safe_number(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        cleaned = re.sub(r"[^\d.]", "", v)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _safe_int(v: Any) -> Optional[int]:
    n = _safe_number(v)
    return int(n) if n is not None else None


def _extract_make(node: dict) -> Optional[str]:
    m = node.get("manufacturer") or node.get("brand")
    if isinstance(m, dict):
        return _safe_str(m.get("name"))
    return _safe_str(m)


def _extract_offer(node: dict) -> tuple[Optional[float], Optional[str]]:
    """Return (price, currency) from a Vehicle's offers field."""
    offers = node.get("offers")
    if offers is None:
        return None, None
    if isinstance(offers, list):
        offer = offers[0] if offers else None
    else:
        offer = offers
    if not isinstance(offer, dict):
        return None, None
    price = _safe_number(offer.get("price"))
    currency = _safe_str(offer.get("priceCurrency")) or "USD"
    return price, currency


def _extract_mileage(node: dict) -> tuple[Optional[float], str]:
    """schema.org mileageFromOdometer is a QuantitativeValue."""
    raw = node.get("mileageFromOdometer")
    if raw is None:
        return None, "unknown"
    if isinstance(raw, dict):
        value = _safe_number(raw.get("value"))
        unit = (raw.get("unitCode") or "").upper()
        # SMI = statute miles, KMT = kilometers per UN/CEFACT
        unit_canon = {"SMI": "mi", "KMT": "km", "MILE": "mi", "KILOMETER": "km"}.get(unit, "unknown")
        return value, unit_canon
    return _safe_number(raw), "unknown"


def vehicle_node_to_listing(
    node: dict,
    *,
    source_id: str,
    source_name: str,
    listing_url: str,
    fetched_at_iso: str,
    seller_name: Optional[str] = None,
    seller_type: Optional[str] = None,
    region: Optional[str] = None,
    city: Optional[str] = None,
) -> Optional[dict]:
    """Map a schema.org Vehicle node to a canonical CarListing dict.

    Returns None when the node is missing the minimum we need to
    fingerprint a listing (no VIN, no usable name).
    """
    vin = _safe_str(node.get("vehicleIdentificationNumber"))

    # Try several places for "name": the @name, the page title-ish field,
    # or constructed from year/make/model.
    name = _safe_str(node.get("name"))
    year = _safe_int(node.get("modelDate") or node.get("vehicleModelDate") or node.get("productionDate"))
    make = _extract_make(node)
    model = _safe_str(node.get("model"))
    if isinstance(node.get("model"), dict):
        model = _safe_str(node["model"].get("name"))
    trim = _safe_str(node.get("vehicleConfiguration") or node.get("trim"))
    body = _safe_str(node.get("bodyType"))

    if not name and (year or make or model):
        name = " ".join(str(p) for p in [year, make, model, trim] if p)

    # Need an external_id even when VIN is missing.
    external_id = vin or _safe_str(node.get("@id")) or _safe_str(node.get("sku")) or None
    if external_id is None:
        # Fall back to the URL itself as a stable key.
        external_id = listing_url

    if not name:
        # No way to identify the car; reject.
        return None

    price, currency = _extract_offer(node)
    mileage, mileage_unit = _extract_mileage(node)

    return {
        "source_id": source_id,
        "source_name": source_name,
        "external_id": external_id,
        "listing_url": listing_url,
        "title": name,
        "description": _safe_str(node.get("description")),
        "make": make,
        "model": model,
        "trim": trim,
        "year": year,
        "body_style": body,
        "vin": vin,
        "mileage": mileage,
        "mileage_unit": mileage_unit,
        "price_amount": price,
        "currency": currency or "USD",
        "seller_name": seller_name,
        "seller_type": seller_type,
        "region": region,
        "city": city,
        "scraped_at": fetched_at_iso,
    }


# --------------------------------------------------------------------- #
# High-level adapter API
# --------------------------------------------------------------------- #


def parse_listing_page(
    page: FetchedPage,
    *,
    source_id: str,
    source_name: str,
    region: Optional[str] = None,
    city: Optional[str] = None,
) -> tuple[list[dict], list[str]]:
    """Return (canonical listings found inline, VDP URLs to follow next)."""
    if page.html is None or page.error:
        return [], []
    inline = []
    for node in vehicles_in_html(page.html):
        listing = vehicle_node_to_listing(
            node,
            source_id=source_id,
            source_name=source_name,
            listing_url=page.url,
            fetched_at_iso=page.fetched_at_iso,
            region=region,
            city=city,
        )
        if listing is not None:
            inline.append(listing)
    vdps = vdp_links_in_html(page.html, page.url)
    return inline, vdps


def parse_vdp(
    page: FetchedPage,
    *,
    source_id: str,
    source_name: str,
    region: Optional[str] = None,
    city: Optional[str] = None,
) -> Optional[dict]:
    """Return canonical listing extracted from a VDP, or None."""
    if page.html is None or page.error:
        return None
    nodes = vehicles_in_html(page.html)
    if not nodes:
        return None
    # Prefer the node that has a VIN in vehicleIdentificationNumber.
    nodes.sort(key=lambda n: 0 if n.get("vehicleIdentificationNumber") else 1)
    for node in nodes:
        listing = vehicle_node_to_listing(
            node,
            source_id=source_id,
            source_name=source_name,
            listing_url=page.url,
            fetched_at_iso=page.fetched_at_iso,
            region=region,
            city=city,
        )
        if listing is not None:
            return listing
    return None

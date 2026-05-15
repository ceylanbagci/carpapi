"""Extract the first image URL from a dealer listing page.

Strategy (in order — first hit wins):
  1. JSON-LD `application/ld+json` blocks → schema.org Vehicle/Product
     payloads almost always include an `image` field. Used by Dealer.com,
     Dealer Inspire, DealerOn, and most CMS-driven dealer platforms.
  2. Open Graph `<meta property="og:image" content="...">` — the
     fallback when the dealer page is single-page JS rendered.
  3. First `<img>` element whose `src` looks like a vehicle photo
     (filename hints, size-class heuristics). Last-resort.

Honors `context/scraper-rules.md`: User-Agent header identifying
CarPapi, no concurrent requests per host, 1.5s sleep between
hits when iterating from the CLI.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("carpapi.images.extractor")

USER_AGENT = "CarPapiImageBot/1.0 (+https://carpapi.app/about; contact@carpapi.app)"
REQUEST_TIMEOUT = 12  # seconds


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def fetch_listing_html(listing_url: str) -> str:
    """GET the listing page. Returns body text; empty string on error."""
    try:
        r = requests.get(
            listing_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if r.status_code >= 400:
            log.info("fetch %s → HTTP %s", listing_url, r.status_code)
            return ""
        return r.text
    except requests.RequestException as exc:
        log.info("fetch %s → %s", listing_url, exc)
        return ""


def first_image_url(html: str, base_url: str) -> Optional[str]:
    """Pull the strongest signal first-image URL out of a dealer page."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for resolver in (_from_jsonld, _from_open_graph, _from_first_img):
        url = resolver(soup)
        if url:
            absolute = urljoin(base_url, url)
            if _looks_like_image_url(absolute):
                return absolute
    return None


# ─────────────────────────────────────────────────────────────────────
# Resolvers
# ─────────────────────────────────────────────────────────────────────

def _from_jsonld(soup: BeautifulSoup) -> Optional[str]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.string or tag.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        for candidate in _walk_jsonld(data):
            url = _pick_image_field(candidate)
            if url:
                return url
    return None


def _walk_jsonld(node) -> Iterable[dict]:
    if isinstance(node, dict):
        # @graph is a common wrapper for multiple typed nodes
        if "@graph" in node and isinstance(node["@graph"], list):
            for sub in node["@graph"]:
                yield from _walk_jsonld(sub)
        yield node
        for v in node.values():
            yield from _walk_jsonld(v)
    elif isinstance(node, list):
        for sub in node:
            yield from _walk_jsonld(sub)


def _pick_image_field(node) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    typ = node.get("@type") or ""
    if isinstance(typ, list):
        typ = ",".join(typ)
    interesting = ("Vehicle", "Product", "Car", "Offer", "AutoDealer")
    img = node.get("image")
    if img is None:
        return None
    if isinstance(img, str):
        if not typ or any(t in typ for t in interesting):
            return img
    elif isinstance(img, list) and img:
        first = img[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url") or first.get("contentUrl")
    elif isinstance(img, dict):
        return img.get("url") or img.get("contentUrl")
    return None


def _from_open_graph(soup: BeautifulSoup) -> Optional[str]:
    for prop in ("og:image:secure_url", "og:image:url", "og:image"):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
    # twitter:image as a final OG-tier fallback
    tag = soup.find("meta", attrs={"name": "twitter:image"})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


_IMG_NAME_RE = re.compile(
    r"(vehicle|inventory|stock|car|auto|hero|main|primary|featured)",
    re.IGNORECASE,
)


def _from_first_img(soup: BeautifulSoup) -> Optional[str]:
    """Pick the first <img> whose src / class / alt suggests it's the car."""
    candidates: list[tuple[int, str]] = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not src:
            continue
        if _looks_like_placeholder(src):
            continue
        score = 0
        if _IMG_NAME_RE.search(src):
            score += 3
        classes = " ".join(img.get("class") or [])
        if _IMG_NAME_RE.search(classes):
            score += 2
        alt = (img.get("alt") or "")
        if _IMG_NAME_RE.search(alt):
            score += 1
        # Reject very small (icon-sized) images.
        w = _to_int(img.get("width"))
        h = _to_int(img.get("height"))
        if w and w < 200:
            continue
        if h and h < 100:
            continue
        candidates.append((score, src))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _to_int(s) -> int:
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return 0


_PLACEHOLDER_HINTS = ("placeholder", "no-image", "noimage", "spinner", "loading", "data:image/svg")


def _looks_like_placeholder(url: str) -> bool:
    low = url.lower()
    return any(h in low for h in _PLACEHOLDER_HINTS)


_IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif)(\?|$)", re.IGNORECASE)


def _looks_like_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    if _IMAGE_EXT_RE.search(parsed.path):
        return True
    # Some dealer CDNs serve images via query-based URLs without an
    # extension — accept them too as long as the path looks vehicle-y.
    if _IMG_NAME_RE.search(parsed.path):
        return True
    return False

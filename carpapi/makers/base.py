"""Manufacturer adapter base class.

Each per-make adapter implements ``lookup()`` and returns a
:class:`MakerLookup` containing the canonical maker page URL, the
parsed factory specs, and (if discoverable) a window-sticker PDF URL.

Adapters share a polite ``requests.Session``: a single User-Agent,
per-instance rate limiting between requests, sane timeouts, and a
size cap. None of this requires the existing Scrapy/runner code.
"""
from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests

log = logging.getLogger(__name__)

USER_AGENT = "CarPapiBot/0.1 (+https://github.com/ceylanbagci/carpapi)"
DEFAULT_TIMEOUT = 15
MAX_BYTES = 8_000_000  # modern manufacturer pages with hero videos and embedded data routinely exceed 2MB


class MakerError(Exception):
    """Catch-all for adapter problems the caller can record on the row."""


class MakerUnsupported(MakerError):
    """The make has no public per-VIN endpoint, or we couldn't derive a URL.

    The orchestrator records ``maker_enrich_status='unsupported'`` and
    won't retry the row.
    """


class MakerLoginRequired(MakerError):
    """The endpoint we landed on demands authentication.

    Sticky in the same way as :class:`MakerUnsupported` — we don't try
    to bypass auth.
    """


@dataclass
class MakerLookup:
    """One adapter run's worth of output."""

    maker_url: str | None = None
    sticker_url: str | None = None
    specs: dict[str, Any] = field(default_factory=dict)
    raw_html: str | None = None


class MakerAdapter(ABC):
    """One adapter per manufacturer.

    Subclasses set ``make`` and may override ``rate_limit_seconds`` /
    ``supported`` (set ``False`` to short-circuit immediately, e.g.
    login-only sites). The required method is :meth:`lookup`.
    """

    make: str = ""
    supported: bool = True
    rate_limit_seconds: float = 1.5

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.7",
            }
        )
        self._last_request_at = 0.0

    def fetch(
        self,
        url: str,
        *,
        accept: str | None = None,
        allow_redirects: bool = True,
    ) -> requests.Response:
        """Polite GET. Sleeps between requests to honour the per-host
        rate limit and bails on responses larger than ``MAX_BYTES``.
        """
        wait = self.rate_limit_seconds - (time.time() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.time()

        headers = {}
        if accept:
            headers["Accept"] = accept

        with self.session.get(
            url,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=allow_redirects,
            stream=True,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            length = int(resp.headers.get("Content-Length", "0") or 0)
            if length and length > MAX_BYTES:
                raise MakerError(f"response too large ({length} bytes) at {url}")
            content = b""
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                content += chunk
                if len(content) > MAX_BYTES:
                    raise MakerError(f"response too large (>{MAX_BYTES}B) at {url}")
            resp._content = content
            return resp

    @abstractmethod
    def lookup(
        self,
        *,
        vin: str,
        make: str,
        model: str | None,
        year: int | None,
        trim: str | None,
    ) -> MakerLookup:
        """Given a VIN and (optionally) the dealer-known shape, return
        whatever the maker site exposes for this car.

        Adapters should:

          1. Try a VIN-keyed lookup if one exists.
          2. Fall back to a (model, year, trim) lookup on the public
             maker site so we still get factory-canonical trim specs
             when no VIN endpoint is available.

        Raise :class:`MakerUnsupported` if neither path is reachable.
        """


# --------------------------------------------------------------------- #
# Small helpers shared by adapters
# --------------------------------------------------------------------- #


def slug(text: str) -> str:
    """make/model/trim → URL slug. ``"F-150 Lightning"`` -> ``"f-150-lightning"``."""
    s = (text or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def first_match(text: str, *patterns: str) -> str | None:
    for p in patterns:
        m = re.search(p, text, flags=re.I | re.S)
        if m:
            return m.group(1).strip()
    return None


def harvest_common_specs(
    html: str,
    *,
    model: str,
    year: int | None,
    trim: str | None,
    vin: str,
    page_url: str,
    source: str,
) -> dict[str, Any]:
    """Parse the universal subset of fields most maker pages publish:
    title / og description / JSON-LD Vehicle nodes / starting MSRP /
    city-hwy MPG. Adapters can extend the result with maker-specific
    fields."""
    import json

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    specs: dict[str, Any] = {
        "source": source,
        "page_url": page_url,
        "model": model,
        "year": year,
        "trim_dealer_reported": trim,
        "vin": vin,
        "vin_match": "model_only",
    }

    title = soup.find("title")
    if title and title.text:
        specs["page_title"] = title.text.strip()

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        specs.setdefault("page_title", og_title["content"])
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        specs["description"] = og_desc["content"]

    for script in soup.find_all("script", type="application/ld+json"):
        blob = (script.string or "").strip()
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except Exception:
            continue
        for node in (data if isinstance(data, list) else [data]):
            if not isinstance(node, dict):
                continue
            for k, jk in (
                ("vehicle_engine", "vehicleEngine"),
                ("transmission", "vehicleTransmission"),
                ("drivetrain", "driveWheelConfiguration"),
                ("body_style", "bodyType"),
                ("fuel_type", "fuelType"),
                ("seating_capacity", "vehicleSeatingCapacity"),
            ):
                v = node.get(jk)
                if v and k not in specs:
                    specs[k] = v.get("name") if isinstance(v, dict) else v
            offers = node.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
                if price and "starting_msrp" not in specs:
                    try:
                        specs["starting_msrp"] = int(float(price))
                    except (TypeError, ValueError):
                        pass

    body = soup.get_text(" ", strip=True)
    msrp = first_match(
        body,
        r"Starting\s+(?:MSRP|at)[^\$]{0,30}\$([\d,]+)",
        r"MSRP[^\$]{0,30}\$([\d,]+)",
        r"\$([\d,]+)\s*Starting",
    )
    if msrp and "starting_msrp" not in specs:
        try:
            specs["starting_msrp"] = int(msrp.replace(",", ""))
        except ValueError:
            pass

    mpg = re.search(r"(\d{1,2})\s*city\s*/\s*(\d{1,2})\s*hwy", body, re.I)
    if mpg:
        specs["mpg_city"] = int(mpg.group(1))
        specs["mpg_hwy"] = int(mpg.group(2))

    return specs


def find_sticker_url_in_html(html: str, vin: str | None) -> str | None:
    """Best-effort: look for any href that screams 'Monroney PDF'."""
    for m in re.finditer(
        r'href=["\']([^"\']+(?:window-?sticker|monroney|window-label)[^"\']*\.pdf[^"\']*)["\']',
        html,
        re.I,
    ):
        return m.group(1)
    if vin:
        m = re.search(
            rf'href=["\']([^"\']*{re.escape(vin)}[^"\']*\.pdf[^"\']*)["\']',
            html,
            re.I,
        )
        if m:
            return m.group(1)
    return None


def try_url_candidates(
    adapter: "MakerAdapter",
    candidates: list[str],
    *,
    must_mention: str | list[str] | None = None,
) -> tuple[str, str | None]:
    """Try each URL in order, return the first response that looks like
    a real page about the model.

    ``must_mention`` is a model name (or list of acceptable strings) the
    page's title / og:title must contain — guards against silent
    redirects to a generic landing page.
    """
    needles: list[str] = []
    if isinstance(must_mention, str):
        needles = [must_mention.lower()]
    elif isinstance(must_mention, list):
        needles = [n.lower() for n in must_mention if n]

    for url in candidates:
        try:
            resp = adapter.fetch(url)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 410):
                continue
            log.debug("%s: HTTP error on %s: %s", adapter.make, url, e)
            continue
        except Exception as e:
            log.debug("%s: error on %s: %s", adapter.make, url, e)
            continue
        text = resp.text
        if "page-not-found" in text.lower() or len(text) <= 500:
            continue

        if needles:
            # Pull the page's title + og:title — quick text check, no full parse.
            head = text[:6000].lower()
            title_match = re.search(
                r'<title[^>]*>(.*?)</title>|property=["\']og:title["\']\s+content=["\']([^"\']+)',
                head,
                re.S,
            )
            blob = ""
            if title_match:
                blob = " ".join(g for g in title_match.groups() if g).lower()
            if not any(n in blob for n in needles):
                log.debug(
                    "%s: %s landed on a page whose title doesn't match model (%r); "
                    "title was %r",
                    adapter.make, url, needles, blob[:120],
                )
                continue

        return url, text
    return "", None

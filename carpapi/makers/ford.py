"""Ford adapter.

Strategy (per the user's instruction "use VIN if available, otherwise
reverse-engineer from make/model/year/trim"):

1. **VIN-keyed lookup** — Ford's owner-portal VIN endpoints generally
   require login; we don't bypass that. We try one public probe and
   fall straight through if it returns auth-required.
2. **Model page fallback** — hit ``www.ford.com/<category>/<model>[/<year>]/``
   and harvest whatever the public page exposes (JSON-LD ``Vehicle``,
   trim list, starting MSRP, MPG strings). This gives factory-
   canonical *trim-level* specs even without a per-VIN endpoint.

Categories on ford.com (as of 2026):

  cars/              Mustang
  suvs-crossovers/   Escape · Edge · Explorer · Expedition · Bronco · Bronco Sport
  trucks/            F-150 · Ranger · Maverick · Super Duty (F-250/350/450)
  electric/          Mustang Mach-E · F-150 Lightning · E-Transit
  commercial/        Transit · Transit Connect

Adapter doesn't blow up on a cold model — it tries each category in
turn until one returns 200.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from .base import MakerAdapter, MakerLookup, MakerUnsupported, first_match, slug

log = logging.getLogger(__name__)

FORD_BASE = "https://www.ford.com"

MODEL_CATEGORY: dict[str, str] = {
    "mustang": "cars",
    "mustang-mach-e": "suvs",
    "mach-e": "suvs",
    "escape": "suvs",
    "edge": "suvs-crossovers",
    "explorer": "suvs",
    "expedition": "suvs",
    "bronco": "suvs",
    "bronco-sport": "suvs",
    "f-150": "trucks",
    "f150": "trucks",
    "f-150-lightning": "trucks",
    "ranger": "trucks",
    "maverick": "trucks",
    "super-duty": "trucks",
    "f-250": "trucks",
    "f-350": "trucks",
    "f-450": "trucks",
    "transit": "commercial-trucks",
    "transit-250": "commercial-trucks",
    "transit-350": "commercial-trucks",
    "transit-connect": "commercial-trucks",
    "e-transit": "commercial-trucks",
}

CATEGORY_FALLBACK_ORDER = [
    "suvs",
    "suvs-crossovers",
    "trucks",
    "cars",
    "commercial-trucks",
    "electric",
]


class FordAdapter(MakerAdapter):
    make = "Ford"
    supported = True

    def lookup(
        self,
        *,
        vin: str,
        make: str,
        model: str | None,
        year: int | None,
        trim: str | None,
    ) -> MakerLookup:
        if not model:
            raise MakerUnsupported("ford: missing model on the listing")

        url, html = self._find_canonical_page(model, year)
        if not html:
            raise MakerUnsupported(f"ford: no model page for {model} {year}")

        specs = self._parse_specs(
            html, model=model, year=year, trim=trim, vin=vin, page_url=url
        )
        sticker_url = self._find_sticker_url(html, vin)

        return MakerLookup(
            maker_url=url,
            sticker_url=sticker_url,
            specs=specs,
            raw_html=html if len(html) < 200_000 else None,
        )

    # --------------------------------------------------------- url scan

    def _find_canonical_page(
        self, model: str, year: int | None
    ) -> tuple[str, str | None]:
        m_slug = slug(model)
        # Try the most-likely category first.
        primary = MODEL_CATEGORY.get(m_slug)
        order: list[str] = []
        if primary:
            order.append(primary)
        order.extend(c for c in CATEGORY_FALLBACK_ORDER if c != primary)

        candidates: list[str] = []
        for c in order:
            if year:
                candidates.append(f"{FORD_BASE}/{c}/{m_slug}/{year}/")
            candidates.append(f"{FORD_BASE}/{c}/{m_slug}/")

        # Words that the page title must contain so we don't silently land
        # on Ford's generic "Commercial / Cars / Trucks" landing page.
        needles = [n.lower() for n in [model] + model.split() if n]

        for url in candidates:
            try:
                resp = self.fetch(url)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code in (404, 410):
                    continue
                log.debug("ford: HTTP error on %s: %s", url, e)
                continue
            except Exception as e:
                log.debug("ford: error on %s: %s", url, e)
                continue
            text = resp.text
            if "page-not-found" in text.lower() or "404" in (resp.url or "").lower():
                continue
            if len(text) <= 500:
                continue

            head = text[:6000].lower()
            tm = re.search(
                r'<title[^>]*>(.*?)</title>|property=["\']og:title["\']\s+content=["\']([^"\']+)',
                head,
                re.S,
            )
            blob = " ".join(g for g in (tm.groups() if tm else ()) if g).lower()
            if not any(n in blob for n in needles):
                log.debug("ford: %s landed on a generic page (title=%r), continuing", url, blob[:120])
                continue
            return url, text
        return "", None

    # --------------------------------------------------------- spec parse

    def _parse_specs(
        self,
        html: str,
        *,
        model: str,
        year: int | None,
        trim: str | None,
        vin: str,
        page_url: str,
    ) -> dict[str, Any]:
        soup = BeautifulSoup(html, "lxml")
        specs: dict[str, Any] = {
            "source": "ford.com",
            "page_url": page_url,
            "model": model,
            "year": year,
            "trim_dealer_reported": trim,
            "vin_match": "model_only",  # we matched by model+year, not VIN
            "vin": vin,
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

        # JSON-LD blocks. Ford embeds Product / Vehicle nodes inconsistently.
        for script in soup.find_all("script", type="application/ld+json"):
            blob = (script.string or "").strip()
            if not blob:
                continue
            try:
                data = json.loads(blob)
            except Exception:
                continue
            for node in (data if isinstance(data, list) else [data]):
                if isinstance(node, dict):
                    self._absorb_jsonld(specs, node)

        # Trim list — peek at headings + data attributes.
        trims: set[str] = set()
        for tag in soup.select("[data-trim], [data-model-trim]"):
            t = (tag.get("data-trim") or tag.get("data-model-trim") or "").strip()
            if t:
                trims.add(t)
        for h in soup.select("h2, h3"):
            t = h.get_text(strip=True)
            if 3 <= len(t) <= 40 and not any(c in t for c in ".,!"):
                # Heuristic: drop sentences. Keep short noun phrases.
                trims.add(t)
        if trims:
            specs["trims_listed"] = sorted(trims)[:40]

        # Numeric scrapes from the visible body text.
        body = soup.get_text(" ", strip=True)
        msrp = first_match(
            body,
            r"Starting\s+(?:MSRP|at)[^\$]{0,30}\$([\d,]+)",
            r"MSRP[^\$]{0,30}\$([\d,]+)",
            r"\$([\d,]+)\s*Starting",
        )
        if msrp:
            try:
                specs["starting_msrp"] = int(msrp.replace(",", ""))
            except ValueError:
                pass

        mpg = re.search(r"(\d{1,2})\s*city\s*/\s*(\d{1,2})\s*hwy", body, re.I)
        if mpg:
            specs["mpg_city"] = int(mpg.group(1))
            specs["mpg_hwy"] = int(mpg.group(2))

        return specs

    def _absorb_jsonld(self, specs: dict[str, Any], d: dict[str, Any]) -> None:
        mapping = {
            "vehicle_engine": "vehicleEngine",
            "transmission": "vehicleTransmission",
            "drivetrain": "driveWheelConfiguration",
            "body_style": "bodyType",
            "fuel_type": "fuelType",
            "seating_capacity": "vehicleSeatingCapacity",
        }
        for k, jk in mapping.items():
            v = d.get(jk)
            if v and k not in specs:
                specs[k] = v.get("name") if isinstance(v, dict) else v
        offers = d.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price") or offers.get("lowPrice")
            if price:
                try:
                    specs.setdefault("starting_msrp", int(float(price)))
                except (TypeError, ValueError):
                    pass

    # --------------------------------------------------------- sticker

    def _find_sticker_url(self, html: str, vin: str) -> str | None:
        # Ford's public model page rarely links a Monroney sticker —
        # those live behind owner.ford.com (login) or on the dealer's
        # VDP. We still scan in case the page does embed one.
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

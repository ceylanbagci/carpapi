"""Japanese-brand dealer locator scraper.

Iterates a state's ZIP codes and asks each maker's locator endpoint
for nearby dealers. Filters to the requested state.

Makers covered: Honda, Kia, Lexus, Nissan, Subaru, Toyota.
(Kia is grouped here for historical reasons with the Japanese sweep.)

Originally hard-coded to NJ; now accepts --state <USPS code>. Honda /
Kia / Nissan / Subaru / Lexus all use zip-driven REST or GraphQL
endpoints. Toyota uses a per-state HTML directory page
(https://www.toyota.com/dealers/<state-slug>/dealer-state-meta/dealers/).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from ._states import load_zips_for_state, state_slug
except ImportError:  # invoked as a script, not as a module
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _states import load_zips_for_state, state_slug


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "output" / "dealers_final.json"
REQUEST_TIMEOUT = 30
MAX_WORKERS = 6

NISSAN_GRAPHQL_URL = "https://graphql.nissanusa.com/graphql"
NISSAN_AUTH_HEADER = "da2-3gadjirlkbfdzg7fiosg4tewl4"
SUBARU_API_URL = "https://www.subaru.com/services/dealers/distances/by/zipcode"
LEXUS_API_URL = "https://www.lexus.com/rest/lexus/dealers"
HONDA_API_URL = "https://automobiles.honda.com/platform/api/v1/dealerLocator"
KIA_API_URL = "https://www.kia.com/us/services/en/dealers/dealerLocatorByZipCode"
TOYOTA_DIRECTORY_TPL = "https://www.toyota.com/dealers/{slug}/dealer-state-meta/dealers/"

MAKE_IDS = {
    "Honda": "17",
    "Kia": "24",
    "Lexus": "27",
    "Nissan": "36",
    "Subaru": "44",
    "Toyota": "46",
}
MAKE_ORDER = [MAKE_IDS[make] for make in ("Honda", "Kia", "Lexus", "Nissan", "Subaru", "Toyota")]


def load_all_dealers() -> list[dict]:
    if not OUTPUT_PATH.exists():
        return []
    return json.loads(OUTPUT_PATH.read_text())


def normalize_website(url: str) -> str | None:
    website = (url or "").strip()
    if not website:
        return None
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    return website


def build_record(name: str, make: str, website: str, slug: str) -> dict | None:
    normalized_name = name.strip()
    normalized_website = normalize_website(website)
    if not normalized_name or not normalized_website:
        return None
    return {
        "name": normalized_name,
        "make": make,
        "make_id": MAKE_IDS[make],
        "state": slug,
        "dealership_website": normalized_website,
    }


def fetch_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict | list:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*", **(headers or {})},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 400:
        return {}
    response.raise_for_status()
    return response.json()


# ---------------------------- Nissan ----------------------------

def fetch_nissan_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = {
        "operationName": "getDealersBaseInfoByLatLng",
        "variables": {
            "market": {"lang": "en", "region": "us", "brand": "nissan", "application": "inventory"},
            "location": {"postalCode": zip_code},
            "size": 100, "radius": 50, "isMarketingDealer": False,
        },
        "query": """
            query getDealersBaseInfoByLatLng($market: Market!, $location: Geolocation!, $size: Int, $radius: Int, $isMarketingDealer: Boolean) {
              getDealersByLatLng(market: $market, location: $location, isMarketingDealer: $isMarketingDealer, size: $size, radius: $radius) {
                id name address { stateCode } websiteURL
              }
            }
        """,
    }
    response = requests.post(
        NISSAN_GRAPHQL_URL, json=payload,
        headers={
            "User-Agent": "Mozilla/5.0", "Accept": "application/json", "Content-Type": "application/json",
            "auth": NISSAN_AUTH_HEADER,
            "Origin": "https://www.nissanusa.com", "Referer": "https://www.nissanusa.com/dealer-locator.html",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(f"Nissan GraphQL returned errors for ZIP {zip_code}: {body['errors']}")
    return body.get("data", {}).get("getDealersByLatLng", [])


def collect_nissan(zip_codes: list[str], state_code: str, slug: str) -> list[dict]:
    return _collect_with_workers(
        zip_codes, fetch_nissan_dealers_for_zip,
        id_key="id", state_filter=lambda d: (d.get("address") or {}).get("stateCode") == state_code,
        name_key="name", website_key="websiteURL",
        make="Nissan", slug=slug,
    )


# ---------------------------- Subaru ----------------------------

def fetch_subaru_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = fetch_json(SUBARU_API_URL, params={"zipcode": zip_code})
    return [item.get("dealer") or {} for item in (payload if isinstance(payload, list) else [])]


def collect_subaru(zip_codes: list[str], state_code: str, slug: str) -> list[dict]:
    return _collect_with_workers(
        zip_codes, fetch_subaru_dealers_for_zip,
        id_key="id",
        state_filter=lambda d: ((d.get("address") or {}).get("state") or "").upper() == state_code,
        name_key="name", website_key="siteUrl",
        make="Subaru", slug=slug,
    )


# ---------------------------- Lexus -----------------------------

def fetch_lexus_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = fetch_json(LEXUS_API_URL, params={"zipCode": zip_code})
    return payload.get("dealers", []) if isinstance(payload, dict) else []


def collect_lexus(zip_codes: list[str], state_code: str, slug: str) -> list[dict]:
    return _collect_with_workers(
        zip_codes, fetch_lexus_dealers_for_zip,
        id_key="id",
        state_filter=lambda d: ((d.get("dealerAddress") or {}).get("state") or "").upper() == state_code,
        name_key="dealerName", website_key="dealerSiteUrl",
        make="Lexus", slug=slug,
    )


# ---------------------------- Honda -----------------------------

def fetch_honda_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = fetch_json(HONDA_API_URL, params={"zip": zip_code, "make": "honda"})
    if isinstance(payload, dict):
        return payload.get("Dealers", []) or payload.get("dealers", []) or []
    return []


def collect_honda(zip_codes: list[str], state_code: str, slug: str) -> list[dict]:
    return _collect_with_workers(
        zip_codes, fetch_honda_dealers_for_zip,
        id_key="DealerNumber",
        state_filter=lambda d: (d.get("State") or d.get("state") or "").upper() == state_code,
        name_key="Name", website_key="Website",
        make="Honda", slug=slug,
    )


# ---------------------------- Kia -----------------------------

def fetch_kia_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = fetch_json(KIA_API_URL, params={"zipCode": zip_code, "radius": 50})
    if isinstance(payload, dict):
        return payload.get("dealers", []) or payload.get("Dealers", []) or []
    return []


def collect_kia(zip_codes: list[str], state_code: str, slug: str) -> list[dict]:
    return _collect_with_workers(
        zip_codes, fetch_kia_dealers_for_zip,
        id_key="dealerCode",
        state_filter=lambda d: (d.get("state") or d.get("State") or "").upper() == state_code,
        name_key="name", website_key="websiteURL",
        make="Kia", slug=slug,
    )


# ---------------------------- Toyota ----------------------------

def collect_toyota(_zip_codes: list[str], state_code: str, slug: str) -> list[dict]:
    url = TOYOTA_DIRECTORY_TPL.format(slug=slug)
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return []
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    ordered: list[dict] = []
    seen_codes: set[str] = set()
    href_re = re.compile(rf"^/dealers/{re.escape(slug)}/")

    for title in soup.select("h2.dealer-card__title-heading"):
        card = title.find_parent(lambda tag: tag.name == "div" and "dealer-card" in (tag.get("class") or []))
        if card is None:
            continue
        details_link = card.find("a", href=href_re)
        website_link = card.find("a", attrs={"data-aa-link_button_action": "Dealer Website link"})
        dealer_code = (website_link or details_link or {}).get("data-aa-dealer-code", "").strip()
        if not dealer_code or dealer_code in seen_codes or details_link is None or website_link is None:
            continue
        record = build_record(title.get_text(" ", strip=True), "Toyota", website_link.get("href", ""), slug)
        if not record:
            continue
        seen_codes.add(dealer_code)
        ordered.append(record)
    return ordered


# ---------------------------- shared worker ----------------------------

def _collect_with_workers(zip_codes, fetcher, *, id_key, state_filter, name_key, website_key, make, slug):
    """Generic concurrent-zip collector. Each fetcher returns a list of
    dealer dicts; we de-dup by `id_key`, filter via `state_filter`, and
    normalize via build_record()."""
    ordered: list[dict] = []
    seen_ids: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, dealers in zip(zip_codes, executor.map(_safe_fetch, [fetcher] * len(zip_codes), zip_codes)):
            zip_to_dealers[zip_code] = dealers

    for zip_code in zip_codes:
        for dealer in zip_to_dealers.get(zip_code, []):
            dealer_id = str(dealer.get(id_key, "")).strip()
            if not dealer_id or dealer_id in seen_ids:
                continue
            if not state_filter(dealer):
                continue
            record = build_record(dealer.get(name_key, ""), make, dealer.get(website_key, ""), slug)
            if not record:
                continue
            seen_ids.add(dealer_id)
            ordered.append(record)
    return ordered


def _safe_fetch(fetcher, zip_code):
    try:
        return fetcher(zip_code)
    except Exception as exc:                                  # noqa: BLE001
        print(f"[japan] {fetcher.__name__} zip {zip_code} failed: {exc}", file=sys.stderr)
        return []


# ---------------------------- merge ----------------------------

def merge_make_blocks(all_dealers, replacements, slug):
    """Replace per-(make_id, state) slices in dealers_final.json with
    the new lists. Other states' dealers for the same maker stay."""
    def is_target(d, make_id):
        return d.get("make_id") == make_id and d.get("state") == slug

    merged = list(all_dealers)
    summary: dict[str, tuple[int, int]] = {}
    for make_id, new_block in replacements.items():
        prev = [i for i, d in enumerate(merged) if is_target(d, make_id)]
        summary[make_id] = (len(prev), len(new_block))
        if prev:
            insert_at = prev[0]
            merged = [d for d in merged if not is_target(d, make_id)]
        else:
            order_index = MAKE_ORDER.index(make_id)
            insert_at = len(merged)
            if order_index > 0:
                prev_make_id = MAKE_ORDER[order_index - 1]
                prev_indexes = [i for i, d in enumerate(merged) if d.get("make_id") == prev_make_id]
                if prev_indexes:
                    insert_at = prev_indexes[-1] + 1
        merged[insert_at:insert_at] = new_block
    return merged, summary


def parse_args():
    p = argparse.ArgumentParser(description="Scrape Japanese-brand dealer locators for one state.")
    p.add_argument("--state", default="NJ", help="USPS 2-letter state code. Default NJ.")
    # Default skips the three makers blocked by maker WAFs / unknown API
    # (Honda, Kia, Nissan). Pass `--makes all` to attempt all six.
    p.add_argument("--makes", default="lexus,subaru,toyota",
                   help="Comma-separated subset of: honda,kia,lexus,nissan,subaru,toyota, or 'all'. "
                        "Default 'lexus,subaru,toyota' (the three known-working).")
    p.add_argument("--sleep", type=float, default=0.0,
                   help="Per-request sleep (rate-limit budget). Default 0.")
    return p.parse_args()


COLLECTORS = {
    "Honda":  collect_honda,
    "Kia":    collect_kia,
    "Lexus":  collect_lexus,
    "Nissan": collect_nissan,
    "Subaru": collect_subaru,
    "Toyota": collect_toyota,
}


def main():
    args = parse_args()
    state_code = args.state.upper()
    slug = state_slug(state_code)
    selected = args.makes.lower()
    chosen_makes = list(COLLECTORS) if selected == "all" else [
        m for m in COLLECTORS if m.lower() in {s.strip() for s in selected.split(",")}
    ]
    if not chosen_makes:
        print(f"[japan][{state_code}] no makes selected; nothing to do.")
        return

    zip_codes = load_zips_for_state(state_code)
    if not zip_codes:
        print(f"[japan][{state_code}] no zips for state; nothing to do.")
        return

    print(f"[japan][{state_code}] {len(zip_codes)} zips × {len(chosen_makes)} makes → scraping…")

    replacements: dict[str, list[dict]] = {}
    for make in chosen_makes:
        if args.sleep:
            time.sleep(args.sleep)
        block = COLLECTORS[make](zip_codes, state_code, slug)
        replacements[MAKE_IDS[make]] = block
        print(f"  · {make}: {len(block)} dealers")

    all_dealers = load_all_dealers()
    merged, summary = merge_make_blocks(all_dealers, replacements, slug)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(merged, indent=2) + "\n")

    for make in chosen_makes:
        prev, new = summary[MAKE_IDS[make]]
        print(f"[japan][{state_code}] {make}: replaced {prev} → {new} entries.")


if __name__ == "__main__":
    main()

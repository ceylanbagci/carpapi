"""Stellantis dealer locator scraper (Ram by default).

Scrapes the Stellantis dealer-locator API. The endpoint serves all
four brands — pass --brand R|D|C|J to switch:
  R = Ram (default), D = Dodge, C = Chrysler, J = Jeep.

State-aware: --state <USPS code>.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

try:
    from ._states import load_zips_for_state, state_slug
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _states import load_zips_for_state, state_slug


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "output" / "dealers_final.json"
STELLANTIS_API_URL = "https://www.ramtrucks.com/bdlws/MDLSDealerLocator"
SEARCH_RADIUS = 50
RESULTS_PER_PAGE = 100
REQUEST_TIMEOUT = 30
MAX_WORKERS = 6
MAX_RETRIES = 3

# brandCode → (make name, input/makes.json id)
BRANDS = {
    "R": ("Ram", "66"),
    "D": ("Dodge", "13"),
    "C": ("Chrysler", "10"),
    "J": ("Jeep", "23"),
}


def fetch_dealers_for_zip(zip_code: str, brand_code: str) -> list[dict]:
    dealers: list[dict] = []
    current_page = 1
    total_pages = 1

    while current_page <= total_pages:
        response = None
        for attempt in range(MAX_RETRIES):
            response = requests.get(
                STELLANTIS_API_URL,
                params={
                    "zipCode": zip_code,
                    "radius": SEARCH_RADIUS,
                    "resultsPage": current_page,
                    "resultsPerPage": RESULTS_PER_PAGE,
                    "brandCode": brand_code,
                },
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 400:
                return []
            if response.status_code != 403:
                break
            time.sleep(1 + attempt)

        if response is None:
            raise RuntimeError(f"Stellantis API returned no response for ZIP {zip_code}")
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("status", 0)) != 200:
            raise RuntimeError(f"Stellantis API returned an unexpected status for ZIP {zip_code}: {payload}")

        page_dealers = payload.get("dealer", [])
        if isinstance(page_dealers, dict):
            page_dealers = [page_dealers]
        dealers.extend(page_dealers)
        total_pages = int(payload.get("numberOfResultPages") or 1)
        current_page += 1
    return dealers


def _safe_fetch(zip_code: str, brand_code: str) -> list[dict]:
    try:
        return fetch_dealers_for_zip(zip_code, brand_code)
    except Exception as exc:                                  # noqa: BLE001
        print(f"[stellantis][{brand_code}] zip {zip_code} failed: {exc}", file=sys.stderr)
        return []


def build_dealer_record(raw_dealer: dict, state_code: str, slug: str,
                        brand_code: str, make_name: str, make_id: str) -> dict | None:
    if raw_dealer.get("dealerState") != state_code:
        return None
    brands = raw_dealer.get("brands") or []
    if brand_code not in brands:
        return None
    website = (raw_dealer.get("website") or "").strip()
    if not website:
        return None
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    name = (raw_dealer.get("dealerName") or "").strip()
    if not name:
        return None
    postal = (raw_dealer.get("dealerZip") or raw_dealer.get("zip") or "").strip()
    city = (raw_dealer.get("dealerCity") or raw_dealer.get("city") or "").strip() or None
    return {
        "name": name,
        "make": make_name,
        "make_id": make_id,
        "state": slug,
        "city": city,
        "postal_code": postal[:5] if postal else None,
        "dealership_website": website,
    }


def collect_dealers(zip_codes, state_code, slug, brand_code, make_name, make_id):
    ordered_dealers: list[dict] = []
    seen_dealer_codes: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, raw_dealers in zip(
            zip_codes,
            executor.map(_safe_fetch, zip_codes, [brand_code] * len(zip_codes)),
        ):
            zip_to_dealers[zip_code] = raw_dealers

    for zip_code in zip_codes:
        for raw_dealer in zip_to_dealers.get(zip_code, []):
            dealer_code = str(raw_dealer.get("dealerCode", "")).strip()
            if not dealer_code or dealer_code in seen_dealer_codes:
                continue
            dealer_record = build_dealer_record(raw_dealer, state_code, slug, brand_code, make_name, make_id)
            if not dealer_record:
                continue
            seen_dealer_codes.add(dealer_code)
            ordered_dealers.append(dealer_record)
    return ordered_dealers


def merge_dealers(output_path, new_dealers, make_id, slug):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_dealers = json.loads(output_path.read_text()) if output_path.exists() else []

    def is_target(d):
        return d.get("make_id") == make_id and d.get("state") == slug

    indexes = [i for i, d in enumerate(all_dealers) if is_target(d)]
    if indexes:
        insert_at = indexes[0]
        remaining = [d for d in all_dealers if not is_target(d)]
    else:
        insert_at = len(all_dealers)
        remaining = all_dealers
    merged = remaining[:insert_at] + new_dealers + remaining[insert_at:]
    output_path.write_text(json.dumps(merged, indent=2) + "\n")
    return len(indexes), len(new_dealers)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Stellantis dealer locator (Ram/Dodge/Chrysler/Jeep) for one state.")
    p.add_argument("--state", default="NJ", help="USPS 2-letter state code. Default NJ.")
    p.add_argument("--brand", default="R", choices=list(BRANDS),
                   help="Brand code: R=Ram (default), D=Dodge, C=Chrysler, J=Jeep.")
    p.add_argument("--sleep", type=float, default=0.0, help="Per-request sleep. Default 0.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    state_code = args.state.upper()
    slug = state_slug(state_code)
    brand_code = args.brand.upper()
    make_name, make_id = BRANDS[brand_code]

    zip_codes = load_zips_for_state(state_code)
    if not zip_codes:
        print(f"[stellantis][{state_code}] no zips for state; nothing to do.")
        return
    print(f"[stellantis][{state_code}][{make_name}] {len(zip_codes)} zips → scraping…")
    dealers = collect_dealers(zip_codes, state_code, slug, brand_code, make_name, make_id)
    previous_count, new_count = merge_dealers(OUTPUT_PATH, dealers, make_id, slug)
    print(
        f"[stellantis][{state_code}][{make_name}] updated {OUTPUT_PATH} with {new_count} dealers "
        f"(replaced {previous_count} existing {make_name}/{slug})."
    )


if __name__ == "__main__":
    main()

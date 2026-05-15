"""Chevrolet (GM) dealer locator scraper.

Despite the filename, this currently scrapes Chevrolet only. GMC/Buick/
Cadillac all share the same GM Quantum dealer-locator endpoint with a
different `makeCodes` value — they can be added by widening MAKE_CODES.

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
CHEVROLET_API_URL = "https://www.chevrolet.com/bypass/pcf/quantum-dealer-locator/v1/getDealers"
CHEVROLET_MAKE = "Chevrolet"
CHEVROLET_MAKE_ID = "9"
CHEVROLET_MAKE_CODE = "001"
SEARCH_RADIUS = 50
DESIRED_COUNT = 100
REQUEST_TIMEOUT = 30
MAX_WORKERS = 6
MAX_RETRIES = 3


def fetch_chevrolet_dealers_for_zip(zip_code: str) -> list[dict]:
    response = None
    for attempt in range(MAX_RETRIES):
        response = requests.get(
            CHEVROLET_API_URL,
            params={
                "desiredCount": DESIRED_COUNT,
                "distance": SEARCH_RADIUS,
                "makeCodes": CHEVROLET_MAKE_CODE,
                "serviceCodes": "",
                "searchType": "postalCodeSearch",
                "postalCode": zip_code,
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
                "clientapplicationid": "quantum",
                "locale": "en-US",
            },
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 400:
            return []
        if response.status_code != 403:
            break
        time.sleep(1 + attempt)

    if response is None:
        raise RuntimeError(f"Chevrolet API returned no response for ZIP {zip_code}")

    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "Failure" and not payload.get("payload", {}).get("dealers"):
        return []
    if payload.get("status") != "success":
        raise RuntimeError(f"Chevrolet API returned an unexpected status for ZIP {zip_code}: {payload}")
    return payload.get("payload", {}).get("dealers", [])


def _safe_fetch(zip_code: str) -> list[dict]:
    try:
        return fetch_chevrolet_dealers_for_zip(zip_code)
    except Exception as exc:                                  # noqa: BLE001
        print(f"[chevy] zip {zip_code} failed: {exc}", file=sys.stderr)
        return []


def normalize_dealer_name(name: str) -> str:
    return name.strip().title()


def build_chevrolet_dealer_record(raw_dealer: dict, state_code: str, slug: str) -> dict | None:
    address = raw_dealer.get("address") or {}
    if address.get("countrySubdivisionCode") != state_code:
        return None

    website = (raw_dealer.get("dealerUrl") or "").strip()
    if not website:
        return None
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"

    name = normalize_dealer_name(raw_dealer.get("dealerName", ""))
    if not name:
        return None

    postal = (address.get("postalCode") or address.get("zip") or "").strip()
    city = (address.get("addressLine2") or address.get("city") or "").strip() or None

    return {
        "name": name,
        "make": CHEVROLET_MAKE,
        "make_id": CHEVROLET_MAKE_ID,
        "state": slug,
        "city": city,
        "postal_code": postal[:5] if postal else None,
        "dealership_website": website,
    }


def collect_chevrolet_dealers(zip_codes: list[str], state_code: str, slug: str) -> list[dict]:
    ordered_dealers: list[dict] = []
    seen_bacs: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, raw_dealers in zip(zip_codes, executor.map(_safe_fetch, zip_codes)):
            zip_to_dealers[zip_code] = raw_dealers

    for zip_code in zip_codes:
        for raw_dealer in zip_to_dealers.get(zip_code, []):
            bac = str(raw_dealer.get("bac", "")).strip()
            if not bac or bac in seen_bacs:
                continue
            dealer_record = build_chevrolet_dealer_record(raw_dealer, state_code, slug)
            if not dealer_record:
                continue
            seen_bacs.add(bac)
            ordered_dealers.append(dealer_record)
    return ordered_dealers


def merge_chevrolet_dealers(output_path: Path, chevrolet_dealers: list[dict], slug: str) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_dealers = json.loads(output_path.read_text()) if output_path.exists() else []

    def is_target(d: dict) -> bool:
        return d.get("make_id") == CHEVROLET_MAKE_ID and d.get("state") == slug

    target_indexes = [i for i, d in enumerate(all_dealers) if is_target(d)]
    if target_indexes:
        insert_at = target_indexes[0]
        remaining = [d for d in all_dealers if not is_target(d)]
    else:
        insert_at = len(all_dealers)
        remaining = all_dealers
    merged = remaining[:insert_at] + chevrolet_dealers + remaining[insert_at:]
    output_path.write_text(json.dumps(merged, indent=2) + "\n")
    return len(target_indexes), len(chevrolet_dealers)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Chevrolet dealer locator for one state.")
    p.add_argument("--state", default="NJ", help="USPS 2-letter state code. Default NJ.")
    p.add_argument("--sleep", type=float, default=0.0, help="Per-request sleep. Default 0.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    state_code = args.state.upper()
    slug = state_slug(state_code)
    zip_codes = load_zips_for_state(state_code)
    if not zip_codes:
        print(f"[chevy][{state_code}] no zips for state; nothing to do.")
        return
    print(f"[chevy][{state_code}] {len(zip_codes)} zips → scraping…")
    chevrolet_dealers = collect_chevrolet_dealers(zip_codes, state_code, slug)
    previous_count, new_count = merge_chevrolet_dealers(OUTPUT_PATH, chevrolet_dealers, slug)
    print(
        f"[chevy][{state_code}] updated {OUTPUT_PATH} with {new_count} Chevrolet/{slug} dealers "
        f"(replaced {previous_count} existing)."
    )


if __name__ == "__main__":
    main()

"""Ford dealer locator scraper.

Iterates a list of US ZIP codes for a single state, asks Ford's
public dealer-locator API for nearby Ford dealers at each ZIP, dedups
by PACode, filters to the requested state, and merges results into
output/dealers_final.json.

Originally hard-coded to NJ; now accepts --state <USPS code>.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


MAX_WORKERS = 6

try:
    from ._states import load_zips_for_state, state_slug
except ImportError:  # invoked as a script, not as a module
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _states import load_zips_for_state, state_slug


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = (ROOT / "inputs", ROOT / "input")
OUTPUT_PATH = ROOT / "output" / "dealers_final.json"
FORD_API_URL = "https://www.ford.com/cxservices/dealer/Dealers.json"
FORD_APPLICATION_ID = "07152898-698b-456e-be56-d3d83011d0a6"
FORD_MAKE = "Ford"
FORD_MAKE_ID = "15"
REQUEST_TIMEOUT = 30


def fetch_ford_dealers_for_zip(zip_code: str) -> list[dict]:
    response = requests.get(
        FORD_API_URL,
        params={
            "make": FORD_MAKE,
            "postalCode": zip_code,
            "radius": 50,
            "minDealers": 1,
            "maxDealers": 100,
        },
        headers={"Application-id": FORD_APPLICATION_ID},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 400:
        return []
    response.raise_for_status()
    payload = response.json()
    if payload.get("Response", {}).get("status") != "OK":
        raise RuntimeError(f"Ford API returned an unexpected status for ZIP {zip_code}: {payload}")
    dealers = payload.get("Response", {}).get("Dealer", [])
    if isinstance(dealers, dict):
        return [dealers]
    return dealers


def build_dealer_record(raw_dealer: dict, state_code: str, slug: str) -> dict | None:
    address = raw_dealer.get("Address") or {}
    if address.get("State") != state_code:
        return None

    website = raw_dealer.get("URL")
    if not website:
        return None

    # Ford returns Zip in Address.Zip (sometimes Address.ZipCode); accept either.
    postal = (address.get("Zip") or address.get("ZipCode") or "").strip()
    city = (address.get("City") or "").strip() or None

    return {
        "name": raw_dealer.get("Name", "").strip(),
        "make": FORD_MAKE,
        "make_id": FORD_MAKE_ID,
        "state": slug,
        "city": city,
        "postal_code": postal[:5] if postal else None,
        "dealership_website": website.strip(),
    }


def _safe_fetch(zip_code: str) -> list[dict]:
    try:
        return fetch_ford_dealers_for_zip(zip_code)
    except Exception as exc:                                  # noqa: BLE001
        print(f"[ford] zip {zip_code} failed: {exc}", file=sys.stderr)
        return []


def collect_ford_dealers(zip_codes: list[str], state_code: str, slug: str, *,
                         sleep_between: float = 0.0,
                         progress_every: int = 50) -> list[dict]:
    """Fan out to Ford's locator with a thread pool; dedupe by PACode."""
    ordered_dealers: list[dict] = []
    seen_pacodes: set[str] = set()

    zip_to_dealers: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for idx, (zip_code, raw_list) in enumerate(
            zip(zip_codes, executor.map(_safe_fetch, zip_codes)), start=1
        ):
            zip_to_dealers[zip_code] = raw_list
            if progress_every and idx % progress_every == 0:
                print(f"[ford][{state_code}] {idx}/{len(zip_codes)} zips fetched")

    for zip_code in zip_codes:
        for raw_dealer in zip_to_dealers.get(zip_code, []):
            pacode = str(raw_dealer.get("PACode", "")).strip()
            if not pacode or pacode in seen_pacodes:
                continue
            dealer_record = build_dealer_record(raw_dealer, state_code, slug)
            if not dealer_record:
                continue
            seen_pacodes.add(pacode)
            ordered_dealers.append(dealer_record)
    print(f"[ford][{state_code}] {len(zip_codes)} zips → {len(ordered_dealers)} unique dealers")
    if sleep_between:
        time.sleep(sleep_between)
    return ordered_dealers


def merge_ford_dealers(output_path: Path, ford_dealers: list[dict], state_slug_value: str) -> tuple[int, int]:
    """Replace the (make=Ford, state=<slug>) slice in dealers_final.json
    with the new list and rewrite. Other states' Ford dealers are left
    alone so per-state runs stack correctly."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        all_dealers = json.loads(output_path.read_text())
    else:
        all_dealers = []

    def is_target(d: dict) -> bool:
        return d.get("make_id") == FORD_MAKE_ID and d.get("state") == state_slug_value

    target_indexes = [i for i, d in enumerate(all_dealers) if is_target(d)]
    if target_indexes:
        insert_at = target_indexes[0]
        remaining = [d for d in all_dealers if not is_target(d)]
    else:
        insert_at = len(all_dealers)
        remaining = all_dealers

    merged = remaining[:insert_at] + ford_dealers + remaining[insert_at:]
    output_path.write_text(json.dumps(merged, indent=2) + "\n")
    return len(target_indexes), len(ford_dealers)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Ford dealer locator for one state.")
    p.add_argument("--state", default="NJ", help="USPS 2-letter state code (e.g. NJ, CA, TX). Default NJ.")
    p.add_argument("--sleep", type=float, default=0.0,
                   help="Seconds to sleep between per-zip requests (rate-limit budget). Default 0.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    state_code = args.state.upper()
    slug = state_slug(state_code)
    zip_codes = load_zips_for_state(state_code)
    if not zip_codes:
        print(f"[ford][{state_code}] no zips found; nothing to do.")
        return
    print(f"[ford][{state_code}] {len(zip_codes)} zips → scraping (sleep={args.sleep}s)…")
    ford_dealers = collect_ford_dealers(zip_codes, state_code, slug, sleep_between=args.sleep)
    previous_count, new_count = merge_ford_dealers(OUTPUT_PATH, ford_dealers, slug)
    print(
        f"[ford][{state_code}] updated {OUTPUT_PATH} with {new_count} dealers "
        f"(replaced {previous_count} existing Ford/{slug} entries)."
    )


if __name__ == "__main__":
    main()

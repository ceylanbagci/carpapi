import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = (ROOT / "inputs", ROOT / "input")
OUTPUT_PATH = ROOT / "output" / "dealers_final.json"
CHEVROLET_API_URL = "https://www.chevrolet.com/bypass/pcf/quantum-dealer-locator/v1/getDealers"
CHEVROLET_MAKE = "Chevrolet"
CHEVROLET_MAKE_ID = "9"
CHEVROLET_MAKE_CODE = "001"
STATE_CODE = "NJ"
STATE_SLUG = "new-jersey"
SEARCH_RADIUS = 50
DESIRED_COUNT = 100
REQUEST_TIMEOUT = 30
MAX_WORKERS = 6
MAX_RETRIES = 3


def resolve_input_dir() -> Path:
    for candidate in INPUT_DIR_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find an input directory. Checked: inputs, input")


def load_zip_codes() -> list[str]:
    zip_codes_path = resolve_input_dir() / "zip_codes.json"
    payload = json.loads(zip_codes_path.read_text())
    zip_codes = payload.get("zip_codes", [])
    if not isinstance(zip_codes, list):
        raise ValueError(f"Invalid zip code payload in {zip_codes_path}")
    return [str(zip_code).zfill(5) for zip_code in zip_codes]


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


def normalize_dealer_name(name: str) -> str:
    return name.strip().title()


def build_chevrolet_dealer_record(raw_dealer: dict) -> dict | None:
    address = raw_dealer.get("address") or {}
    if address.get("countrySubdivisionCode") != STATE_CODE:
        return None

    website = (raw_dealer.get("dealerUrl") or "").strip()
    if not website:
        return None
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"

    name = normalize_dealer_name(raw_dealer.get("dealerName", ""))
    if not name:
        return None

    return {
        "name": name,
        "make": CHEVROLET_MAKE,
        "make_id": CHEVROLET_MAKE_ID,
        "state": STATE_SLUG,
        "dealership_website": website,
    }


def collect_chevrolet_dealers(zip_codes: list[str]) -> list[dict]:
    ordered_dealers: list[dict] = []
    seen_bacs: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, raw_dealers in zip(zip_codes, executor.map(fetch_chevrolet_dealers_for_zip, zip_codes)):
            zip_to_dealers[zip_code] = raw_dealers

    for zip_code in zip_codes:
        for raw_dealer in zip_to_dealers.get(zip_code, []):
            bac = str(raw_dealer.get("bac", "")).strip()
            if not bac or bac in seen_bacs:
                continue

            dealer_record = build_chevrolet_dealer_record(raw_dealer)
            if not dealer_record:
                continue

            seen_bacs.add(bac)
            ordered_dealers.append(dealer_record)

    return ordered_dealers


def merge_chevrolet_dealers(output_path: Path, chevrolet_dealers: list[dict]) -> tuple[int, int]:
    all_dealers = json.loads(output_path.read_text())
    chevrolet_indexes = [
        index for index, dealer in enumerate(all_dealers) if dealer.get("make_id") == CHEVROLET_MAKE_ID
    ]

    if chevrolet_indexes:
        insert_at = chevrolet_indexes[0]
        remaining_dealers = [dealer for dealer in all_dealers if dealer.get("make_id") != CHEVROLET_MAKE_ID]
    else:
        insert_at = len(all_dealers)
        remaining_dealers = all_dealers

    merged = remaining_dealers[:insert_at] + chevrolet_dealers + remaining_dealers[insert_at:]
    output_path.write_text(json.dumps(merged, indent=2) + "\n")
    return len(chevrolet_indexes), len(chevrolet_dealers)


def main() -> None:
    zip_codes = load_zip_codes()
    chevrolet_dealers = collect_chevrolet_dealers(zip_codes)
    previous_count, new_count = merge_chevrolet_dealers(OUTPUT_PATH, chevrolet_dealers)
    print(
        f"Updated {OUTPUT_PATH} with {new_count} Chevrolet dealers "
        f"(replaced {previous_count} existing Chevrolet entries)."
    )


if __name__ == "__main__":
    main()

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = (ROOT / "inputs", ROOT / "input")
OUTPUT_PATH = ROOT / "output" / "dealers_final.json"
RAM_API_URL = "https://www.ramtrucks.com/bdlws/MDLSDealerLocator"
RAM_MAKE = "Ram"
RAM_MAKE_ID = "66"
STATE_CODE = "NJ"
STATE_SLUG = "new-jersey"
SEARCH_RADIUS = 50
RESULTS_PER_PAGE = 100
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


def fetch_ram_dealers_for_zip(zip_code: str) -> list[dict]:
    dealers: list[dict] = []
    current_page = 1
    total_pages = 1

    while current_page <= total_pages:
        response = None
        for attempt in range(MAX_RETRIES):
            response = requests.get(
                RAM_API_URL,
                params={
                    "zipCode": zip_code,
                    "radius": SEARCH_RADIUS,
                    "resultsPage": current_page,
                    "resultsPerPage": RESULTS_PER_PAGE,
                    "brandCode": "R",
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
            raise RuntimeError(f"Ram API returned no response for ZIP {zip_code}")

        response.raise_for_status()
        payload = response.json()
        if int(payload.get("status", 0)) != 200:
            raise RuntimeError(f"Ram API returned an unexpected status for ZIP {zip_code}: {payload}")

        page_dealers = payload.get("dealer", [])
        if isinstance(page_dealers, dict):
            page_dealers = [page_dealers]
        dealers.extend(page_dealers)

        total_pages = int(payload.get("numberOfResultPages") or 1)
        current_page += 1

    return dealers


def build_ram_dealer_record(raw_dealer: dict) -> dict | None:
    if raw_dealer.get("dealerState") != STATE_CODE:
        return None

    brands = raw_dealer.get("brands") or []
    if "R" not in brands:
        return None

    website = (raw_dealer.get("website") or "").strip()
    if not website:
        return None
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"

    name = (raw_dealer.get("dealerName") or "").strip()
    if not name:
        return None

    return {
        "name": name,
        "make": RAM_MAKE,
        "make_id": RAM_MAKE_ID,
        "state": STATE_SLUG,
        "dealership_website": website,
    }


def collect_ram_dealers(zip_codes: list[str]) -> list[dict]:
    ordered_dealers: list[dict] = []
    seen_dealer_codes: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, raw_dealers in zip(zip_codes, executor.map(fetch_ram_dealers_for_zip, zip_codes)):
            zip_to_dealers[zip_code] = raw_dealers

    for zip_code in zip_codes:
        for raw_dealer in zip_to_dealers.get(zip_code, []):
            dealer_code = str(raw_dealer.get("dealerCode", "")).strip()
            if not dealer_code or dealer_code in seen_dealer_codes:
                continue

            dealer_record = build_ram_dealer_record(raw_dealer)
            if not dealer_record:
                continue

            seen_dealer_codes.add(dealer_code)
            ordered_dealers.append(dealer_record)

    return ordered_dealers


def merge_ram_dealers(output_path: Path, ram_dealers: list[dict]) -> tuple[int, int]:
    all_dealers = json.loads(output_path.read_text())
    ram_indexes = [index for index, dealer in enumerate(all_dealers) if dealer.get("make_id") == RAM_MAKE_ID]

    if ram_indexes:
        insert_at = ram_indexes[0]
        remaining_dealers = [dealer for dealer in all_dealers if dealer.get("make_id") != RAM_MAKE_ID]
    else:
        insert_at = len(all_dealers)
        remaining_dealers = all_dealers

    merged = remaining_dealers[:insert_at] + ram_dealers + remaining_dealers[insert_at:]
    output_path.write_text(json.dumps(merged, indent=2) + "\n")
    return len(ram_indexes), len(ram_dealers)


def main() -> None:
    zip_codes = load_zip_codes()
    ram_dealers = collect_ram_dealers(zip_codes)
    previous_count, new_count = merge_ram_dealers(OUTPUT_PATH, ram_dealers)
    print(
        f"Updated {OUTPUT_PATH} with {new_count} Ram dealers "
        f"(replaced {previous_count} existing Ram entries)."
    )


if __name__ == "__main__":
    main()

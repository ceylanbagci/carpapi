import json
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = (ROOT / "inputs", ROOT / "input")
OUTPUT_PATH = ROOT / "output" / "dealers_final.json"
FORD_API_URL = "https://www.ford.com/cxservices/dealer/Dealers.json"
FORD_APPLICATION_ID = "07152898-698b-456e-be56-d3d83011d0a6"
FORD_MAKE = "Ford"
FORD_MAKE_ID = "15"
STATE_SLUG = "new-jersey"
REQUEST_TIMEOUT = 30


def resolve_input_dir() -> Path:
    for candidate in INPUT_DIR_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find an input directory. Checked: inputs, input")


def load_zip_codes() -> list[str]:
    input_dir = resolve_input_dir()
    zip_codes_path = input_dir / "zip_codes.json"
    payload = json.loads(zip_codes_path.read_text())
    zip_codes = payload.get("zip_codes", [])
    if not isinstance(zip_codes, list):
        raise ValueError(f"Invalid zip code payload in {zip_codes_path}")
    return [str(zip_code).zfill(5) for zip_code in zip_codes]


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


def build_dealer_record(raw_dealer: dict) -> dict | None:
    address = raw_dealer.get("Address") or {}
    if address.get("State") != "NJ":
        return None

    website = raw_dealer.get("URL")
    if not website:
        return None

    return {
        "name": raw_dealer.get("Name", "").strip(),
        "make": FORD_MAKE,
        "make_id": FORD_MAKE_ID,
        "state": STATE_SLUG,
        "dealership_website": website.strip(),
    }


def collect_ford_dealers(zip_codes: list[str]) -> list[dict]:
    ordered_dealers: list[dict] = []
    seen_pacodes: set[str] = set()

    for zip_code in zip_codes:
        for raw_dealer in fetch_ford_dealers_for_zip(zip_code):
            pacode = str(raw_dealer.get("PACode", "")).strip()
            if not pacode or pacode in seen_pacodes:
                continue

            dealer_record = build_dealer_record(raw_dealer)
            if not dealer_record:
                continue

            seen_pacodes.add(pacode)
            ordered_dealers.append(dealer_record)

    return ordered_dealers


def merge_ford_dealers(output_path: Path, ford_dealers: list[dict]) -> tuple[int, int]:
    all_dealers = json.loads(output_path.read_text())
    ford_indexes = [index for index, dealer in enumerate(all_dealers) if dealer.get("make_id") == FORD_MAKE_ID]

    if ford_indexes:
        insert_at = ford_indexes[0]
        remaining_dealers = [dealer for dealer in all_dealers if dealer.get("make_id") != FORD_MAKE_ID]
    else:
        insert_at = len(all_dealers)
        remaining_dealers = all_dealers

    merged = remaining_dealers[:insert_at] + ford_dealers + remaining_dealers[insert_at:]
    output_path.write_text(json.dumps(merged, indent=2) + "\n")
    return len(ford_indexes), len(ford_dealers)


def main() -> None:
    zip_codes = load_zip_codes()
    ford_dealers = collect_ford_dealers(zip_codes)
    previous_count, new_count = merge_ford_dealers(OUTPUT_PATH, ford_dealers)
    print(
        f"Updated {OUTPUT_PATH} with {new_count} Ford dealers "
        f"(replaced {previous_count} existing Ford entries)."
    )


if __name__ == "__main__":
    main()

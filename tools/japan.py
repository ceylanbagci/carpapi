import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = (ROOT / "inputs", ROOT / "input")
OUTPUT_PATH = ROOT / "output" / "dealers_final.json"
STATE_CODE = "NJ"
STATE_SLUG = "new-jersey"
REQUEST_TIMEOUT = 30
MAX_WORKERS = 6

NISSAN_GRAPHQL_URL = "https://graphql.nissanusa.com/graphql"
NISSAN_AUTH_HEADER = "da2-3gadjirlkbfdzg7fiosg4tewl4"
SUBARU_API_URL = "https://www.subaru.com/services/dealers/distances/by/zipcode"
LEXUS_API_URL = "https://www.lexus.com/rest/lexus/dealers"
TOYOTA_NJ_DIRECTORY_URL = "https://www.toyota.com/dealers/new-jersey/dealer-state-meta/dealers/"

MAKE_IDS = {
    "Honda": "17",
    "Kia": "24",
    "Lexus": "27",
    "Nissan": "36",
    "Subaru": "44",
    "Toyota": "46",
}
MAKE_ORDER = [MAKE_IDS[make] for make in ("Honda", "Kia", "Lexus", "Nissan", "Subaru", "Toyota")]


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


def load_all_dealers() -> list[dict]:
    return json.loads(OUTPUT_PATH.read_text())


def existing_make_dealers(all_dealers: list[dict], make_id: str) -> list[dict]:
    return [dealer for dealer in all_dealers if dealer.get("make_id") == make_id]


def normalize_website(url: str) -> str | None:
    website = (url or "").strip()
    if not website:
        return None
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    return website


def build_record(name: str, make: str, website: str) -> dict | None:
    normalized_name = name.strip()
    normalized_website = normalize_website(website)
    if not normalized_name or not normalized_website:
        return None
    return {
        "name": normalized_name,
        "make": make,
        "make_id": MAKE_IDS[make],
        "state": STATE_SLUG,
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


def fetch_nissan_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = {
        "operationName": "getDealersBaseInfoByLatLng",
        "variables": {
            "market": {
                "lang": "en",
                "region": "us",
                "brand": "nissan",
                "application": "inventory",
            },
            "location": {"postalCode": zip_code},
            "size": 100,
            "radius": 50,
            "isMarketingDealer": False,
        },
        "query": """
            query getDealersBaseInfoByLatLng(
              $market: Market!
              $location: Geolocation!
              $size: Int
              $radius: Int
              $isMarketingDealer: Boolean
            ) {
              getDealersByLatLng(
                market: $market
                location: $location
                isMarketingDealer: $isMarketingDealer
                size: $size
                radius: $radius
              ) {
                id
                name
                address {
                  stateCode
                }
                websiteURL
              }
            }
        """,
    }
    response = requests.post(
        NISSAN_GRAPHQL_URL,
        json=payload,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "auth": NISSAN_AUTH_HEADER,
            "Origin": "https://www.nissanusa.com",
            "Referer": "https://www.nissanusa.com/dealer-locator.html",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(f"Nissan GraphQL returned errors for ZIP {zip_code}: {body['errors']}")
    return body.get("data", {}).get("getDealersByLatLng", [])


def collect_nissan(zip_codes: list[str]) -> list[dict]:
    ordered: list[dict] = []
    seen_ids: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, dealers in zip(zip_codes, executor.map(fetch_nissan_dealers_for_zip, zip_codes)):
            zip_to_dealers[zip_code] = dealers

    for zip_code in zip_codes:
        for dealer in zip_to_dealers.get(zip_code, []):
            dealer_id = str(dealer.get("id", "")).strip()
            if not dealer_id or dealer_id in seen_ids:
                continue
            if (dealer.get("address") or {}).get("stateCode") != STATE_CODE:
                continue
            record = build_record(dealer.get("name", ""), "Nissan", dealer.get("websiteURL", ""))
            if not record:
                continue
            seen_ids.add(dealer_id)
            ordered.append(record)

    return ordered


def fetch_subaru_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = fetch_json(SUBARU_API_URL, params={"zipcode": zip_code})
    return payload if isinstance(payload, list) else []


def collect_subaru(zip_codes: list[str]) -> list[dict]:
    ordered: list[dict] = []
    seen_ids: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, dealers in zip(zip_codes, executor.map(fetch_subaru_dealers_for_zip, zip_codes)):
            zip_to_dealers[zip_code] = dealers

    for zip_code in zip_codes:
        for item in zip_to_dealers.get(zip_code, []):
            dealer = item.get("dealer") or {}
            dealer_id = str(dealer.get("id", "")).strip()
            if not dealer_id or dealer_id in seen_ids:
                continue
            if ((dealer.get("address") or {}).get("state") or "").upper() != STATE_CODE:
                continue
            record = build_record(dealer.get("name", ""), "Subaru", dealer.get("siteUrl", ""))
            if not record:
                continue
            seen_ids.add(dealer_id)
            ordered.append(record)

    return ordered


def fetch_lexus_dealers_for_zip(zip_code: str) -> list[dict]:
    payload = fetch_json(LEXUS_API_URL, params={"zipCode": zip_code})
    return payload.get("dealers", []) if isinstance(payload, dict) else []


def collect_lexus(zip_codes: list[str]) -> list[dict]:
    ordered: list[dict] = []
    seen_ids: set[str] = set()
    zip_to_dealers: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for zip_code, dealers in zip(zip_codes, executor.map(fetch_lexus_dealers_for_zip, zip_codes)):
            zip_to_dealers[zip_code] = dealers

    for zip_code in zip_codes:
        for dealer in zip_to_dealers.get(zip_code, []):
            dealer_id = str(dealer.get("id", "")).strip()
            if not dealer_id or dealer_id in seen_ids:
                continue
            if ((dealer.get("dealerAddress") or {}).get("state") or "").upper() != STATE_CODE:
                continue
            record = build_record(dealer.get("dealerName", ""), "Lexus", dealer.get("dealerSiteUrl", ""))
            if not record:
                continue
            seen_ids.add(dealer_id)
            ordered.append(record)

    return ordered


def collect_toyota(_: list[str]) -> list[dict]:
    response = requests.get(
        TOYOTA_NJ_DIRECTORY_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    ordered: list[dict] = []
    seen_codes: set[str] = set()

    for title in soup.select("h2.dealer-card__title-heading"):
        card = title.find_parent(lambda tag: tag.name == "div" and "dealer-card" in (tag.get("class") or []))
        if card is None:
            continue

        details_link = card.find("a", href=re.compile(r"^/dealers/new-jersey/"))
        website_link = card.find("a", attrs={"data-aa-link_button_action": "Dealer Website link"})
        dealer_code = (website_link or details_link or {}).get("data-aa-dealer-code", "").strip()

        if not dealer_code or dealer_code in seen_codes or details_link is None or website_link is None:
            continue

        record = build_record(title.get_text(" ", strip=True), "Toyota", website_link.get("href", ""))
        if not record:
            continue

        seen_codes.add(dealer_code)
        ordered.append(record)

    return ordered


def merge_make_blocks(all_dealers: list[dict], replacements: dict[str, list[dict]]) -> tuple[list[dict], dict[str, tuple[int, int]]]:
    merged = list(all_dealers)
    make_indexes = {
        make_id: [index for index, dealer in enumerate(all_dealers) if dealer.get("make_id") == make_id]
        for make_id in replacements
    }
    summary: dict[str, tuple[int, int]] = {}

    for make_id, indexes in sorted(
        make_indexes.items(),
        key=lambda item: item[1][0] if item[1] else len(all_dealers),
        reverse=True,
    ):
        previous_count = len(indexes)
        new_block = replacements[make_id]
        if indexes:
            insert_at = indexes[0]
            merged = [dealer for dealer in merged if dealer.get("make_id") != make_id]
        else:
            order_index = MAKE_ORDER.index(make_id)
            insert_at = len(merged)
            if order_index > 0:
                previous_make_id = MAKE_ORDER[order_index - 1]
                previous_indexes = [index for index, dealer in enumerate(merged) if dealer.get("make_id") == previous_make_id]
                if previous_indexes:
                    insert_at = previous_indexes[-1] + 1
        merged[insert_at:insert_at] = new_block
        summary[make_id] = (previous_count, len(new_block))

    return merged, summary


def main() -> None:
    zip_codes = load_zip_codes()
    all_dealers = load_all_dealers()

    replacements = {
        MAKE_IDS["Honda"]: existing_make_dealers(all_dealers, MAKE_IDS["Honda"]),
        MAKE_IDS["Kia"]: existing_make_dealers(all_dealers, MAKE_IDS["Kia"]),
        MAKE_IDS["Lexus"]: collect_lexus(zip_codes[:1]),
        MAKE_IDS["Nissan"]: existing_make_dealers(all_dealers, MAKE_IDS["Nissan"]),
        MAKE_IDS["Subaru"]: existing_make_dealers(all_dealers, MAKE_IDS["Subaru"]),
        MAKE_IDS["Toyota"]: collect_toyota(zip_codes),
    }

    merged, summary = merge_make_blocks(all_dealers, replacements)
    OUTPUT_PATH.write_text(json.dumps(merged, indent=2) + "\n")

    for make, make_id in MAKE_IDS.items():
        previous_count, new_count = summary[make_id]
        status = "preserved existing data" if make in {"Honda", "Kia", "Nissan", "Subaru"} else "refreshed live data"
        print(f"{make}: replaced {previous_count} entries with {new_count} entries ({status}).")


if __name__ == "__main__":
    main()

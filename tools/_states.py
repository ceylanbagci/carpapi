"""Shared state-code helpers for the dealer-locator scrapers.

The maker scrapers in `tools/` were originally hard-coded to New Jersey.
This module centralizes the per-state mapping + a zip-loader that
filters our local ZIP dataset to the requested state. No DB dependency
— reads `input/zip_codes_full.json` (loaded once from GeoNames).

Usage:

    from tools._states import load_zips_for_state, state_slug, state_name

    args = parse_args()                       # --state CA
    state = args.state.upper()
    zips = load_zips_for_state(state)         # ["90001", "90002", ...]
    slug = state_slug(state)                  # "california"

Slugs match the URL conventions used by Ford, Toyota, Honda, etc.
(lowercase, hyphenated). Two-letter codes match USPS / GeoNames.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_INPUT_FULL = _ROOT / "input" / "zip_codes_full.json"


# USPS 2-letter code → (canonical name, URL slug). Includes all 50 states +
# DC and the 5 inhabited territories. The military codes AA/AE/AP exist in
# our zip data too but no dealer locator serves them; skipped intentionally.
STATES: dict[str, tuple[str, str]] = {
    "AL": ("Alabama", "alabama"),
    "AK": ("Alaska", "alaska"),
    "AZ": ("Arizona", "arizona"),
    "AR": ("Arkansas", "arkansas"),
    "CA": ("California", "california"),
    "CO": ("Colorado", "colorado"),
    "CT": ("Connecticut", "connecticut"),
    "DE": ("Delaware", "delaware"),
    "DC": ("District of Columbia", "district-of-columbia"),
    "FL": ("Florida", "florida"),
    "GA": ("Georgia", "georgia"),
    "HI": ("Hawaii", "hawaii"),
    "ID": ("Idaho", "idaho"),
    "IL": ("Illinois", "illinois"),
    "IN": ("Indiana", "indiana"),
    "IA": ("Iowa", "iowa"),
    "KS": ("Kansas", "kansas"),
    "KY": ("Kentucky", "kentucky"),
    "LA": ("Louisiana", "louisiana"),
    "ME": ("Maine", "maine"),
    "MD": ("Maryland", "maryland"),
    "MA": ("Massachusetts", "massachusetts"),
    "MI": ("Michigan", "michigan"),
    "MN": ("Minnesota", "minnesota"),
    "MS": ("Mississippi", "mississippi"),
    "MO": ("Missouri", "missouri"),
    "MT": ("Montana", "montana"),
    "NE": ("Nebraska", "nebraska"),
    "NV": ("Nevada", "nevada"),
    "NH": ("New Hampshire", "new-hampshire"),
    "NJ": ("New Jersey", "new-jersey"),
    "NM": ("New Mexico", "new-mexico"),
    "NY": ("New York", "new-york"),
    "NC": ("North Carolina", "north-carolina"),
    "ND": ("North Dakota", "north-dakota"),
    "OH": ("Ohio", "ohio"),
    "OK": ("Oklahoma", "oklahoma"),
    "OR": ("Oregon", "oregon"),
    "PA": ("Pennsylvania", "pennsylvania"),
    "RI": ("Rhode Island", "rhode-island"),
    "SC": ("South Carolina", "south-carolina"),
    "SD": ("South Dakota", "south-dakota"),
    "TN": ("Tennessee", "tennessee"),
    "TX": ("Texas", "texas"),
    "UT": ("Utah", "utah"),
    "VT": ("Vermont", "vermont"),
    "VA": ("Virginia", "virginia"),
    "WA": ("Washington", "washington"),
    "WV": ("West Virginia", "west-virginia"),
    "WI": ("Wisconsin", "wisconsin"),
    "WY": ("Wyoming", "wyoming"),
    "PR": ("Puerto Rico", "puerto-rico"),
    "VI": ("U.S. Virgin Islands", "us-virgin-islands"),
    "GU": ("Guam", "guam"),
    "AS": ("American Samoa", "american-samoa"),
    "MP": ("Northern Mariana Islands", "northern-mariana-islands"),
}


# The 50 states + DC. Most maker locators don't serve territories, so by
# default scrape over ALL_STATES rather than STATES.keys().
ALL_STATES: list[str] = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL",
    "IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE",
    "NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD",
    "TN","TX","UT","VT","VA","WA","WV","WI","WY",
]


def state_name(code: str) -> str:
    code = code.upper()
    if code not in STATES:
        raise KeyError(f"Unknown state code: {code!r}")
    return STATES[code][0]


def state_slug(code: str) -> str:
    code = code.upper()
    if code not in STATES:
        raise KeyError(f"Unknown state code: {code!r}")
    return STATES[code][1]


@lru_cache(maxsize=1)
def _full_zip_index() -> dict[str, list[str]]:
    """Read input/zip_codes_full.json once and bucket by state code."""
    if not _INPUT_FULL.exists():
        raise FileNotFoundError(
            f"{_INPUT_FULL} missing. Run the GeoNames import "
            f"(see scripts and input/raw/geonames_us.zip)."
        )
    by_state: dict[str, list[str]] = {}
    for row in json.loads(_INPUT_FULL.read_text()):
        st = (row.get("state") or "").upper()
        if not st:
            continue
        z = str(row.get("zip_code") or "").zfill(5)
        if z:
            by_state.setdefault(st, []).append(z)
    # de-dup + sort each bucket so successive runs are deterministic
    for st in by_state:
        by_state[st] = sorted(set(by_state[st]))
    return by_state


def load_zips_for_state(code: str) -> list[str]:
    """Return all 5-digit ZIP codes in the given state (USPS code)."""
    return list(_full_zip_index().get(code.upper(), []))

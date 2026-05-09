from __future__ import annotations

"""ZIP code → (latitude, longitude) centroid lookup.

Starter set covering NJ/NY/PA test queries. For production coverage, replace
the in-memory dict with a loader that reads US Census 2020 ZCTA data (~33k
rows) into Postgres or a parquet file. Until then this module returns None
for unknown ZIPs and the caller must skip the radius filter.
"""

# (lat, lng) for ZIP centroids. Public data, US Census ZCTA / USPS.
_CENTROIDS: dict[str, tuple[float, float]] = {
    # New Jersey
    "07102": (40.7357, -74.1724),  # Newark
    "07302": (40.7178, -74.0431),  # Jersey City
    "07470": (40.9456, -74.2535),  # Wayne
    "07501": (40.9168, -74.1718),  # Paterson
    "07920": (40.6651, -74.5685),  # Basking Ridge
    "08540": (40.3573, -74.6672),  # Princeton
    "08902": (40.4862, -74.4519),  # North Brunswick
    # New York
    "10001": (40.7506, -73.9972),  # Manhattan / Chelsea
    "10128": (40.7816, -73.9521),  # Upper East Side
    "11201": (40.6940, -73.9903),  # Brooklyn Heights
    "11375": (40.7220, -73.8459),  # Forest Hills
    # Pennsylvania
    "19103": (39.9523, -75.1722),  # Philadelphia / Rittenhouse
    "19087": (40.0570, -75.4002),  # Wayne, PA
    # Connecticut
    "06830": (41.0262, -73.6285),  # Greenwich
}


def lookup(zip_code: str | None) -> tuple[float, float] | None:
    """Return (lat, lng) centroid for a 5-digit US ZIP, or None if unknown."""
    if not zip_code:
        return None
    return _CENTROIDS.get(zip_code.strip())


def known_zips() -> list[str]:
    return sorted(_CENTROIDS.keys())

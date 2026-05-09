from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from carapi_pipeline.dedupe import normalize_vin
from carapi_pipeline.pii import redact_pii


def _schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "schema" / "car_listing.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


_SCHEMA_CACHE: dict[str, Any] | None = None


def listing_schema() -> dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = _schema()
    return _SCHEMA_CACHE


def parse_iso_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_listing_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply light normalization before JSON Schema validation."""
    data = dict(raw)
    vin = normalize_vin(data.get("vin"))
    data["vin"] = vin
    if not data.get("mileage_unit"):
        data["mileage_unit"] = "unknown"
    if not data.get("currency"):
        data["currency"] = "USD"

    # Strip phone/email PII from free-text fields BEFORE persistence and
    # BEFORE simhash dedup. See context/compliance-rules.md.
    redacted_desc, _ = redact_pii(data.get("description"))
    data["description"] = redacted_desc
    redacted_title, _ = redact_pii(data.get("title"))
    if redacted_title is not None:
        data["title"] = redacted_title

    jsonschema.validate(instance=data, schema=listing_schema())
    return data


def load_fixture(name: str = "sample_listings.json") -> list[dict[str, Any]]:
    """Load packaged JSON array of listings."""
    path = Path(__file__).resolve().parent / "fixtures" / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Fixture must be a JSON array")
    return payload

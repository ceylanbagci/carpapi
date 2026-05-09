from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from carapi_pipeline.models import Listing
from carapi_pipeline.zip_centroids import lookup as zip_lookup

_EARTH_RADIUS_MILES = 3958.7613


def _car_query_schema() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3] / "schema" / "car_query.schema.json"
    return json.loads(root.read_text(encoding="utf-8"))


_SCHEMA: dict[str, Any] | None = None


def car_query_schema() -> dict[str, Any]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = _car_query_schema()
    return _SCHEMA


def validate_car_query(obj: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=obj, schema=car_query_schema())
    return obj


def build_select(q: dict[str, Any]) -> Select:
    stmt = select(Listing)
    if q.get("make"):
        stmt = stmt.where(Listing.make.ilike(q["make"]))
    if q.get("model"):
        stmt = stmt.where(Listing.model.ilike(q["model"]))
    if q.get("body_style"):
        stmt = stmt.where(Listing.body_style.ilike(q["body_style"]))
    if q.get("year_min") is not None:
        stmt = stmt.where(Listing.year >= int(q["year_min"]))
    if q.get("year_max") is not None:
        stmt = stmt.where(Listing.year <= int(q["year_max"]))
    if q.get("price_min") is not None:
        stmt = stmt.where(Listing.price_amount >= float(q["price_min"]))
    if q.get("price_max") is not None:
        stmt = stmt.where(Listing.price_amount <= float(q["price_max"]))
    if q.get("mileage_max") is not None:
        stmt = stmt.where(Listing.mileage <= float(q["mileage_max"]))
    if q.get("region"):
        stmt = stmt.where(Listing.region.ilike(q["region"]))

    zip_code = q.get("zip_code")
    radius_miles = q.get("radius_miles")
    if zip_code and radius_miles:
        centroid = zip_lookup(zip_code)
        if centroid is not None:
            center_lat, center_lng = centroid
            cos_term = (
                func.cos(func.radians(center_lat))
                * func.cos(func.radians(Listing.latitude))
                * func.cos(func.radians(Listing.longitude) - func.radians(center_lng))
                + func.sin(func.radians(center_lat))
                * func.sin(func.radians(Listing.latitude))
            )
            clamped = func.least(func.greatest(cos_term, -1.0), 1.0)
            distance_miles = _EARTH_RADIUS_MILES * func.acos(clamped)
            stmt = stmt.where(
                Listing.latitude.is_not(None),
                Listing.longitude.is_not(None),
                distance_miles <= float(radius_miles),
            )

    limit = int(q.get("limit") or 10)
    stmt = stmt.order_by(Listing.price_amount.asc().nullslast())
    stmt = stmt.limit(min(max(limit, 1), 50))
    return stmt


def run_car_query(session: Session, q: dict[str, Any]) -> list[Listing]:
    validate_car_query(q)
    return list(session.scalars(build_select(q)))

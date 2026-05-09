from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from carapi_pipeline.dedupe import build_dedupe_key
from carapi_pipeline.metrics import pipeline_summary_metrics
from carapi_pipeline.models import Listing
from carapi_pipeline.normalize import normalize_listing_dict, parse_iso_dt
from carapi_pipeline.raw_store import write_raw_payload
from carapi_pipeline.settings import Settings

log = logging.getLogger(__name__)


def _priority(settings: Settings, source_id: str) -> int:
    return settings.source_priority.get(source_id, settings.source_priority.get("default", 0))


def _listing_from_doc(
    doc: dict[str, Any],
    dedupe_key: str,
    *,
    dealer_id: uuid.UUID | None = None,
) -> Listing:
    scraped = parse_iso_dt(doc["scraped_at"])
    if scraped is None:
        scraped = datetime.now(timezone.utc)
    listing_url = doc["listing_url"]
    is_on_sale = bool(doc.get("is_on_sale", False))
    return Listing(
        dedupe_key=dedupe_key,
        source_id=doc["source_id"],
        source_name=doc["source_name"],
        external_id=doc["external_id"],
        listing_url=listing_url,
        title=doc["title"],
        description=doc.get("description"),
        make=doc.get("make"),
        model=doc.get("model"),
        trim=doc.get("trim"),
        year=doc.get("year"),
        body_style=doc.get("body_style"),
        vin=doc.get("vin"),
        mileage=float(doc["mileage"]) if doc.get("mileage") is not None else None,
        mileage_unit=doc.get("mileage_unit") or "unknown",
        price_amount=float(doc["price_amount"]) if doc.get("price_amount") is not None else None,
        currency=doc["currency"],
        monthly_payment_estimate=(
            float(doc["monthly_payment_estimate"])
            if doc.get("monthly_payment_estimate") is not None
            else None
        ),
        seller_name=doc.get("seller_name"),
        seller_type=doc.get("seller_type"),
        latitude=float(doc["latitude"]) if doc.get("latitude") is not None else None,
        longitude=float(doc["longitude"]) if doc.get("longitude") is not None else None,
        region=doc.get("region"),
        city=doc.get("city"),
        postal_code=doc.get("postal_code"),
        listing_posted_at=parse_iso_dt(doc.get("listing_posted_at")),
        listing_updated_at=parse_iso_dt(doc.get("listing_updated_at")),
        scraped_at=scraped,
        raw_checksum=doc.get("raw_checksum"),
        features=doc.get("features"),
        images=doc.get("images"),
        raw_document=doc,
        # carpapi DB extensions:
        car_url=listing_url,
        dealer_id=dealer_id,
        is_on_sale=is_on_sale,
    )


def _resolve_dealer_id(session: Session, source_id: str) -> uuid.UUID | None:
    """Look up dealers.id by slug == source_id. Returns None when no match.

    Cheap because callers cache the result for the duration of a batch.
    """
    from sqlalchemy import text as sql_text

    row = session.execute(
        sql_text(
            "SELECT id FROM public.dealers WHERE slug = :slug LIMIT 1"
        ),
        {"slug": source_id},
    ).first()
    return row[0] if row is not None else None


def _should_replace(existing: Listing, new_doc: dict[str, Any], settings: Settings) -> bool:
    new_p = _priority(settings, new_doc["source_id"])
    old_p = _priority(settings, existing.source_id)
    if new_p > old_p:
        return True
    if new_p < old_p:
        return False
    new_ts = parse_iso_dt(new_doc.get("listing_updated_at")) or parse_iso_dt(new_doc.get("scraped_at"))
    old_ts = existing.listing_updated_at or existing.scraped_at
    if new_ts and old_ts and new_ts > old_ts:
        return True
    if new_ts and old_ts and new_ts < old_ts:
        return False
    new_sc = parse_iso_dt(new_doc.get("scraped_at"))
    return bool(new_sc and new_sc > existing.scraped_at)


def upsert_listing(
    session: Session,
    doc: dict[str, Any],
    settings: Settings,
    *,
    dealer_id: uuid.UUID | None = None,
) -> str:
    """Insert or update by dedupe_key. Returns 'inserted', 'updated', or 'skipped'."""
    dedupe_key = build_dedupe_key(doc)
    row = session.execute(select(Listing).where(Listing.dedupe_key == dedupe_key)).scalar_one_or_none()
    candidate = _listing_from_doc(doc, dedupe_key, dealer_id=dealer_id)
    if row is None:
        session.add(candidate)
        return "inserted"
    if _should_replace(row, doc, settings):
        for attr in (
            "source_id",
            "source_name",
            "external_id",
            "listing_url",
            "title",
            "description",
            "make",
            "model",
            "trim",
            "year",
            "body_style",
            "vin",
            "mileage",
            "mileage_unit",
            "price_amount",
            "currency",
            "monthly_payment_estimate",
            "seller_name",
            "seller_type",
            "latitude",
            "longitude",
            "region",
            "city",
            "postal_code",
            "listing_posted_at",
            "listing_updated_at",
            "scraped_at",
            "raw_checksum",
            "features",
            "images",
            "raw_document",
            # carpapi DB extensions:
            "car_url",
            "dealer_id",
            "is_on_sale",
        ):
            setattr(row, attr, getattr(candidate, attr))
        return "updated"
    return "skipped"


def run_ingest_batch(
    session: Session,
    settings: Settings,
    docs: list[dict[str, Any]],
    *,
    source_id: str,
    batch_id: str | None = None,
) -> dict[str, int]:
    batch_id = batch_id or str(uuid.uuid4())
    counts = {"RecordsFetched": 0, "RecordsNormalized": 0, "RecordsInserted": 0, "RecordsUpdated": 0, "RecordsSkipped": 0, "RecordsRejected": 0}
    started_at = time.monotonic()

    # Resolve dealer FK once per batch (source_id == dealers.slug).
    dealer_id = _resolve_dealer_id(session, source_id)

    for doc in docs:
        counts["RecordsFetched"] += 1
        try:
            checksum = write_raw_payload(settings=settings, source_id=source_id, batch_id=batch_id, payload=doc)
            norm = normalize_listing_dict(dict(doc))
            norm["raw_checksum"] = checksum
            outcome = upsert_listing(session, norm, settings, dealer_id=dealer_id)
            counts["RecordsNormalized"] += 1
            if outcome == "inserted":
                counts["RecordsInserted"] += 1
            elif outcome == "updated":
                counts["RecordsUpdated"] += 1
            else:
                counts["RecordsSkipped"] += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("Reject record: %s", exc)
            counts["RecordsRejected"] += 1

    pipeline_summary_metrics(
        settings,
        counts,
        source_id=source_id,
        duration_seconds=time.monotonic() - started_at,
    )
    return counts


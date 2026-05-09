from __future__ import annotations

"""Domain-grouped query helpers.

Repositories hide SQLAlchemy mechanics from callers. Each method takes a
Session as its first arg so the caller controls the transaction (typically
via `with session_scope() as s: DealerRepo.upsert(s, ...)`).

These are intentionally thin — they centralize the most common access
patterns; ad-hoc queries can still drop down to plain SQLAlchemy.
"""

import datetime as dt
import logging
import re
import uuid
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from carpapi.db.models import (
    AICall,
    DailyReport,
    Dealer,
    IngestRun,
    ListingGroup,
    RawPayload,
    RejectionLog,
    ScrapeMonitorReport,
    Source,
    TokenCacheRow,
)

log = logging.getLogger(__name__)


# --------------------------------------------------------------------- #
# Dealer
# --------------------------------------------------------------------- #


class DealerRepo:
    @staticmethod
    def slugify(name: str) -> str:
        """Stable, URL-safe slug from a dealer name. Used as the natural key."""
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return slug[:200] or "unnamed"

    @staticmethod
    def get_by_slug(session: Session, slug: str) -> Optional[Dealer]:
        return session.scalar(select(Dealer).where(Dealer.slug == slug))

    @staticmethod
    def list_active(session: Session, *, region: Optional[str] = None) -> list[Dealer]:
        stmt = select(Dealer).where(Dealer.status == "active")
        if region:
            stmt = stmt.where(Dealer.region == region)
        return list(session.scalars(stmt))

    @staticmethod
    def upsert(session: Session, fields: dict[str, Any]) -> Dealer:
        """Insert-or-update by `slug` (the natural key).

        `fields` must include `slug` and `name`. All other columns optional.
        Returns the persisted row.
        """
        if "slug" not in fields or "name" not in fields:
            raise ValueError("DealerRepo.upsert requires at least 'slug' and 'name'")

        existing = DealerRepo.get_by_slug(session, fields["slug"])
        now = dt.datetime.now(dt.timezone.utc)
        if existing is None:
            row = Dealer(**fields)
            session.add(row)
            session.flush()
            return row
        for k, v in fields.items():
            if k == "slug":
                continue
            setattr(existing, k, v)
        existing.updated_at = now
        session.flush()
        return existing

    @staticmethod
    def mark_scraped(session: Session, slug: str, *, when: Optional[dt.datetime] = None) -> None:
        when = when or dt.datetime.now(dt.timezone.utc)
        dealer = DealerRepo.get_by_slug(session, slug)
        if dealer is None:
            return
        dealer.last_scraped_at = when
        dealer.updated_at = when
        session.flush()

    @staticmethod
    def cms_breakdown(session: Session) -> dict[str, int]:
        """Return {cms_id -> dealer_count} for active dealers."""
        from sqlalchemy import func

        stmt = (
            select(Dealer.cms, func.count(Dealer.id))
            .where(Dealer.status == "active")
            .group_by(Dealer.cms)
        )
        return {row[0] or "unknown": int(row[1]) for row in session.execute(stmt)}


# --------------------------------------------------------------------- #
# Source
# --------------------------------------------------------------------- #


class SourceRepo:
    @staticmethod
    def get(session: Session, source_id: str) -> Optional[Source]:
        return session.get(Source, source_id)

    @staticmethod
    def list_enabled(session: Session) -> list[Source]:
        return list(session.scalars(select(Source).where(Source.enabled.is_(True))))

    @staticmethod
    def upsert(session: Session, fields: dict[str, Any]) -> Source:
        if "id" not in fields or "name" not in fields or "type" not in fields:
            raise ValueError("SourceRepo.upsert requires 'id', 'name', and 'type'")
        existing = session.get(Source, fields["id"])
        if existing is None:
            row = Source(**fields)
            session.add(row)
            session.flush()
            return row
        for k, v in fields.items():
            if k == "id":
                continue
            setattr(existing, k, v)
        existing.updated_at = dt.datetime.now(dt.timezone.utc)
        session.flush()
        return existing

    @staticmethod
    def priority_map(session: Session) -> dict[str, int]:
        """Return {source_id: priority} for survivorship in dedup."""
        return {s.id: s.priority for s in session.scalars(select(Source))}


# --------------------------------------------------------------------- #
# ListingGroup
# --------------------------------------------------------------------- #


class ListingGroupRepo:
    @staticmethod
    def get_or_create_by_vin(
        session: Session,
        vin: str,
        *,
        make: Optional[str] = None,
        model: Optional[str] = None,
        trim: Optional[str] = None,
        year: Optional[int] = None,
    ) -> ListingGroup:
        existing = session.scalar(
            select(ListingGroup).where(ListingGroup.canonical_vin == vin)
        )
        if existing is not None:
            return existing
        row = ListingGroup(
            canonical_vin=vin,
            canonical_make=make,
            canonical_model=model,
            canonical_trim=trim,
            canonical_year=year,
        )
        session.add(row)
        session.flush()
        return row


# --------------------------------------------------------------------- #
# Ingest (runs + raw payloads + rejections)
# --------------------------------------------------------------------- #


class IngestRepo:
    @staticmethod
    def start_run(
        session: Session,
        *,
        source_id: str,
        run_kind: str = "scheduled",
        batch_id: Optional[uuid.UUID] = None,
    ) -> IngestRun:
        run = IngestRun(
            source_id=source_id,
            run_kind=run_kind,
            batch_id=batch_id,
            status="running",
        )
        session.add(run)
        session.flush()
        return run

    @staticmethod
    def finish_run(
        session: Session,
        run_id: uuid.UUID,
        *,
        counts: dict[str, int],
        duration_seconds: float,
        status: str = "success",
        error_summary: Optional[dict] = None,
    ) -> None:
        # ORM-style update: load, mutate, let the session flush. This keeps
        # the identity map coherent — a subsequent session.get(IngestRun)
        # in the same session sees the new attribute values without an
        # extra refresh dance.
        run = session.get(IngestRun, run_id)
        if run is None:
            raise LookupError(f"IngestRun {run_id} not found (cannot finish_run)")
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.counts = counts
        run.duration_seconds = Decimal(str(round(duration_seconds, 3)))
        run.status = status
        run.error_summary = error_summary
        session.flush()

    @staticmethod
    def store_raw_pointer(
        session: Session,
        *,
        source_id: str,
        ingest_run_id: uuid.UUID,
        external_id: str,
        s3_uri: Optional[str] = None,
        raw_checksum: Optional[str] = None,
    ) -> RawPayload:
        rp = RawPayload(
            source_id=source_id,
            ingest_run_id=ingest_run_id,
            external_id=external_id,
            s3_uri=s3_uri,
            raw_checksum=raw_checksum,
        )
        session.add(rp)
        session.flush()
        return rp

    @staticmethod
    def attach_listing(
        session: Session, *, raw_payload_id: uuid.UUID, listing_id: uuid.UUID
    ) -> None:
        rp = session.get(RawPayload, raw_payload_id)
        if rp is not None:
            rp.listing_id = listing_id
            session.flush()

    @staticmethod
    def log_rejection(
        session: Session,
        *,
        ingest_run_id: Optional[uuid.UUID],
        source_id: str,
        reason: str,
        error_class: Optional[str] = None,
        snippet: Optional[str] = None,
        raw_payload_id: Optional[uuid.UUID] = None,
    ) -> None:
        session.add(
            RejectionLog(
                ingest_run_id=ingest_run_id,
                source_id=source_id,
                raw_payload_id=raw_payload_id,
                reason=reason,
                error_class=error_class,
                snippet=snippet[:500] if snippet else None,
            )
        )


# --------------------------------------------------------------------- #
# Monitor
# --------------------------------------------------------------------- #


class MonitorRepo:
    @staticmethod
    def insert_scrape_report(
        session: Session,
        *,
        ingest_run_id: Optional[uuid.UUID],
        source_id: str,
        record_count: int,
        null_rates: dict[str, float],
        duplicate_rate: float,
        http_error_rate: float,
        flags: list[str],
        healthy: bool,
    ) -> ScrapeMonitorReport:
        row = ScrapeMonitorReport(
            ingest_run_id=ingest_run_id,
            source_id=source_id,
            record_count=record_count,
            null_rates=null_rates,
            duplicate_rate=Decimal(str(round(duplicate_rate, 4))),
            http_error_rate=Decimal(str(round(http_error_rate, 4))),
            flags=flags,
            healthy=healthy,
        )
        session.add(row)
        session.flush()
        return row

    @staticmethod
    def upsert_daily_report(
        session: Session,
        *,
        report_date: dt.date,
        summary: dict,
        per_source: dict,
        markdown: str,
    ) -> DailyReport:
        existing = session.scalar(
            select(DailyReport).where(DailyReport.report_date == report_date)
        )
        if existing is None:
            row = DailyReport(
                report_date=report_date,
                summary=summary,
                per_source=per_source,
                markdown=markdown,
            )
            session.add(row)
            session.flush()
            return row
        existing.summary = summary
        existing.per_source = per_source
        existing.markdown = markdown
        existing.generated_at = dt.datetime.now(dt.timezone.utc)
        session.flush()
        return existing

    @staticmethod
    def latest_for_source(
        session: Session, source_id: str, *, limit: int = 7
    ) -> list[ScrapeMonitorReport]:
        stmt = (
            select(ScrapeMonitorReport)
            .where(ScrapeMonitorReport.source_id == source_id)
            .order_by(ScrapeMonitorReport.created_at.desc())
            .limit(limit)
        )
        return list(session.scalars(stmt))


# --------------------------------------------------------------------- #
# AI cache + audit
# --------------------------------------------------------------------- #


class AICacheRepo:
    """Backend operations for ai.token_cache.

    Designed to plug into TokenCache as a CacheBackend (see
    carpapi/cache/token_cache.py — the protocol matches get/set/stats).
    """

    @staticmethod
    def get(session: Session, key: str) -> Optional[str]:
        # Bypass the identity-map cache — for a read-through cache we always
        # want the current value from the DB (a recent .set() in this same
        # session might not be visible via session.get()'s cached row).
        row = session.execute(
            select(TokenCacheRow).where(TokenCacheRow.key == key).execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.expires_at < dt.datetime.now(dt.timezone.utc):
            session.delete(row)
            return None
        row.hit_count += 1
        return row.value

    @staticmethod
    def set(
        session: Session,
        key: str,
        value: str,
        ttl_seconds: int,
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        skill: Optional[str] = None,
        raw_size: Optional[int] = None,
        compressed_size: Optional[int] = None,
    ) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        expires = now + dt.timedelta(seconds=ttl_seconds)
        stmt = pg_insert(TokenCacheRow).values(
            key=key,
            value=value,
            model=model,
            max_tokens=max_tokens,
            skill=skill,
            raw_size=raw_size,
            compressed_size=compressed_size,
            hit_count=0,
            created_at=now,
            expires_at=expires,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={
                "value": stmt.excluded.value,
                "model": stmt.excluded.model,
                "max_tokens": stmt.excluded.max_tokens,
                "skill": stmt.excluded.skill,
                "raw_size": stmt.excluded.raw_size,
                "compressed_size": stmt.excluded.compressed_size,
                "expires_at": stmt.excluded.expires_at,
            },
        )
        session.execute(stmt)

    @staticmethod
    def purge_expired(session: Session) -> int:
        from sqlalchemy import delete

        result = session.execute(
            delete(TokenCacheRow).where(
                TokenCacheRow.expires_at < dt.datetime.now(dt.timezone.utc)
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def log_call(
        session: Session,
        *,
        skill: Optional[str],
        model: Optional[str],
        max_tokens: Optional[int],
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        cost_usd: Optional[float],
        latency_ms: Optional[int],
        pii_rejected: bool = False,
        error: Optional[str] = None,
    ) -> AICall:
        row = AICall(
            skill=skill,
            model=model,
            max_tokens=max_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=Decimal(str(round(cost_usd, 6))) if cost_usd is not None else None,
            latency_ms=latency_ms,
            pii_rejected=pii_rejected,
            error=error,
        )
        session.add(row)
        session.flush()
        return row

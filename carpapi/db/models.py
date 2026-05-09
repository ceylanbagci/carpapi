from __future__ import annotations

"""SQLAlchemy ORM models for the carpapi DB adapter.

These mirror carpapi/db/schema.sql (which is the structural source of
truth — DDL is applied via that file, not by Base.metadata.create_all).

The pre-existing `listings` table is owned by carapi_pipeline.models;
we deliberately do NOT redeclare it here. Cross-table joins reference
'public.listings.id' via string FKs.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Interval,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Separate metadata from carapi_pipeline.models.Base. Cross-package
    references are by FK string ('public.listings.id'), not Python imports."""


# --------------------------------------------------------------------- #
# public.listing_groups
# --------------------------------------------------------------------- #


class ListingGroup(Base):
    __tablename__ = "listing_groups"
    __table_args__ = (
        UniqueConstraint("canonical_vin", name="uq_listing_groups_canonical_vin_runtime"),
        Index(
            "ix_listing_groups_make_model_year_runtime",
            "canonical_make",
            "canonical_model",
            "canonical_year",
        ),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_vin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canonical_make: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canonical_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canonical_trim: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canonical_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


# --------------------------------------------------------------------- #
# public.dealers
# --------------------------------------------------------------------- #


class Dealer(Base):
    __tablename__ = "dealers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'blocked')",
            name="ck_dealers_status_runtime",
        ),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    homepage_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inventory_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cms_signals: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    robots_allows_inventory: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    makes_carried: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    last_scraped_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enrolled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


# --------------------------------------------------------------------- #
# public.sources
# --------------------------------------------------------------------- #


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "type IN ('api', 'feed', 'scrape', 'fixture')", name="ck_sources_type_runtime"
        ),
        {"schema": "public"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    license_terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ingest_cadence: Mapped[dt.timedelta] = mapped_column(
        Interval, nullable=False, default=lambda: dt.timedelta(days=1)
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


# --------------------------------------------------------------------- #
# ingest.ingest_runs
# --------------------------------------------------------------------- #


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'failed', 'partial')",
            name="ck_ingest_runs_status_runtime",
        ),
        CheckConstraint(
            "run_kind IN ('scheduled', 'manual', 'backfill', 'fixture')",
            name="ck_ingest_runs_kind_runtime",
        ),
        {"schema": "ingest"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(
        Text, ForeignKey("public.sources.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    counts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    duration_seconds: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3), nullable=True)
    run_kind: Mapped[str] = mapped_column(Text, nullable=False, default="scheduled")


# --------------------------------------------------------------------- #
# ingest.raw_payloads
# --------------------------------------------------------------------- #


class RawPayload(Base):
    __tablename__ = "raw_payloads"
    __table_args__ = ({"schema": "ingest"},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    ingest_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    s3_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_checksum: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    listing_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# --------------------------------------------------------------------- #
# ingest.rejection_log
# --------------------------------------------------------------------- #


class RejectionLog(Base):
    __tablename__ = "rejection_log"
    __table_args__ = ({"schema": "ingest"},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingest_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    error_class: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


# --------------------------------------------------------------------- #
# monitor.scrape_monitor_reports
# --------------------------------------------------------------------- #


class ScrapeMonitorReport(Base):
    __tablename__ = "scrape_monitor_reports"
    __table_args__ = ({"schema": "monitor"},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingest_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    null_rates: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    duplicate_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    http_error_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    flags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


# --------------------------------------------------------------------- #
# monitor.daily_reports
# --------------------------------------------------------------------- #


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("report_date", name="uq_daily_reports_report_date_runtime"),
        {"schema": "monitor"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_date: Mapped[dt.date] = mapped_column(nullable=False)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    per_source: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


# --------------------------------------------------------------------- #
# ai.token_cache  (production analog of the SQLite cache)
# --------------------------------------------------------------------- #


class TokenCacheRow(Base):
    __tablename__ = "token_cache"
    __table_args__ = ({"schema": "ai"},)

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    skill: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    compressed_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# --------------------------------------------------------------------- #
# ai.ai_calls (LLM call audit log)
# --------------------------------------------------------------------- #


class AICall(Base):
    __tablename__ = "ai_calls"
    __table_args__ = ({"schema": "ai"},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pii_rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )

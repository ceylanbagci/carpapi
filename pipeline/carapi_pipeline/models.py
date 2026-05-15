from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_listings_dedupe_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    source_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(256), nullable=False)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    listing_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    make: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    trim: Mapped[str | None] = mapped_column(String(128), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    body_style: Mapped[str | None] = mapped_column(String(64), nullable=True)

    vin: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mileage: Mapped[float | None] = mapped_column(Float, nullable=True)
    mileage_unit: Mapped[str] = mapped_column(String(8), nullable=False, default="unknown")

    price_amount: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    monthly_payment_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)

    seller_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    seller_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    listing_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    listing_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    raw_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    features: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    images: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    # 1024-dim to match Amazon Titan Embed Text v2 (default output).
    # Populated by carpapi/rag/embed.py; HNSW index on cosine ops added in
    # carpapi/db/schema.sql migrations (or manually for older installs).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    raw_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # carpapi DB extensions (managed by carpapi/db/schema.sql, populated
    # at ingest time by carapi_pipeline/pipeline.py).
    car_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    dealer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_on_sale: Mapped[bool] = mapped_column(default=False, nullable=False, server_default=text("false"))
    listing_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Image pipeline (`carpapi/images/`):
    #   image_url     — public S3/CloudFront URL of a 240×160 JPEG thumbnail
    #   image_svg_url — optional minimal SVG silhouette (potrace output)
    # Both nullable; the frontend prefers JPEG and falls back to SVG.
    # Schema is added via the Django RunSQL migration
    # `accounts/migrations/0003_listings_image_columns.py` so it applies
    # on every container boot (Listing isn't a Django model).
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_svg_url: Mapped[str | None] = mapped_column(Text, nullable=True)


def init_schema(engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_listings_make_model ON listings (make, model)"))

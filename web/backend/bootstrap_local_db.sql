-- Local-dev bootstrap: creates the carpapi role + DB on the running
-- Postgres and provisions just enough of the schema for the Django UI
-- to render. Skips pgvector (not installed locally) and the
-- ingest/monitor/ai schemas (Django doesn't query them).
--
-- Run as a Postgres superuser:
--   psql -h localhost -p 5432 -U $USER -d postgres -f bootstrap_local_db.sql

-- (Run the role+db creation outside this file — psql won't run them
-- inside a transaction with \c. See the wrapper script.)

\c carpapi

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- public.dealers — full schema, lifted from carpapi/db/schema.sql
CREATE TABLE IF NOT EXISTS public.dealers (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                     TEXT NOT NULL UNIQUE,
    name                     TEXT NOT NULL,
    homepage_url             TEXT,
    inventory_url            TEXT,
    cms                      TEXT,
    cms_signals              JSONB,
    robots_allows_inventory  BOOLEAN,
    region                   TEXT,
    city                     TEXT,
    postal_code              TEXT,
    latitude                 DOUBLE PRECISION,
    longitude                DOUBLE PRECISION,
    makes_carried            TEXT[],
    status                   TEXT NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'paused', 'blocked')),
    last_scraped_at          TIMESTAMPTZ,
    enrolled_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes                    TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- public.listings — column set from carapi_pipeline.models.Listing,
-- minus the pgvector ``embedding`` column (extension not installed
-- locally). Sufficient for Django list endpoints.
CREATE TABLE IF NOT EXISTS public.listings (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dedupe_key                VARCHAR(512) NOT NULL,
    source_id                 VARCHAR(128) NOT NULL,
    source_name               VARCHAR(256) NOT NULL,
    external_id               VARCHAR(256) NOT NULL,
    listing_url               TEXT NOT NULL,
    title                     TEXT NOT NULL,
    description               TEXT,
    make                      VARCHAR(128),
    model                     VARCHAR(128),
    trim                      VARCHAR(128),
    year                      INTEGER,
    body_style                VARCHAR(64),
    vin                       VARCHAR(32),
    mileage                   DOUBLE PRECISION,
    mileage_unit              VARCHAR(8) NOT NULL DEFAULT 'unknown',
    price_amount              DOUBLE PRECISION,
    currency                  VARCHAR(3) NOT NULL DEFAULT 'USD',
    monthly_payment_estimate  DOUBLE PRECISION,
    seller_name               VARCHAR(256),
    seller_type               VARCHAR(32),
    latitude                  DOUBLE PRECISION,
    longitude                 DOUBLE PRECISION,
    region                    VARCHAR(64),
    city                      VARCHAR(128),
    postal_code               VARCHAR(32),
    listing_posted_at         TIMESTAMPTZ,
    listing_updated_at        TIMESTAMPTZ,
    scraped_at                TIMESTAMPTZ NOT NULL,
    raw_checksum              VARCHAR(128),
    features                  JSONB,
    images                    JSONB,
    raw_document              JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_listings_dedupe_key ON public.listings (dedupe_key);
CREATE INDEX IF NOT EXISTS ix_listings_make_model ON public.listings (make, model);
CREATE INDEX IF NOT EXISTS ix_listings_year ON public.listings (year);
CREATE INDEX IF NOT EXISTS ix_listings_price ON public.listings (price_amount);

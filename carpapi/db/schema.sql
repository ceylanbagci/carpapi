-- CarPapi PostgreSQL schema.
--
-- This file is the structural source of truth. Idempotent: every CREATE
-- uses IF NOT EXISTS, every ALTER TABLE / FK is guarded, every constraint
-- is a no-op on re-run. Apply with:
--
--   PGPASSWORD=carpapi psql -h localhost -p 5433 -U carpapi -d carpapi \
--     -f carpapi/db/schema.sql
--
-- or via the adapter CLI:  python -m carpapi.db init
--
-- Namespaces (PostgreSQL schemas) are intentional — they let us grant
-- read-only roles per domain later (analytics on monitor.*, etc.):
--
--   public   — core entities (listings, dealers, sources, listing_groups)
--   ingest   — pipeline operational state (ingest_runs, raw_payloads, rejection_log)
--   monitor  — telemetry + reporting (scrape_monitor_reports, daily_reports)
--   ai       — TokenCache + LLM call audit (token_cache, ai_calls)
--
-- The 'listings' table is OWNED by the carapi_pipeline package's
-- SQLAlchemy model (carapi_pipeline.models.Listing). This file only
-- ADDS columns to it via ALTER TABLE IF EXISTS — it does not redefine
-- the table.

-- --------------------------------------------------------------------- --
-- Schemas
-- --------------------------------------------------------------------- --

CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS monitor;
CREATE SCHEMA IF NOT EXISTS ai;

-- Always-needed extensions. pgcrypto for gen_random_uuid().
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- --------------------------------------------------------------------- --
-- public.listing_groups
--   One row per "same physical car listed on multiple sites" cluster.
--   carpapi_pipeline.dedupe.build_dedupe_key already groups identical
--   listings within a single dedup key; this table groups across
--   dedup keys (e.g. private-party + dealer relisting same VIN with
--   slightly different prices).
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS public.listing_groups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_vin   TEXT,
    canonical_make  TEXT,
    canonical_model TEXT,
    canonical_trim  TEXT,
    canonical_year  INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_listing_groups_canonical_vin
    ON public.listing_groups (canonical_vin)
    WHERE canonical_vin IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_listing_groups_make_model_year
    ON public.listing_groups (canonical_make, canonical_model, canonical_year);

-- Add columns to public.listings if missing. The listings table is
-- created by carapi_pipeline.models.init_schema; this block layers in
-- carpapi-managed extensions idempotently. Safe to apply while the
-- ingest pipeline is running — all columns are nullable / defaulted.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'public' AND table_name = 'listings') THEN

        -- listing_group_id: cross-source same-physical-car grouping.
        ALTER TABLE public.listings
            ADD COLUMN IF NOT EXISTS listing_group_id UUID;
        BEGIN
            ALTER TABLE public.listings
                ADD CONSTRAINT fk_listings_group_id
                FOREIGN KEY (listing_group_id)
                REFERENCES public.listing_groups(id)
                ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL;
                  WHEN invalid_foreign_key THEN NULL;
        END;
        CREATE INDEX IF NOT EXISTS ix_listings_listing_group_id
            ON public.listings (listing_group_id);

        -- car_url: plain-named alias for the canonical detail-page URL.
        --   Mirrors listing_url at insert/update time so callers can
        --   use the more obvious column name. Indexed for lookups by URL.
        ALTER TABLE public.listings
            ADD COLUMN IF NOT EXISTS car_url TEXT;
        CREATE INDEX IF NOT EXISTS ix_listings_car_url
            ON public.listings (car_url);

        -- dealer_id: FK to public.dealers — the dealership this listing
        --   came from. Resolved at ingest by matching source_id to
        --   dealers.slug. Nullable for fixture / non-dealer sources.
        ALTER TABLE public.listings
            ADD COLUMN IF NOT EXISTS dealer_id UUID;
        BEGIN
            ALTER TABLE public.listings
                ADD CONSTRAINT fk_listings_dealer_id
                FOREIGN KEY (dealer_id)
                REFERENCES public.dealers(id)
                ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL;
                  WHEN invalid_foreign_key THEN NULL;
        END;
        CREATE INDEX IF NOT EXISTS ix_listings_dealer_id
            ON public.listings (dealer_id);

        -- is_on_sale: boolean flag for promotional / sale-priced listings.
        --   Set true at ingest when the source publishes a separate MSRP
        --   higher than the offer price, or when schema.org markup
        --   tags the listing as a sale. Default false.
        ALTER TABLE public.listings
            ADD COLUMN IF NOT EXISTS is_on_sale BOOLEAN NOT NULL DEFAULT false;
        CREATE INDEX IF NOT EXISTS ix_listings_is_on_sale
            ON public.listings (is_on_sale) WHERE is_on_sale = true;
    END IF;
END
$$;

-- --------------------------------------------------------------------- --
-- public.listing_price_history
--   Append-only record of every price change observed on a listing.
--   The pipeline writes a row here ONLY when the new price differs from
--   the previous most-recent entry (or there is no previous entry).
--   Re-scraping a listing whose price hasn't moved produces no new row.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS public.listing_price_history (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id    UUID NOT NULL REFERENCES public.listings(id) ON DELETE CASCADE,
    price_amount  NUMERIC(12, 2),               -- nullable: tracks "price disappeared" too
    currency      TEXT NOT NULL DEFAULT 'USD',
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id     TEXT,                         -- which source the observation came from
    raw_checksum  TEXT                          -- ties back to ingest.raw_payloads when present
);

CREATE INDEX IF NOT EXISTS ix_lph_listing_observed
    ON public.listing_price_history (listing_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_lph_observed
    ON public.listing_price_history (observed_at DESC);

-- --------------------------------------------------------------------- --
-- public.dealers
--   The roster. Seeded from output/dealers_final.json + extended with
--   discovered CMS data (carpapi.scrapers.discover_cms output).
-- --------------------------------------------------------------------- --

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

CREATE INDEX IF NOT EXISTS ix_dealers_cms          ON public.dealers (cms);
CREATE INDEX IF NOT EXISTS ix_dealers_region_status ON public.dealers (region, status);

-- --------------------------------------------------------------------- --
-- public.makes
--   Reference table for vehicle makes — name, USA homepage URL, and a
--   relative path to the brand's placeholder logo (served by Django out
--   of MEDIA_ROOT/logos/). Seeded by web/backend/seed_makes.py from the
--   union of listings.make, dealers.makes_carried[], and a curated
--   homepage map in web/backend/api/make_info.py.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS public.makes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL UNIQUE,
    homepage_url TEXT,
    logo_url     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_makes_name ON public.makes (name);
CREATE INDEX IF NOT EXISTS ix_dealers_makes_gin    ON public.dealers USING gin (makes_carried);

-- --------------------------------------------------------------------- --
-- public.listings — enrichment columns
--   Two-track pipeline:
--     * hot loop  — price_refreshed_at marks the last cheap price refresh
--     * cold loop — maker_url + maker_specs + window_sticker filled once
--                   per VIN by the orchestrator (carpapi.enrich)
--   maker_enrich_status sticks at 'unsupported' / 'login_required' so the
--   orchestrator skips dead-end makes on subsequent runs.
-- --------------------------------------------------------------------- --

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'public' AND table_name = 'listings') THEN
        ALTER TABLE public.listings
            ADD COLUMN IF NOT EXISTS price_refreshed_at  TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS maker_url           TEXT,
            ADD COLUMN IF NOT EXISTS maker_specs         JSONB,
            ADD COLUMN IF NOT EXISTS window_sticker      JSONB,
            ADD COLUMN IF NOT EXISTS window_sticker_url  TEXT,
            ADD COLUMN IF NOT EXISTS maker_enriched_at   TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS maker_enrich_status TEXT,
            ADD COLUMN IF NOT EXISTS maker_enrich_error  TEXT;

        BEGIN
            ALTER TABLE public.listings
                ADD CONSTRAINT ck_listings_maker_enrich_status
                CHECK (maker_enrich_status IS NULL OR maker_enrich_status IN
                       ('pending','enriched','unsupported','login_required','failed'));
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END;

        CREATE INDEX IF NOT EXISTS ix_listings_enrich_pending
            ON public.listings (make)
            WHERE maker_specs IS NULL
              AND (maker_enrich_status IS NULL
                   OR maker_enrich_status NOT IN ('unsupported','login_required'));

        CREATE INDEX IF NOT EXISTS ix_listings_price_refreshed_at
            ON public.listings (price_refreshed_at);
    END IF;
END
$$;

-- --------------------------------------------------------------------- --
-- public.sources
--   Registry of every data source (replaces CARAPI_SOURCE_PRIORITY env var).
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS public.sources (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL
                    CHECK (type IN ('api', 'feed', 'scrape', 'fixture')),
    priority        INTEGER NOT NULL DEFAULT 0,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    license_terms   TEXT,
    ingest_cadence  INTERVAL NOT NULL DEFAULT INTERVAL '1 day',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_sources_enabled ON public.sources (enabled);

-- --------------------------------------------------------------------- --
-- ingest.ingest_runs
--   One row per run_ingest_batch() invocation.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS ingest.ingest_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         TEXT NOT NULL REFERENCES public.sources(id) DEFERRABLE INITIALLY DEFERRED,
    batch_id          UUID,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    status            TEXT NOT NULL
                      CHECK (status IN ('running', 'success', 'failed', 'partial')),
    counts            JSONB,
    error_summary     JSONB,
    duration_seconds  NUMERIC(12, 3),
    run_kind          TEXT NOT NULL DEFAULT 'scheduled'
                      CHECK (run_kind IN ('scheduled', 'manual', 'backfill', 'fixture'))
);

CREATE INDEX IF NOT EXISTS ix_ingest_runs_source_started
    ON ingest.ingest_runs (source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_ingest_runs_status
    ON ingest.ingest_runs (status, started_at DESC);

-- --------------------------------------------------------------------- --
-- ingest.raw_payloads
--   Pointer table for raw scrape artifacts (S3 URI lookup by external_id
--   per source). Survivor of normalization+upsert points at listing.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS ingest.raw_payloads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       TEXT NOT NULL,
    ingest_run_id   UUID,
    external_id     TEXT NOT NULL,
    s3_uri          TEXT,
    raw_checksum    TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    listing_id      UUID
);

CREATE INDEX IF NOT EXISTS ix_raw_payloads_run
    ON ingest.raw_payloads (ingest_run_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_payloads_s3_uri
    ON ingest.raw_payloads (s3_uri)
    WHERE s3_uri IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_raw_payloads_source_external
    ON ingest.raw_payloads (source_id, external_id);

-- --------------------------------------------------------------------- --
-- ingest.rejection_log
--   Records that failed normalization or schema validation.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS ingest.rejection_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingest_run_id   UUID,
    source_id       TEXT NOT NULL,
    raw_payload_id  UUID,
    reason          TEXT NOT NULL,
    error_class     TEXT,
    snippet         TEXT,
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_rejection_log_source_time
    ON ingest.rejection_log (source_id, rejected_at DESC);

-- --------------------------------------------------------------------- --
-- monitor.scrape_monitor_reports
--   Output of carpapi.monitor.scrape_monitor.analyze() — one row per
--   scrape run per source.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS monitor.scrape_monitor_reports (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingest_run_id     UUID,
    source_id         TEXT NOT NULL,
    record_count      INTEGER NOT NULL,
    null_rates        JSONB,
    duplicate_rate    NUMERIC(6, 4),
    http_error_rate   NUMERIC(6, 4),
    flags             TEXT[],
    healthy           BOOLEAN NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_scrape_monitor_source_time
    ON monitor.scrape_monitor_reports (source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_scrape_monitor_unhealthy
    ON monitor.scrape_monitor_reports (created_at DESC) WHERE healthy = false;

-- --------------------------------------------------------------------- --
-- monitor.daily_reports
--   Aggregated daily report (carapi-daily-report output) — one row per
--   date.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS monitor.daily_reports (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date   DATE NOT NULL UNIQUE,
    summary       JSONB,
    per_source    JSONB,
    markdown      TEXT,
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------- --
-- ai.token_cache
--   Production analog of the SQLite TokenCache (single entry point for
--   all Claude calls per ai-cache-rules.md). The Python TokenCache
--   class still drives the lookup; only the backend changes when this
--   table is in use.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS ai.token_cache (
    key               TEXT PRIMARY KEY,           -- sha256 hex
    value             TEXT NOT NULL,
    model             TEXT,
    max_tokens        INTEGER,
    skill             TEXT,
    raw_size          INTEGER,
    compressed_size   INTEGER,
    hit_count         INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_token_cache_expires_at
    ON ai.token_cache (expires_at);
CREATE INDEX IF NOT EXISTS ix_token_cache_skill_time
    ON ai.token_cache (skill, created_at DESC);

-- --------------------------------------------------------------------- --
-- ai.ai_calls
--   Audit log of LLM calls (cache MISSES that hit a real model).
--   Cost / latency tracking lives here.
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS ai.ai_calls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill           TEXT,
    model           TEXT,
    max_tokens      INTEGER,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        NUMERIC(10, 6),
    latency_ms      INTEGER,
    pii_rejected    BOOLEAN NOT NULL DEFAULT false,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ai_calls_time
    ON ai.ai_calls (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_calls_skill_time
    ON ai.ai_calls (skill, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_calls_errors
    ON ai.ai_calls (created_at DESC) WHERE error IS NOT NULL;

-- --------------------------------------------------------------------- --
-- Grants — safe to re-run.
--
-- public has mixed ownership (some tables created by other tooling like
-- Django migrations), so we only grant on the carpapi-owned ones by name.
-- The dedicated schemas (ingest, monitor, ai) are wholly carpapi-owned;
-- we can grant on ALL TABLES there.
-- --------------------------------------------------------------------- --

GRANT USAGE ON SCHEMA ingest, monitor, ai TO carpapi;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    public.listings,
    public.listing_groups,
    public.listing_price_history,
    public.dealers,
    public.sources
TO carpapi;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA ingest, monitor, ai TO carpapi;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ingest, monitor, ai TO carpapi;

ALTER DEFAULT PRIVILEGES IN SCHEMA ingest, monitor, ai
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO carpapi;
ALTER DEFAULT PRIVILEGES IN SCHEMA ingest, monitor, ai
    GRANT USAGE, SELECT ON SEQUENCES TO carpapi;

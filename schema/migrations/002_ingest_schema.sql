-- Migration 002: ingest schema (ingest_runs / raw_payloads / rejection_log)
--
-- Carved out of carpapi/db/schema.sql so the inventory scraper
-- (carpapi.scrapers.run) and listing-validator can write to RDS
-- without dragging in the entire schema file. Idempotent — safe to
-- re-run.

CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS monitor;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- --------------------------------------------------------------------- --
-- ingest.ingest_runs
--   One row per scraper invocation. Used to correlate raw_payloads
--   back to "the 04:00 UTC Dealer.com sweep" or "the manual rescrape
--   of axis_chrysler_jeep_dodge_ram on 2026-05-15".
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
--   The unfiltered scraper output. listing-validator picks rows up
--   from here and normalizes into public.listings.
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
CREATE INDEX IF NOT EXISTS ix_raw_payloads_s3
    ON ingest.raw_payloads (s3_uri) WHERE s3_uri IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_raw_payloads_source_external
    ON ingest.raw_payloads (source_id, external_id);

-- --------------------------------------------------------------------- --
-- ingest.rejection_log
--   Rows that listing-validator refused — schema mismatch, missing
--   required field, parser exception. Audit trail for "why isn't
--   listing X showing up?".
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

-- Migration 001: ref.zip_codes
-- Reference table for US postal codes. Sourced from GeoNames (CC BY 4.0).
-- Used by the dealer-zip-scraper agent (and any future geo radius queries)
-- as the canonical zip → city / state / lat / lng lookup.
--
-- Idempotent: safe to re-run.

CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE IF NOT EXISTS ref.zip_codes (
    zip_code    VARCHAR(10)        PRIMARY KEY,
    city        VARCHAR(180)       NOT NULL,
    state_code  CHAR(2)            NOT NULL,
    state_name  VARCHAR(100),
    county      VARCHAR(180),
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    accuracy    SMALLINT,
    source      VARCHAR(32)        NOT NULL DEFAULT 'geonames',
    created_at  TIMESTAMPTZ        NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ        NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_zip_codes_state ON ref.zip_codes (state_code);
CREATE INDEX IF NOT EXISTS ix_zip_codes_city  ON ref.zip_codes (city);
CREATE INDEX IF NOT EXISTS ix_zip_codes_geo   ON ref.zip_codes (latitude, longitude);

COMMENT ON TABLE  ref.zip_codes IS 'US postal codes (GeoNames, CC BY 4.0). Loaded by scripts/import_zip_codes.py.';
COMMENT ON COLUMN ref.zip_codes.accuracy IS '1=estimated .. 6=address centroid (GeoNames accuracy field)';

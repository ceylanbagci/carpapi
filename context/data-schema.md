# Data Schema Rules

## Authoritative sources
- Canonical listing JSON Schema: [schema/car_listing.schema.json](../schema/car_listing.schema.json)
- Query JSON Schema: [schema/car_query.schema.json](../schema/car_query.schema.json)
- ORM model: [pipeline/carapi_pipeline/models.py](../pipeline/carapi_pipeline/models.py)

These three must stay in sync. The JSON Schema is the contract; the ORM is its Postgres binding.

## Required fields on every listing
`source_id`, `source_name`, `external_id`, `listing_url`, `title`, `currency`, `scraped_at`. Everything else is nullable. See `car_listing.schema.json` for full field list.

## Identifier hierarchy
1. `vin` — 17-char `[A-HJ-NPR-Z0-9]{17}`. Strongest dedup key when present.
2. `(source_id, external_id)` — guarantees per-source uniqueness pre-dedup.
3. `dedupe_key` — internal unique constraint, computed by `carapi_pipeline.dedupe.build_dedupe_key()`. Either `vin:<VIN>` or `fp:<simhash>:<make>:<model>:<year>:<price_bucket>:<mileage_bucket>:<geo>`.

## Geo fields
Listings carry `latitude`, `longitude`, `region` (state code), `city`, `postal_code`. All optional. Radius queries require both `latitude` and `longitude` to be present.

## Schema versioning (TBD — gap)
The canonical schema does not yet carry a `schema_version` field. Add when a parser change requires re-parsing old `raw_document` payloads. Until then: treat any parser change as forward-compatible.

## Storage
- Raw payloads → `raw_document` JSONB column + optional S3 path (`raw_store.py`).
- Embedding column `embedding Vector(1536)` reserved for pgvector RAG. Currently unused.
- Add columns via Alembic migration only (do not run `Base.metadata.create_all` in production).

## What goes in `raw_document`
The post-normalization JSON object that was inserted (post `validate(car_listing_schema)`). Keep the source-side raw HTML/JSON in S3 via `raw_store.write_raw()`, not in this column.

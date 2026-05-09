# Skill: scrape-source

Use when adding ingestion for a new data source (licensed API, partner feed, or sanctioned public source).

## Pre-conditions
- Source is on the allow-list per [context/scraper-rules.md](../context/scraper-rules.md). If not, stop — get sign-off first.
- A `source_id` slug is decided (lowercase snake_case, stable, e.g. `marketcheck_v3`).
- A sample raw payload is saved to `pipeline/carapi_pipeline/fixtures/<source_id>_sample.json` (or `.html`) for regression testing.

## Steps
1. **Register the source** — append a row to the per-source registry table in [context/scraper-rules.md](../context/scraper-rules.md): `source_id, source_name, type, rate_limit, status, notes`.
2. **Add an extractor module** — `pipeline/carapi_pipeline/extractors/<source_id>.py` exposing `def fetch_batch(settings) -> Iterator[dict]:` that yields raw documents in source-native shape. Use Playwright/Scrapy/HTTP per source needs. Honor robots.txt + ToS at runtime.
3. **Add a normalizer mapping** — extend `pipeline/carapi_pipeline/normalize.py` (or a per-source mapper imported from it) so each raw document is mapped to the canonical CarListing schema. Validate with `jsonschema.validate(doc, car_listing_schema)`.
4. **Set source priority** — decide where this source sits in `CARAPI_SOURCE_PRIORITY` survivorship (see [context/deduplication-rules.md](../context/deduplication-rules.md)). Higher number wins on dedup-key collision.
5. **Wire raw storage** — call `raw_store.write_raw(source_id, external_id, raw_bytes)` BEFORE normalization, so failed parses are debuggable.
6. **Add fixture-driven tests** — load the fixture, normalize, assert shape + key fields. No live network in tests.
7. **Add a metric tag** — emit metrics with `source_id` dimension so the daily report can break down by source.
8. **Schedule** — add an EventBridge cron (production) or document local cron equivalent. See [runbooks/daily-schedule.md](../runbooks/daily-schedule.md).

## Don't
- Don't ship without fixture-based tests — they catch source-side HTML drift first.
- Don't cross sources in a single extractor module.
- Don't merge before [context/scraper-rules.md](../context/scraper-rules.md) registry row is added — that's the audit trail.

## Done when
- `carapi-run-pipeline --source <source_id>` ingests the fixture and inserts rows into a clean DB.
- Per-source metrics show up in EMF output.
- Manual: trigger one live fetch, verify rows match expected count and pass schema validation.

# Canonical schemas

- [car_listing.schema.json](car_listing.schema.json) — normalized listing after scrape + map step.  
- [car_query.schema.json](car_query.schema.json) — safe query object the orchestrator maps to SQL / search.

## Deduplication keys

### 1. VIN match (strongest)

When `vin` matches `^[A-HJ-NPR-Z0-9]{17}$` after normalization (uppercase, strip spaces):

- **Dedupe key:** `vin:<normalized_vin>`  
- Listings without valid VIN never use this key.

### 2. Fuzzy fingerprint (no VIN)

Build **fingerprint** from:

| Component | How |
|-----------|-----|
| make | Lowercase, ASCII fold |
| model | Lowercase |
| year | Integer or `null` → `0` |
| price_bucket | `floor(price_amount / 500)` or `null` → `-1` |
| mileage_bucket | `floor(mileage / 1000)` or `null` → `-1` |
| geo | `round(lat, 2):round(lon, 2)` or `region|city` lowercased |
| text_simhash | 64-bit simhash over `title + " " + (description or "")` |

**Dedupe key:** `fp:<hex_simhash>:<make>:<model>:<year>:<pb>:<mb>:<geo>`

Implementation: see `carapi_pipeline.dedupe.build_dedupe_key`.

### 3. Survivorship

- Prefer higher `source_priority` (ingestion config).  
- Then newer `listing_updated_at` / `scraped_at`.  
- Winning row becomes canonical; others link via `duplicate_of_listing_id` (future) or are skipped on insert.

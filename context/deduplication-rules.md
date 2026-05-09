# Deduplication Rules

## Authoritative
- Implementation: [pipeline/carapi_pipeline/dedupe.py](../pipeline/carapi_pipeline/dedupe.py)
- Operational policy: [runbooks/dedupe-policy.md](../runbooks/dedupe-policy.md)

This file summarizes the rules; the linked code/runbook is the source of truth.

## Key construction (in priority order)
1. **VIN match** (when present): `vin:<normalized 17-char VIN>`. Strongest signal.
2. **Fuzzy fingerprint** (no VIN): `fp:<simhash16hex>:<make>:<model>:<year>:<price_bucket>:<mileage_bucket>:<geo>` where:
   - `price_bucket = floor(price / 500)`
   - `mileage_bucket = floor(mileage / 1000)`
   - `geo = round(lat, 2):round(lng, 2)` if coords; else `region|city`; else `unknown`
   - `simhash` = 64-bit simhash over title + description (3-grams, MD5-bit-vote)

## Survivorship rule (which row wins on collision)
1. Higher `source_priority` wins (configured via `CARAPI_SOURCE_PRIORITY` env var, e.g. `"demo_dealer=10,other_feed=5"`).
2. On tie: most recent `listing_updated_at` wins.
3. On tie: most recent `listing_posted_at`.
4. On tie: most recent `scraped_at`.

## Database enforcement
Unique constraint `uq_listings_dedupe_key` on `listings.dedupe_key`. Pipeline upserts by this key.

## Known gaps (plan-tracked)
- **Photo perceptual hash** — not yet implemented. Would catch same-car-different-listings cases where simhash on title+description misses.
- **`listing_group_id`** — not yet tracked. Would let UI show "this car is on 3 sites for $X–$Y."
- **Manual merge override / audit table** — runbook flags this as "future admin API."

## When changing dedup rules
- Bump simhash or bucketing → backfill existing rows by re-running normalize+dedupe; otherwise old keys collide with new in unpredictable ways.
- Update [runbooks/dedupe-policy.md](../runbooks/dedupe-policy.md) summary table.
- Update fixture-based tests in `pipeline/` so the new keys are pinned.

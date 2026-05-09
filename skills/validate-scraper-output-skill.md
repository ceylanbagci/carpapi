# Skill: validate-scraper-output

Use to gate a scraper run before it's merged into the canonical `listings` table.

## Inputs
- A batch of post-normalization documents (canonical CarListing dicts).
- The `source_id` they came from.
- Recent baseline metrics for that source (last 7 days).

## Checks (in order — stop on first failure category)

### 1. Schema validation
Every doc passes `jsonschema.validate(doc, car_listing_schema)`. Reject the batch if any single doc fails — schema drift is upstream and won't fix itself.

### 2. Volume sanity
- `len(batch) > 0` (zero records is itself an alarm condition)
- `len(batch)` within 50%–200% of trailing-7-day median for this source. Outside that range → flag for human review, don't silently accept.

### 3. Field presence rates
Compute null-rate per field. Compare to baseline. Alert if any of these drift:
- `vin` null-rate jumps > 20pp (likely upstream layout change hiding the VIN block)
- `price_amount` null-rate jumps > 10pp (price is critical; bad data here is worse than no data)
- `make`/`model` null-rate jumps > 5pp
- `latitude`/`longitude` null-rate jumps > 30pp (geo is high-noise; tolerate more)

### 4. Distribution sanity
- `year` range mostly within last 30 years; reject batches where > 5% have `year < 1990` or `year > current_year + 1` (likely parsing error).
- `mileage` distribution: < 0.1% with `mileage < 100` (likely parsing error treating "12,500" as "12.5"); < 0.5% with `mileage > 500000`.
- `price_amount`: < 0.1% with `price < 500` or `price > 500000` (parse errors usually land here).

### 5. Dedup-key sanity
- Compute `dedupe_key` for each doc. Within a single batch, expect very few internal duplicates (< 1%). High internal dup rate suggests pagination is double-counting.

### 6. PII scan
Description text matches no `\d{3}[-.\s]\d{3}[-.\s]\d{4}` (US phone) or `\b[\w.+-]+@[\w-]+\.[\w.-]+\b` (email). Fail batch if any rows fail — normalize step should have stripped these.

## On failure
- Write the rejected batch to `monitoring/rejected_batches/<source_id>_<timestamp>.json`.
- Emit `RecordsRejected` metric with `source_id` dimension.
- Page per [runbooks/scrape-failures.md](../runbooks/scrape-failures.md) escalation rules.

## On success
- Hand off to the merge step (`pipeline.upsert_records()`).
- Emit `RecordsNormalized` with batch size.

## Don't
- Don't auto-accept batches that fail volume sanity by "just letting them through" — that's how silent regressions ship.
- Don't run validation on raw documents — only on post-normalization canonical docs.

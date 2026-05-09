# Skill: normalize-listing

Use when mapping a source-specific raw document into the canonical CarListing schema.

## Inputs
- One raw document (dict from JSON or parsed HTML).
- The source_id (drives source-specific quirks).

## Output
- One dict matching [schema/car_listing.schema.json](../schema/car_listing.schema.json), or a typed `RawListing` rejection with reason.

## Steps
1. **Required fields first** — `source_id`, `source_name`, `external_id`, `listing_url`, `title`, `currency`, `scraped_at`. Reject if missing.
2. **VIN cleanup** — strip whitespace, uppercase, validate `[A-HJ-NPR-Z0-9]{17}` via `dedupe.normalize_vin()`. Set null if invalid.
3. **Make/model normalization** — apply per-source string-to-canonical mapping. Examples: `"toyota"` → `"Toyota"`, `"CR V"` → `"CR-V"`, `"chevrolet"` → `"Chevrolet"`. Keep mapping in the per-source extractor, not scattered.
4. **Year** — int 1900–2100, else null.
5. **Mileage** — number; convert km → miles only when source is non-US and label `mileage_unit` accordingly.
6. **Price** — `price_amount` in source currency; `currency` 3-letter ISO. Reject mixed-currency sources without a converter.
7. **Geo** — prefer source-provided `latitude`/`longitude`; fall back to dealer postal_code → centroid only if source consistently lacks coords.
8. **Description** — strip seller PII per [context/compliance-rules.md](../context/compliance-rules.md): regex out phone numbers (US format) and emails before persisting.
9. **`raw_checksum`** — SHA-256 of the canonicalized raw payload (sorted-keys JSON dump). Used for "unchanged → skip" detection.
10. **Validate** — `jsonschema.validate(out, car_listing_schema)`. Reject + emit `RecordsRejected` metric on failure.

## Don't
- Don't fill in missing fields with defaults that look like real data (e.g., `latitude: 0`, `mileage: 0`). Use null.
- Don't translate `body_style` strings — keep them in the canonical set defined in [schema/car_listing.schema.json](../schema/car_listing.schema.json) examples (`SUV`, `Sedan`, `Truck`, `Coupe`, `Hatchback`, `Van`, `Wagon`, `Convertible`).
- Don't compute `dedupe_key` here — that's `dedupe.build_dedupe_key()`'s job.

## Done when
- Fixture inputs round-trip: raw → normalize → JSON-Schema validate → match expected canonical fields.
- All known PII patterns in description are stripped on representative samples.
